#!/usr/bin/env python3
"""Refresh the marked media activity section of the profile README."""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

README = Path(__file__).resolve().parents[1] / "README.md"
START = "<!-- aggregato:latest-start -->"
END = "<!-- aggregato:latest-end -->"
MEDIA_TYPES = (
    ("anime", "Anime"),
    ("manga", "Manga"),
    ("film", "Films"),
    ("book", "Books"),
)
ENTRY_LIMIT = 3


def escape_markdown(value: str) -> str:
    value = html.escape(" ".join(value.split())[:120], quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|~])", r"\\\1", value)


def format_date(value: str, precision: str) -> str:
    if precision == "unknown":
        return ""
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return {
        "year": date.strftime("%Y"),
        "month": date.strftime("%Y-%m"),
        "day": date.strftime("%Y-%m-%d"),
        "exact": date.strftime("%Y-%m-%d"),
    }[precision]


def render_entries(sections: list[tuple[str, list[dict[str, object]]]]) -> str:
    lines = []
    for label, entries in sections:
        items = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Unexpected entry in Aggregato response")
            work = entry.get("work")
            if work is None:
                continue
            if not isinstance(work, dict):
                raise ValueError("Unexpected work in Aggregato response")
            title, kind, logged_at, precision = (
                work.get("title"),
                entry.get("kind"),
                entry.get("logged_at"),
                entry.get("logged_precision"),
            )
            if not all(
                isinstance(value, str) for value in (title, kind, logged_at, precision)
            ):
                raise ValueError("Unexpected entry in Aggregato response")

            details = []
            if isinstance(work.get("release_year"), int):
                details.append(str(work["release_year"]))
            details.append(escape_markdown(kind.replace("_", " ").title()))
            date = format_date(logged_at, precision)
            if date:
                details.append(date)
            items.append(f"- **{escape_markdown(title)}** · {' · '.join(details)}")
        if items:
            lines.extend([f"### {label}", "", *items, ""])
    return "\n".join(lines).strip() or "_No recent media updates._"


def replace_section(readme: str, content: str) -> str:
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("README must contain one Aggregato start and end marker")
    start = readme.index(START) + len(START)
    end = readme.index(END)
    if end < start:
        raise ValueError("Aggregato README markers are out of order")
    return readme[:start] + "\n" + content + "\n" + readme[end:]


def fetch_entries(base_url: str, token: str, media_type: str) -> list[dict[str, object]]:
    query = urlencode(
        {
            "media_type": media_type,
            "status": "completed",
            "sort": "logged_at",
            "order": "desc",
            "limit": ENTRY_LIMIT,
        }
    )
    request = Request(
        f"{base_url.rstrip('/')}/api/v1/entries?{query}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "minipps-aggregato-readme/1.0",
        },
    )
    with urlopen(request, timeout=20) as response:
        page = json.load(response)
    if not isinstance(page, dict) or not isinstance(page.get("items"), list):
        raise ValueError("Unexpected response from Aggregato API")
    return page["items"][:ENTRY_LIMIT]


def main() -> None:
    token = os.environ.get("AGGREGATO_READONLY_TOKEN")
    if not token:
        raise SystemExit("Set the AGGREGATO_READONLY_TOKEN GitHub Actions secret")
    base_url = os.environ.get("AGGREGATO_URL")
    if not base_url:
        raise SystemExit("Set the AGGREGATO_URL GitHub Actions secret")
    readme = README.read_text()
    sections = [
        (label, fetch_entries(base_url, token, media_type))
        for media_type, label in MEDIA_TYPES
    ]
    updated = replace_section(readme, render_entries(sections))
    if updated != readme:
        README.write_text(updated)
        print("Updated media activity in README.md")
    else:
        print("README.md is already up to date")


if __name__ == "__main__":
    main()
