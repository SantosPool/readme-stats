#!/usr/bin/env python3
"""
Generates profile/stats.svg and profile/languages.svg from GitHub GraphQL API.
Requires: GH_TOKEN (PAT with `repo` scope), optionally GH_USERNAME.
"""
import os
import sys
from datetime import datetime, timezone

import requests

TOKEN = os.environ.get("GH_TOKEN")
if not TOKEN:
    sys.exit("Error: GH_TOKEN environment variable is not set")

USERNAME = os.environ.get("GH_USERNAME")
if not USERNAME:
    sys.exit("Error: GH_USERNAME environment variable is not set")
OUT = "profile"
os.makedirs(OUT, exist_ok=True)

GQL_URL = "https://api.github.com/graphql"
HEADERS = {"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"}

# Dark theme colours (mirrors github-readme-stats default dark)
BG      = "#1a1b27"
BORDER  = "#e4e2e2"
TITLE   = "#e4e2e2"
LABEL   = "#9f9f9f"
VALUE   = "#e4e2e2"
FONT    = "'Segoe UI', Ubuntu, 'Helvetica Neue', sans-serif"
BAR_BG  = "#2d2d3f"
ACCENT  = "#70a5fd"


# ── GraphQL helpers ──────────────────────────────────────────────────────────

def gql(query, variables=None):
    r = requests.post(
        GQL_URL,
        json={"query": query, "variables": variables or {}},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch():
    print(f"→ Fetching profile for @{USERNAME}")

    # 1. Basic user info
    user = gql(
        """query($u:String!){user(login:$u){
            name login createdAt
            followers{totalCount}
            pullRequests{totalCount}
            issues{totalCount}
        }}""",
        {"u": USERNAME},
    )["user"]

    created_year = max(int(user["createdAt"][:4]), 2015)
    now_year = datetime.now(timezone.utc).year

    # 2. Commits per year (public + private via restrictedContributionsCount)
    #    restrictedContributionsCount counts private contributions when the user
    #    has enabled "Include private contributions on my profile" in GitHub settings.
    #    With your own PAT those are always visible regardless of that setting.
    print(f"→ Counting commits {created_year}–{now_year}")
    total_commits = 0
    for yr in range(created_year, now_year + 1):
        try:
            cc = gql(
                """query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){
                    contributionsCollection(from:$f,to:$t){
                        totalCommitContributions
                        restrictedContributionsCount
                    }
                }}""",
                {
                    "u": USERNAME,
                    "f": f"{yr}-01-01T00:00:00Z",
                    "t": f"{yr}-12-31T23:59:59Z",
                },
            )["user"]["contributionsCollection"]
            total_commits += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        except Exception as e:
            print(f"  ⚠ skipping {yr}: {e}", file=sys.stderr)

    # 3. Repos (paginated) — includes private because the PAT has repo scope
    print("→ Fetching repositories")
    all_repos, cursor = [], None
    while True:
        data = gql(
            """query($u:String!,$c:String){user(login:$u){
                repositories(ownerAffiliations:OWNER,isFork:false,first:100,after:$c){
                    nodes{
                        name
                        stargazers{totalCount}
                        defaultBranchRef{
                            target{
                                ... on Commit{ history{ totalCount } }
                            }
                        }
                        languages(first:10,orderBy:{field:SIZE,direction:DESC}){
                            edges{size node{color name}}
                        }
                    }
                    pageInfo{hasNextPage endCursor}
                }
            }}""",
            {"u": USERNAME, "c": cursor},
        )["user"]["repositories"]
        all_repos.extend(data["nodes"])
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]

    total_stars = sum(r["stargazers"]["totalCount"] for r in all_repos)

    # 4. Aggregate language bytes
    lang_bytes, lang_colors = {}, {}
    for repo in all_repos:
        for edge in repo["languages"]["edges"]:
            n = edge["node"]["name"]
            lang_bytes[n] = lang_bytes.get(n, 0) + edge["size"]
            lang_colors[n] = edge["node"]["color"] or "#858585"

    top = sorted(lang_bytes.items(), key=lambda kv: -kv[1])[:8]
    total_bytes = sum(s for _, s in top)
    languages = [
        {
            "name": n,
            "color": lang_colors[n],
            "pct": s / total_bytes * 100 if total_bytes else 0,
        }
        for n, s in top
    ]

    # 5. Top repos by commit count on default branch
    repo_commits = []
    for repo in all_repos:
        ref = repo.get("defaultBranchRef")
        if ref and ref.get("target"):
            count = ref["target"]["history"]["totalCount"]
            if count > 0:
                langs = [
                    {"name": e["node"]["name"], "color": e["node"]["color"] or "#858585"}
                    for e in repo["languages"]["edges"][:4]
                ]
                repo_commits.append({"name": repo["name"], "commits": count, "langs": langs})

    repo_commits.sort(key=lambda r: -r["commits"])
    top_repos = repo_commits[:8]
    total_repo_commits = sum(r["commits"] for r in top_repos)
    for r in top_repos:
        r["pct"] = r["commits"] / total_repo_commits * 100 if total_repo_commits else 0

    return {
        "name":     user["name"] or user["login"],
        "followers": user["followers"]["totalCount"],
        "prs":       user["pullRequests"]["totalCount"],
        "issues":    user["issues"]["totalCount"],
        "commits":   total_commits,
        "stars":     total_stars,
        "langs":     languages,
        "projects":  top_repos,
    }


# ── SVG helpers ───────────────────────────────────────────────────────────────

def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def txt(content, x, y, fill=LABEL, size=13, weight="400", anchor="start"):
    return (
        f'<text font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" x="{x}" y="{y}" text-anchor="{anchor}">{content}</text>'
    )


# ── Stats SVG ─────────────────────────────────────────────────────────────────

def make_stats(d):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Grid: 3 rows × 2 cols  (col 1 only has 2 items, so row 2 col 1 is empty)
    row_y   = [82, 117, 152]
    # (label_x, value_x)  — values are right-anchored
    col_pos = [(25, 233), (263, 468)]

    items = [
        (0, 0, "⭐ Total Stars",    f"{d['stars']:,}"),
        (0, 1, "🔨 Total Commits",  f"{d['commits']:,}"),
        (1, 0, "🔀 Pull Requests",  f"{d['prs']:,}"),
        (1, 1, "🐛 Issues",         f"{d['issues']:,}"),
        (2, 0, "👥 Followers",      f"{d['followers']:,}"),
    ]

    lines = []
    for row, col, label, value in items:
        y = row_y[row]
        lx, vx = col_pos[col]
        lines.append(f"  {txt(esc(label), lx, y)}")
        lines.append(f"  {txt(esc(value), vx, y, fill=VALUE, weight='700', anchor='end')}")

    content = "\n".join(lines)
    name    = esc(d["name"])

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="495" height="185" viewBox="0 0 495 185">
  <rect width="494" height="184" x=".5" y=".5" rx="4.5" fill="{BG}" stroke="{BORDER}" stroke-opacity=".1"/>
  {txt(f"{name}’s GitHub Stats", 25, 35, fill=TITLE, size=17, weight="600")}
  <line x1="25" x2="470" y1="49" y2="49" stroke="{BORDER}" stroke-opacity=".1"/>
{content}
  {txt(f"Updated {today}", 470, 178, size=10, anchor="end")}
</svg>"""


# ── Languages SVG ─────────────────────────────────────────────────────────────

def make_langs(langs):
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    PAD     = 25
    LABEL_W = 118
    BAR_X   = PAD + LABEL_W
    BAR_W   = 272
    PCT_X   = BAR_X + BAR_W + 10
    ROW_H   = 38
    BAR_H   = 8
    TITLE_H = 60
    FOOTER_H = 28
    height  = TITLE_H + len(langs) * ROW_H + FOOTER_H

    rows = []
    for i, lang in enumerate(langs):
        y      = TITLE_H + i * ROW_H
        text_y = y + 18
        bar_y  = y + 6
        fill_w  = max(1, int(BAR_W * lang["pct"] / 100))
        pct_str = f"{lang['pct']:.1f}%"
        color   = lang["color"]
        name    = esc(lang["name"])
        rows.append(
            f"  {txt(name, PAD, text_y)}\n"
            f'  <rect x="{BAR_X}" y="{bar_y}" width="{BAR_W}" height="{BAR_H}" rx="4" fill="{BAR_BG}"/>\n'
            f'  <rect x="{BAR_X}" y="{bar_y}" width="{fill_w}" height="{BAR_H}" rx="4" fill="{color}"/>\n'
            f"  {txt(pct_str, PCT_X, text_y, fill=VALUE, size=12)}"
        )

    content = "\n".join(rows)
    sep_y   = TITLE_H - 5

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="495" height="{height}" viewBox="0 0 495 {height}">
  <rect width="494" height="{height - 1}" x=".5" y=".5" rx="4.5" fill="{BG}" stroke="{BORDER}" stroke-opacity=".1"/>
  {txt("Top Languages", PAD, 35, fill=TITLE, size=17, weight="600")}
  {txt("(public + private repos)", PAD, 50, size=11)}
  <line x1="{PAD}" x2="470" y1="{sep_y}" y2="{sep_y}" stroke="{BORDER}" stroke-opacity=".1"/>
{content}
  {txt(f"Updated {today}", 470, height - 8, size=10, anchor="end")}
</svg>"""


# ── Projects SVG ─────────────────────────────────────────────────────────────

def make_projects(projects):
    today    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    PAD      = 25
    BAR_W    = 380
    PCT_X    = PAD + BAR_W + 10
    BAR_H    = 8
    ROW_H    = 62   # 3 lines: name / bar / languages
    TITLE_H  = 60
    FOOTER_H = 28
    height   = TITLE_H + len(projects) * ROW_H + FOOTER_H

    def lang_dots(langs, base_y):
        """Colored circle + name for each language, spaced horizontally."""
        elements = []
        x = PAD
        for lang in langs:
            cx   = x + 5
            cy   = base_y - 4
            col  = lang["color"]
            name = esc(lang["name"])
            # estimate char width at 11px font ≈ 6.5px/char
            label_w = int(len(lang["name"]) * 6.5)
            elements.append(f'<circle cx="{cx}" cy="{cy}" r="4" fill="{col}"/>')
            elements.append(txt(name, x + 13, base_y, fill=LABEL, size=11))
            x += 13 + label_w + 14   # circle + label + gap
            if x > 460:
                break
        return "\n  ".join(elements)

    rows = []
    for i, proj in enumerate(projects):
        y        = TITLE_H + i * ROW_H
        name_y   = y + 16
        bar_y    = y + 26
        langs_y  = y + 50
        fill_w   = max(1, int(BAR_W * proj["pct"] / 100))
        pct_str  = f"{proj['commits']:,}  ({proj['pct']:.1f}%)"
        name     = esc(proj["name"])
        rows.append(
            f"  {txt(name, PAD, name_y, fill=VALUE, size=13, weight='600')}\n"
            f'  <rect x="{PAD}" y="{bar_y}" width="{BAR_W}" height="{BAR_H}" rx="4" fill="{BAR_BG}"/>\n'
            f'  <rect x="{PAD}" y="{bar_y}" width="{fill_w}" height="{BAR_H}" rx="4" fill="{ACCENT}"/>\n'
            f"  {txt(pct_str, PCT_X, bar_y + 7, fill=LABEL, size=11)}\n"
            f"  {lang_dots(proj['langs'], langs_y)}"
        )

    content = "\n".join(rows)
    sep_y   = TITLE_H - 5

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="495" height="{height}" viewBox="0 0 495 {height}">
  <rect width="494" height="{height - 1}" x=".5" y=".5" rx="4.5" fill="{BG}" stroke="{BORDER}" stroke-opacity=".1"/>
  {txt("Top Projects by Commits", PAD, 35, fill=TITLE, size=17, weight="600")}
  {txt("(public + private repos)", PAD, 50, size=11)}
  <line x1="{PAD}" x2="470" y1="{sep_y}" y2="{sep_y}" stroke="{BORDER}" stroke-opacity=".1"/>
{content}
  {txt(f"Updated {today}", 470, height - 8, size=10, anchor="end")}
</svg>"""


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    data = fetch()
    print(f"  stars={data['stars']}  commits={data['commits']}  "
          f"prs={data['prs']}  issues={data['issues']}")
    print(f"  top langs:     {[l['name'] for l in data['langs']]}")
    print(f"  top projects:  {[p['name'] for p in data['projects']]}")

    cards = [
        (f"{OUT}/stats.svg",    make_stats(data)),
        (f"{OUT}/languages.svg", make_langs(data["langs"])),
        (f"{OUT}/projects.svg",  make_projects(data["projects"])),
    ]
    for path, svg in cards:
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"✓ {path}")
