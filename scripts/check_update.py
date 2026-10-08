#!/usr/bin/env python3
"""Check for updates by comparing local version against GitHub releases."""

import json
import sys
import urllib.request
import urllib.error


def get_local_version() -> str:
    """Read version from the VERSION file at the project root."""
    import os
    version_path = os.path.join(os.path.dirname(__file__), "..", "VERSION")
    try:
        with open(version_path) as f:
            return f.read().strip()
    except FileNotFoundError:
        print("✗ VERSION file not found")
        sys.exit(2)


def get_latest_github_release(owner: str = "happydasch", repo: str = "job-engine") -> str | None:
    """Fetch the latest release tag from GitHub."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("tag_name", "").lstrip("v")
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        print(f"⚠ Could not fetch latest release: {e}")
        return None


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a semver string into a tuple of ints."""
    parts = version_str.split(".")
    return tuple(int(p) for p in parts[:3])


def main():
    local = get_local_version()
    print(f"Local version: {local}")

    latest = get_latest_github_release()
    if latest:
        print(f"Latest release: {latest}")
        local_parts = parse_version(local)
        latest_parts = parse_version(latest)

        if local_parts >= latest_parts:
            print("✓ You are up to date!")
            sys.exit(0)
        else:
            print(f"⚠ Update available: {latest} (you have {local})")
            sys.exit(1)
    else:
        print("⚠ Could not check for updates (offline or API unavailable)")
        sys.exit(1)


if __name__ == "__main__":
    main()