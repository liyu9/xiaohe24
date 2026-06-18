#!/usr/bin/env python3
"""GitHub repo health check for third-party skills/libraries.

Usage:
    python github-repo-health.py <owner>/<repo>

Returns JSON with: stars, forks, open_issues, created_at, pushed_at,
default_branch, archived, description, size_kb, and a verdict field
("healthy" | "suspicious" | "demo-only" | "abandoned") with a list of
red flags.

Red flags:
- created_at == pushed_at and recent (abandoned-on-arrival)
- README still has placeholder text
- archived
- last commit > 12 months ago
- low stars + low forks + no description
"""
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

PLACEHOLDER_PATTERNS = [
    r"\byourusername\b",
    r"\byour[-_]?org(?:anization)?\b",
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bXXX\b",
    r"<repo[-_]?name>",
    r"<owner>",
    r"<author>",
    r"lorem ipsum",
]


def gh_api(path: str) -> dict:
    url = f"https://api.github.com/{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "hermes-blocked-content-recovery",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def gh_raw(owner: str, repo: str, branch: str, path: str) -> str | None:
    """Fetch a raw file from the repo's default branch. Returns None on 404."""
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-health-check"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError:
        return None


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def check(owner: str, repo: str) -> dict:
    meta = gh_api(f"repos/{owner}/{repo}")
    flags: list[str] = []

    stars = meta.get("stargazers_count", 0) or 0
    forks = meta.get("forks_count", 0) or 0
    issues = meta.get("open_issues_count", 0) or 0
    created = parse_dt(meta["created_at"])
    pushed = parse_dt(meta["pushed_at"])
    archived = bool(meta.get("archived"))
    description = (meta.get("description") or "").strip()
    branch = meta.get("default_branch") or "main"

    # Flag 1: abandoned-on-arrival (created and last commit within 24h)
    if (pushed - created).total_seconds() < 86400:
        flags.append("created_and_pushed_within_24h")

    # Flag 2: archived
    if archived:
        flags.append("archived")

    # Flag 3: last commit > 12 months ago
    age_days = (datetime.now(timezone.utc) - pushed).days
    if age_days > 365:
        flags.append(f"last_commit_{age_days}_days_ago")

    # Flag 4: low engagement + no description
    if stars < 5 and forks < 5 and not description:
        flags.append("low_engagement_no_description")

    # Flag 5: README has placeholder text
    readme_text = ""
    for fname in ("README.md", "readme.md", "Readme.md", "README.rst", "README"):
        readme_text = gh_raw(owner, repo, branch, fname) or ""
        if readme_text:
            break
    placeholder_hits = []
    if readme_text:
        for pat in PLACEHOLDER_PATTERNS:
            if re.search(pat, readme_text, re.IGNORECASE):
                placeholder_hits.append(pat)
    if placeholder_hits:
        flags.append(f"readme_placeholders:{','.join(placeholder_hits)}")

    # Verdict
    if archived or age_days > 730:
        verdict = "abandoned"
    elif placeholder_hits or (stars < 5 and forks < 5):
        verdict = "demo-only"
    elif flags:
        verdict = "suspicious"
    else:
        verdict = "healthy"

    return {
        "repo": f"{owner}/{repo}",
        "stars": stars,
        "forks": forks,
        "open_issues": issues,
        "created_at": meta["created_at"],
        "pushed_at": meta["pushed_at"],
        "last_commit_days_ago": age_days,
        "default_branch": branch,
        "archived": archived,
        "description": description,
        "size_kb": meta.get("size"),
        "readme_placeholder_hits": placeholder_hits,
        "red_flags": flags,
        "verdict": verdict,
    }


def main() -> int:
    if len(sys.argv) != 2 or "/" not in sys.argv[1]:
        print("usage: github-repo-health.py <owner>/<repo>", file=sys.stderr)
        return 2
    owner, repo = sys.argv[1].split("/", 1)
    try:
        result = check(owner, repo)
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": f"HTTP {e.code}", "body": e.read()[:300].decode()}, indent=2))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["verdict"] in ("healthy", "suspicious") else 3


if __name__ == "__main__":
    sys.exit(main())
