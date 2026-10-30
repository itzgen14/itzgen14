# itzgen14 profile README — asset pipeline

Renders live GitHub stats into SVG assets committed back to `main`, so the
profile README shows real numbers instead of hardcoded ones.

## Layout

```
scripts/update_readme_assets.py   renderer (stdlib only)
assets/icons/                     Font Awesome 6 SVGs, inlined into output
assets/panel.svg                  generated — followers/repos/stars/commits/contributors/visitors
assets/contributors.svg           generated — contributor roster
assets/stats.json                 generated — raw data snapshot
.github/workflows/sync-readme-assets.yml   every 6h + on push to scripts/
.github/workflows/snake.yml        contribution snake -> output branch
```

## Local run

```bash
GITHUB_TOKEN=ghp_xxx python3 scripts/update_readme_assets.py
```

`GITHUB_TOKEN` optional (raises rate limit 60 -> 5000/h).
`VISITOR_BADGE_URL` optional — set to a komarev-style badge URL to fold the
visitor counter into the panel; without it the VISITORS cell is omitted.

## Setup on GitHub

1. Push this repo as `itzgen14/itzgen14` (profile README = repo named after the user).
2. Actions > "Sync README Assets" > enable. Runs immediately, then every 6h.
3. Optional: Settings > Variables > Actions > add `VISITOR_BADGE_URL`
   = `https://komarev.com/ghpvc/?username=itzgen14&style=flat&color=0F172A&label=VISITORS`
4. Enable "Snake" workflow; it publishes to the `output` branch which the
   README references via `raw.githubusercontent.com/Platane/snk/output/...`
   — that URL only resolves once the snake action has run at least once.
   Until then the snake image 404s; harmless.

## Notes

- Panel/contributor SVGs are regenerated on a diff-guarded commit, so a failed
  API call never produces an empty or broken image.
- Commit count uses the `Link: rel="last"` header on `per_page=1`, not pagination.
- Repo forks excluded from aggregates.
