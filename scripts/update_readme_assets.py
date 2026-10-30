#!/usr/bin/env python3
"""
itzgen14 README asset generator.

Pulls live data from the GitHub REST API and renders two SVG assets that the
profile README references by raw URL:

  assets/panel.svg         - system panel: followers / repos / stars / commits / contributors / visitors
  assets/contributors.svg  - contributor roster with commit counts

Stdlib only. Auth via GITHUB_TOKEN env (Actions provides it automatically;
unauthenticated works too, 60 req/h).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

OWNER = os.environ.get("GH_OWNER", "itzgen14")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
VISITOR_URL = os.environ.get("VISITOR_BADGE_URL", "").strip()
ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "assets" / "icons"
OUT = ROOT / "assets"

API = "https://api.github.com"
UA = {"Accept": "application/vnd.github+json", "User-Agent": "itzgen14-readme-sync"}
if TOKEN:
    UA["Authorization"] = f"Bearer {TOKEN}"

# palette
BG = "#0F172A"
CARD = "#161B22"
BORDER = "#334155"
MUTED = "#94A3B8"
DIM = "#64748B"
FG = "#F8FAFC"
ACCENT = "#22C55E"


def api(path):
    req = urllib.request.Request(API + path, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()), r
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        print(f"  ! {path} -> HTTP {e.code}", file=sys.stderr)
        return None, None
    except Exception as e:
        print(f"  ! {path} -> {e}", file=sys.stderr)
        return None, None


def icon(name, color, size=14):
    """Inline a Font Awesome svg as a <g> with currentColor replaced."""
    f = ICONS / f"{name}.svg"
    if not f.exists():
        return ""
    raw = f.read_text()
    m = re.search(r'<path[^>]*d="([^"]+)"', raw)
    if not m:
        return ""
    d = m.group(1)
    vb = re.search(r'viewBox="([^"]+)"', raw)
    x0, y0, w, h = (float(v) for v in vb.group(1).split()) if vb else (0, 0, 512, 512)
    scale = size / max(w, h)
    return (
        f'<g transform="translate(0,0) scale({scale:.4f})" fill="{color}">'
        f'<path d="{d}"/></g>'
    )


def text(x, y, s, size=11, color=MUTED, weight="normal", anchor="start", family="monospace"):
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(s))}</text>'
    )


def commit_count(repo):
    """Total commits via Link rel=last on per_page=1."""
    req = urllib.request.Request(
        f"{API}/repos/{OWNER}/{repo}/commits?per_page=1", headers=UA
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            link = r.headers.get("Link") or ""
            m = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link)
            if m:
                return int(m.group(1))
            body = json.loads(r.read().decode())
            return len(body)
    except urllib.error.HTTPError as e:
        if e.code in (409, 404):  # empty repo / gone
            return 0
        print(f"  ! commits {repo} -> HTTP {e.code}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"  ! commits {repo} -> {e}", file=sys.stderr)
        return 0


def fetch_all():
    user, _ = api(f"/users/{OWNER}")
    repos, _ = api(f"/users/{OWNER}/repos?per_page=100&type=owner")
    repos = repos or []
    repos = [r for r in repos if not r.get("fork")]

    stats = {
        "followers": (user or {}).get("followers", 0),
        "following": (user or {}).get("following", 0),
        "public_repos": (user or {}).get("public_repos", len(repos)),
        "stars": sum(r.get("stargazers_count", 0) for r in repos),
        "forks": sum(r.get("forks_count", 0) for r in repos),
        "commits": 0,
        "visitors": None,
        "repos": [],
    }
    for r in repos:
        n = commit_count(r["name"])
        stats["commits"] += n
        stats["repos"].append(
            {
                "name": r["name"],
                "desc": r.get("description") or "",
                "lang": r.get("language") or "-",
                "stars": r.get("stargazers_count", 0),
                "commits": n,
                "pushed": (r.get("pushed_at") or "")[:10],
            }
        )

    # contributors aggregated across owned repos
    contrib = {}
    for r in repos:
        data, _ = api(f"/repos/{OWNER}/{r['name']}/contributors?per_page=100")
        for c in data or []:
            if c.get("type") != "User":
                continue
            login = c["login"]
            if login not in contrib:
                contrib[login] = {"login": login, "commits": 0, "avatar": c.get("avatar_url", "")}
            contrib[login]["commits"] += c.get("contributions", 0)
    stats["contributors"] = sorted(
        contrib.values(), key=lambda c: (-c["commits"], c["login"])
    )

    if VISITOR_URL:
        try:
            req = urllib.request.Request(
                VISITOR_URL, headers={"User-Agent": "itzgen14-readme-sync"}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode(errors="ignore")
            # komarev/visitorbadge emit the count as the last standalone
            # numeric text node; take the largest plausible count found.
            nums = [
                int(n)
                for n in re.findall(r">\s*(\d{1,12})\s*<", body)
            ]
            if nums:
                stats["visitors"] = max(nums)
        except Exception as e:
            print(f"  ! visitor badge -> {e}", file=sys.stderr)
    return stats


def render_panel(stats):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cells = [
        ("users", "FOLLOWERS", stats["followers"]),
        ("cube", "REPOS", stats["public_repos"]),
        ("star", "STARS", stats["stars"]),
        ("code-branch", "COMMITS", stats["commits"]),
        ("robot", "CONTRIBS", len(stats["contributors"])),
    ]
    if stats["visitors"] is not None:
        cells.append(("eye", "VISITORS", stats["visitors"]))

    W = 880
    cell_w = (W - 40 - (len(cells) - 1) * 10) / len(cells)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="150" '
        f'viewBox="0 0 {W} 150" font-family="monospace">',
        f'<rect width="{W}" height="150" rx="10" fill="{BG}" stroke="{BORDER}" stroke-width="2"/>',
    ]
    # header
    parts.append(f'<g transform="translate(18,26)">{icon("terminal", ACCENT, 13)}</g>')
    parts.append(text(40, 30, "ITZGEN14 // SYSTEM PANEL", 13, FG, "bold"))
    parts.append(
        f'<circle cx="{W - 30}" cy="26" r="4" fill="{ACCENT}">'
        f'<animate attributeName="opacity" values="1;0.2;1" dur="2s" repeatCount="indefinite"/></circle>'
    )
    parts.append(text(W - 42, 30, "ONLINE", 10, ACCENT, "bold", anchor="end"))
    parts.append(
        f'<line x1="18" y1="42" x2="{W - 18}" y2="42" stroke="{BORDER}" stroke-width="1" stroke-dasharray="4 4"/>'
    )

    for i, (ic, label, val) in enumerate(cells):
        x = 20 + i * (cell_w + 10)
        parts.append(
            f'<rect x="{x:.1f}" y="56" width="{cell_w:.1f}" height="62" rx="6" '
            f'fill="{CARD}" stroke="{BORDER}"/>'
        )
        parts.append(f'<g transform="translate({x + 12:.1f},64)">{icon(ic, ACCENT, 12)}</g>')
        parts.append(text(x + 12, 96, label, 9, DIM, "bold"))
        parts.append(text(x + 12, 112, f"{val:,}", 20, FG, "bold"))

    parts.append(
        f'<line x1="18" y1="128" x2="{W - 18}" y2="128" stroke="{BORDER}" stroke-width="1"/>'
    )
    parts.append(text(18, 142, f"LAST_SYNC {ts}", 9, DIM))
    parts.append(
        text(
            W - 18,
            142,
            "AUTO-UPDATED BY GITHUB_ACTIONS // 6H CYCLE",
            9,
            DIM,
            anchor="end",
        )
    )
    parts.append("</svg>")
    return "\n".join(parts)


def render_contributors(stats):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = stats["contributors"][:12]
    W = 880
    row_h = 26
    H = 60 + len(rows) * row_h + (16 if len(rows) < len(stats["contributors"]) else 0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="monospace">',
        f'<rect width="{W}" height="{H}" rx="10" fill="{BG}" stroke="{BORDER}" stroke-width="2"/>',
        f'<g transform="translate(18,26)">{icon("robot", ACCENT, 13)}</g>',
        text(40, 30, "CONTRIBUTOR_REGISTRY", 13, FG, "bold"),
        text(W - 18, 30, f"TOTAL {len(stats['contributors'])}", 10, ACCENT, "bold", anchor="end"),
        f'<line x1="18" y1="42" x2="{W - 18}" y2="42" stroke="{BORDER}" stroke-width="1" stroke-dasharray="4 4"/>',
    ]
    if not rows:
        parts.append(text(20, 70, "NO_CONTRIBUTORS_YET // BE_THE_FIRST", 11, DIM))
    for i, c in enumerate(rows):
        y = 62 + i * row_h
        parts.append(
            f'<rect x="18" y="{y}" width="{W - 36}" height="{row_h - 4}" rx="4" fill="{CARD}"/>'
        )
        parts.append(f'<g transform="translate(28,{y + 6})">{icon("fingerprint", ACCENT, 11)}</g>')
        parts.append(text(46, y + 17, c["login"], 11, FG, "bold"))
        parts.append(text(W - 30, y + 17, f"{c['commits']} commits", 10, MUTED, anchor="end"))
    if len(rows) < len(stats["contributors"]):
        parts.append(
            text(20, H - 6, f"+{len(stats['contributors']) - len(rows)} more", 9, DIM)
        )
    parts.append(text(W - 18, H - 6, ts, 9, DIM, anchor="end"))
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    print(f"[*] fetching github data for {OWNER} ...")
    stats = fetch_all()
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    (OUT / "panel.svg").write_text(render_panel(stats))
    (OUT / "contributors.svg").write_text(render_contributors(stats))
    print(
        f"[+] panel.svg + contributors.svg + stats.json written "
        f"(followers={stats['followers']} repos={stats['public_repos']} "
        f"stars={stats['stars']} commits={stats['commits']} "
        f"contribs={len(stats['contributors'])} visitors={stats['visitors']})"
    )


if __name__ == "__main__":
    main()
