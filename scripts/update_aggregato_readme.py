#!/usr/bin/env python3
"""Refresh the Spotify and media activity sections of the profile README."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

README = Path(__file__).resolve().parents[1] / "README.md"
START = "<!-- aggregato:latest-start -->"
END = "<!-- aggregato:latest-end -->"
SPOTIFY_START = "<!-- aggregato:spotify-start -->"
SPOTIFY_END = "<!-- aggregato:spotify-end -->"
MEDIA_TYPES = (
    ("anime", "Anime"),
    ("manga", "Manga"),
    ("film", "Films"),
    ("book", "Books"),
)
ENTRY_LIMIT = 25
MEDIA_COVER_LIMIT = 5
SPOTIFY_LIMIT = 1


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


def image_tag(title: str, image: object, base_url: str, details: str = "") -> str:
    if not isinstance(image, str) or not image.startswith("/api/v1/media/image/"):
        return ""
    clean_title = " ".join(title.split())[:120]
    title_attr = html.escape(" · ".join(filter(None, (clean_title, details))), quote=True)
    source = html.escape(f"{base_url.rstrip('/')}{image}", quote=True)
    return f'<img src="{source}" alt="" title="{title_attr}" width="120">'


def render_entries(
    sections: list[tuple[str, list[dict[str, object]]]], base_url: str
) -> str:
    lines = []
    for label, entries in sections:
        items = []
        seen: set[str] = set()
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
            work_id = work.get("id")
            if isinstance(work_id, str) and work_id in seen:
                continue
            if isinstance(work_id, str):
                seen.add(work_id)
            details = []
            if isinstance(work.get("release_year"), int):
                details.append(str(work["release_year"]))
            details.append(kind.replace("_", " ").title())
            date = format_date(logged_at, precision)
            if date:
                details.append(date)
            detail_text = " · ".join(details)
            image = image_tag(title, work.get("image"), base_url, detail_text)
            if image:
                caption = html.escape(" ".join(title.split())[:120])
                items.append(
                    f'<td align="center">{image}<br><strong>{caption}</strong>'
                    f"<br><small>{html.escape(detail_text)}</small></td>"
                )
            if len(items) == MEDIA_COVER_LIMIT:
                break
        if items:
            lines.extend([f"### {label}", "", "<table><tr>", *items, "</tr></table>", ""])
    return "\n".join(lines).strip() or "_No recent media updates._"


def render_spotify(entries: list[dict[str, object]], base_url: str) -> str:
    if not entries:
        return "_No recent listens._"
    entry = entries[0]
    if not isinstance(entry, dict):
        raise ValueError("Unexpected entry in Aggregato response")
    work = entry.get("work")
    if work is None:
        return "_No recent listens._"
    if not isinstance(work, dict):
        raise ValueError("Unexpected work in Aggregato response")
    title = work.get("title")
    if not isinstance(title, str):
        raise ValueError("Unexpected title in Aggregato response")
    image = image_tag(title, work.get("image"), base_url)
    title_text = html.escape(" ".join(title.split())[:120])
    content = f"<strong>{title_text}</strong>"
    return f"{image}<br>{content}" if image else content


def replace_section(
    readme: str, content: str, start_marker: str = START, end_marker: str = END
) -> str:
    if readme.count(start_marker) != 1 or readme.count(end_marker) != 1:
        raise ValueError("README must contain one Aggregato start and end marker")
    start = readme.index(start_marker) + len(start_marker)
    end = readme.index(end_marker)
    if end < start:
        raise ValueError("Aggregato README markers are out of order")
    return readme[:start] + "\n" + content + "\n" + readme[end:]


def fetch_entries(
    base_url: str,
    token: str,
    media_type: str,
    limit: int = ENTRY_LIMIT,
    provider: str | None = None,
) -> list[dict[str, object]]:
    params = {
        "media_type": media_type,
        "status": "completed",
        "sort": "logged_at",
        "order": "desc",
        "limit": limit,
    }
    if provider:
        params["provider"] = provider
    query = urlencode(params)
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
    return page["items"][:limit]


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
    spotify = fetch_entries(base_url, token, "track", SPOTIFY_LIMIT, "spotify")
    updated = replace_section(readme, render_entries(sections, base_url))
    updated = replace_section(
        updated,
        render_spotify(spotify, base_url),
        SPOTIFY_START,
        SPOTIFY_END,
    )
    if updated != readme:
        README.write_text(updated)
        print("Updated media activity in README.md")
    else:
        print("README.md is already up to date")


if __name__ == "__main__":
    main()
