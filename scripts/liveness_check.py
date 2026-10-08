#!/usr/bin/env python3
"""Liveness Check — verify each scraper's target URL is reachable.

Reads the list of enabled scrapers from the Node.js scraper registry,
maps each scraper to its target URL, and performs an HTTP HEAD request
to verify reachability.

Exit codes:
    0  All scrapers reachable
    1  One or more scrapers unreachable
    2  Critical error (e.g. config missing, registry query failed)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


# ── Terminal colour support ───────────────────────────────────────────────────

def _supports_color() -> bool:
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_USE_COLOR = _supports_color()


def _green(text: str) -> str:
    return f"\033[92m{text}\033[0m" if _USE_COLOR else text


def _yellow(text: str) -> str:
    return f"\033[93m{text}\033[0m" if _USE_COLOR else text


def _red(text: str) -> str:
    return f"\033[91m{text}\033[0m" if _USE_COLOR else text


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if _USE_COLOR else text


# ── Scraper URL mapping ───────────────────────────────────────────────────────

# Mapping from scraper platform/ID to target URL for liveness checks.
# The platform field from the registry metadata is used as the key.
_SCRAPER_URLS: dict[str, str] = {
    "arc.dev": "https://arc.dev",
    "bulldogjob.pl": "https://bulldogjob.pl",
    "cryptocurrencyjobs": "https://cryptocurrencyjobs.co",
    "cryptojobslist.com": "https://cryptojobslist.com",
    "googlejobs": "https://careers.google.com",
    "indeed.com": "https://indeed.com",
    "jooble.org": "https://jooble.org",
    "justjoin.it": "https://justjoin.it",
    "linkedin.com": "https://linkedin.com",
    "nofluffjobs": "https://nofluffjobs.com",
    "olx": "https://olx.pl",
    "pracuj.pl": "https://pracuj.pl",
    "reddit": "https://reddit.com",
    "remoteok": "https://remoteok.com",
    "simplyhired.com": "https://simplyhired.com",
    "solid.jobs": "https://solid.jobs",
    "upwork": "https://upwork.com",
}


def _resolve_url(platform: str, scraper_id: str) -> str | None:
    """Resolve a scraper's target URL from its platform or ID."""
    if platform in _SCRAPER_URLS:
        return _SCRAPER_URLS[platform]
    if scraper_id in _SCRAPER_URLS:
        return _SCRAPER_URLS[scraper_id]
    return None


# ── Registry metadata loader ───────────────────────────────────────────────────

def _query_registry() -> list[dict[str, Any]]:
    """Query the Node.js scraper registry for metadata.

    Returns a list of scraper metadata dicts.

    Raises RuntimeError if the registry query fails.
    """
    project_root = _find_project_root()
    dump_script = project_root / "packages" / "job-engine-scrapers" / "dump-metadata.js"

    if not dump_script.exists():
        raise RuntimeError(
            f"dump-metadata.js not found at {dump_script}\n"
            "  Have you installed the scraper packages? (make install)"
        )

    try:
        result = subprocess.run(
            ["node", str(dump_script)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(project_root),
        )
    except FileNotFoundError:
        raise RuntimeError("Node.js not found on PATH — cannot query scraper registry")
    except subprocess.TimeoutExpired:
        raise RuntimeError("dump-metadata.js timed out after 30 seconds")

    if result.returncode != 0:
        raise RuntimeError(
            f"dump-metadata.js failed (exit {result.returncode}):\n"
            f"  stderr: {result.stderr.strip()}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"dump-metadata.js output is not valid JSON: {e}")

    if not isinstance(data, list):
        raise RuntimeError(
            f"dump-metadata.js returned unexpected type: {type(data).__name__}"
        )

    return data


# ── Project root discovery ────────────────────────────────────────────────────

def _find_project_root() -> Path:
    """Discover the project root directory."""
    if env_root := os.getenv("JOB_ENGINE_ROOT"):
        return Path(env_root)
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".project-root").exists():
            return parent
    scripts_dir = Path(__file__).resolve().parent
    if (scripts_dir.parent / ".project-root").exists():
        return scripts_dir.parent
    return Path.cwd()


# ── Liveness check ────────────────────────────────────────────────────────────

def _check_url(url: str, scraper_id: str, timeout: float = 5.0) -> tuple[str, str | None]:
    """Check if a URL is reachable via HTTP HEAD.

    Returns (status, error_message) where status is one of:
        "reachable", "unreachable", "error"
    """
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            if 200 <= code < 400:
                return ("reachable", None)
            else:
                return ("unreachable", f"HTTP {code}")
    except urllib.error.HTTPError as e:
        # Some servers don't support HEAD — fall back to GET
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = resp.status
                if 200 <= code < 400:
                    return ("reachable", None)
                else:
                    return ("unreachable", f"HTTP {code}")
        except urllib.error.HTTPError as e2:
            return ("unreachable", f"HTTP {e2.code}")
        except urllib.error.URLError as e2:
            return ("unreachable", str(e2.reason))
        except TimeoutError:
            return ("unreachable", "timeout")
    except urllib.error.URLError as e:
        return ("unreachable", str(e.reason))
    except TimeoutError:
        return ("unreachable", "timeout")
    except Exception as e:
        return ("error", str(e))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print()
    print(_bold("Scraper Liveness Check"))
    print()

    # Query the scraper registry
    try:
        scrapers = _query_registry()
    except RuntimeError as e:
        print(f"  {_red('✗')} Failed to query scraper registry: {e}")
        print()
        return 2

    if not scrapers:
        print(f"  {_yellow('⚠')} No scrapers found in registry")
        print()
        return 0

    # Determine which scrapers are enabled
    # We read the scraper_config.yaml to check enabled status for scrapers that
    # have an entry there. For scrapers not yet in the config file, we check
    # the "enabled" field from the registry metadata.
    scraper_config_path = _find_project_root() / "data" / "scraper_config.yaml"
    enabled_ids: set[str] = set()

    if scraper_config_path.exists():
        try:
            from ruamel.yaml import YAML
            yaml = YAML()
            with open(scraper_config_path) as f:
                config_data = yaml.load(f)
            if config_data and "scrapers" in config_data:
                for scraper_id, scraper_cfg in config_data["scrapers"].items():
                    if isinstance(scraper_cfg, dict) and scraper_cfg.get("enabled", False):
                        enabled_ids.add(scraper_id)
        except Exception as e:
            print(f"  {_yellow('⚠')} Could not read scraper config: {e}")
            print(f"  {_yellow('⚠')} Falling back to registry metadata enabled status")
    else:
        print(f"  {_yellow('⚠')} scraper_config.yaml not found — using registry metadata")

    # Merge: if we have no config data, rely on registry metadata 'enabled' field
    if not enabled_ids:
        for s in scrapers:
            if s.get("enabled", True):
                enabled_ids.add(s["id"])

    results: list[dict[str, Any]] = []
    reachable_count = 0
    unreachable_count = 0
    error_count = 0
    skipped_count = 0

    for scraper in scrapers:
        scraper_id = scraper["id"]
        name = scraper.get("name", scraper_id)
        platform = scraper.get("platform", scraper_id)
        enabled = scraper_id in enabled_ids

        if not enabled:
            skipped_count += 1
            continue

        url = _resolve_url(platform, scraper_id)

        if url is None:
            results.append({
                "id": scraper_id,
                "name": name,
                "url": None,
                "status": "skipped",
                "detail": "no URL mapping",
            })
            skipped_count += 1
            continue

        status, error = _check_url(url, scraper_id)
        detail = error or ""

        results.append({
            "id": scraper_id,
            "name": name,
            "url": url,
            "status": status,
            "detail": detail,
        })

        if status == "reachable":
            reachable_count += 1
            print(f"  {_green('✓')} {name:25s} {url}")
        elif status == "unreachable":
            unreachable_count += 1
            print(f"  {_red('✗')} {name:25s} {url}  — {_red(detail)}")
        else:
            error_count += 1
            print(f"  {_yellow('⚠')} {name:25s} {url}  — {_yellow(detail)}")

    # Summary
    checked = reachable_count + unreachable_count + error_count
    print()
    if checked == 0:
        print(f"  {_yellow('⚠')} No enabled scrapers to check")
    elif unreachable_count == 0 and error_count == 0:
        print(f"  {_green(f'All {checked} enabled scrapers reachable')}"
              f" ({skipped_count} disabled/skipped)")
    else:
        print(f"  {_red(f'{unreachable_count} unreachable, {error_count} error(s)')}"
              f" — {reachable_count} reachable, {skipped_count} disabled/skipped")

    print()

    if error_count > 0:
        return 2
    if unreachable_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())