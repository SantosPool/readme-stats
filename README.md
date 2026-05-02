# readme-stats

Generates GitHub stats SVGs via a GitHub Action and commits them to `profile/` —
**no Vercel, no external service required**.  
Cards include **private repos** and **all years of commits**.

---

## Generated cards (Examples)

| Stats | Languages |
|-------|-----------|
| ![Languages](https://raw.githubusercontent.com/SantosPool/readme-stats/main/profile/languages.svg) | ![Stats](https://raw.githubusercontent.com/SantosPool/readme-stats/main/profile/stats.svg) |

![Projects](https://raw.githubusercontent.com/SantosPool/readme-stats/main/profile/projects.svg)

---

## Setup (one-time)

### 1 — Fork / use this repo

Create a **public** repo named `readme-stats` in your account (or fork this one).  
It must be public so that `raw.githubusercontent.com` links work without auth.

### 2 — Create a Personal Access Token (PAT)

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens** (or classic tokens).
2. Create a token with **`repo`** scope (classic) — this allows reading all public and private repos.
3. Copy the token value.

> **Why a PAT?**  
> The automatic `GITHUB_TOKEN` that Actions provides is scoped only to the current repo.  
> A PAT with `repo` scope lets the script read data from *all* your repos via the GraphQL API.

### 3 — Add the secret and the username variable

In **your `readme-stats` repo** go to: Settings → Secrets and variables → Actions

**Secret** (tab Secrets → New repository secret):
| Name | Value |
|------|-------|
| `GH_TOKEN` | the PAT from step 2 |

**Variable** (tab Variables → New repository variable):
| Name | Value |
|------|-------|
| `GH_USERNAME` | your GitHub username (e.g. `YourUsername`) |

### 4 — (Optional) Enable private contribution counts

For the commit total to include private contributions on your profile graph:

GitHub → Settings → Contributions → tick **"Include private contributions on my profile"**.

Even without this setting, the script counts commits from private repos because it
uses *your own token* — the graph on your public profile is a separate display concern.

### 5 — Trigger the workflow

Go to **Actions → Update GitHub Stats → Run workflow**.  
After it finishes, `profile/stats.svg` and `profile/languages.svg` will be committed.

The workflow also runs automatically **every day at 06:00 UTC** and whenever
`generate_stats.py` is pushed.

---

## Embed in your profile README

In your profile repo (`YOUR_USERNAME/YOUR_USERNAME`) add:

```markdown
![Stats](https://raw.githubusercontent.com/YOUR_USERNAME/readme-stats/main/profile/stats.svg)
![Languages](https://raw.githubusercontent.com/YOUR_USERNAME/readme-stats/main/profile/languages.svg)
![Projects](https://raw.githubusercontent.com/YOUR_USERNAME/readme-stats/main/profile/projects.svg)
```

GitHub caches raw content aggressively. To bust the cache append `?v=1` and increment
the number each time you want a fresh load, or just wait ~5 minutes.

---

## Customisation

| What | Where |
|------|-------|
| Your username | `GH_USERNAME` env var in `.github/workflows/update-stats.yml` |
| Number of top languages | `[:8]` slice in `generate_stats.py` → `fetch()` |
| Theme colours | `BG`, `BORDER`, `TITLE`, `LABEL`, `VALUE` constants at the top of `generate_stats.py` |
| Schedule | `cron:` line in `.github/workflows/update-stats.yml` |

---

## Local run

```bash
pip install -r requirements.txt
GH_TOKEN=ghp_xxx GH_USERNAME=YOUR_USERNAME python generate_stats.py
# SVGs written to profile/stats.svg and profile/languages.svg
```

---

## How it works

```
GitHub Actions (daily)
  └─ generate_stats.py
       ├─ GitHub GraphQL API  (PAT with repo scope)
       │    ├─ user info (name, followers, PRs, issues)
       │    ├─ commits per year, created_year → now  (public + private)
       │    └─ all repos (paginated) → stars + language bytes
       ├─ Renders profile/stats.svg
       ├─ Renders profile/languages.svg
       └─ git commit && git push  →  main branch
```

Raw SVG URLs (`raw.githubusercontent.com/…/profile/stats.svg`) are then embedded
directly in any README — no server, no API key at render time.
