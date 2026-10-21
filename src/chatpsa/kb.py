"""Validation and dry-run planning for HaloPSA knowledge articles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .safe import safe_kb_tag_projection


def build_kb_article_create_plan(
    *,
    title: str,
    description: str,
    resolution: str,
    tag_ids: Sequence[int],
    available_tags: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    title = " ".join(title.split())
    description = description.strip()
    resolution = resolution.strip()
    if not 3 <= len(title) <= 180:
        raise ValueError("title must contain between 3 and 180 characters")
    if not description or len(description) > 20_000:
        raise ValueError("description must contain between 1 and 20000 characters")
    if not resolution or len(resolution) > 30_000:
        raise ValueError("resolution must contain between 1 and 30000 characters")
    if len(tag_ids) > 20 or any(not isinstance(tag_id, int) or tag_id <= 0 for tag_id in tag_ids):
        raise ValueError("tag_ids must contain at most 20 positive integers")

    by_id = {
        tag.get("id"): safe_kb_tag_projection(tag)
        for tag in available_tags
        if isinstance(tag.get("id"), int)
    }
    missing = sorted(set(tag_ids) - set(by_id))
    if missing:
        raise ValueError(f"Unknown HaloPSA tag IDs: {missing}")
    selected = [by_id[tag_id] for tag_id in dict.fromkeys(tag_ids)]
    return {
        "name": title,
        "description_markdown": description,
        "resolution_markdown": resolution,
        "tags": selected,
        "inactive": True,
        "is_draft": True,
    }


def build_release_create_plan(
    *,
    name: str,
    notes: str,
    release_type_id: int,
    available_types: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    name = " ".join(name.split())
    notes = notes.strip()
    if not 3 <= len(name) <= 180:
        raise ValueError("name must contain between 3 and 180 characters")
    if not notes or len(notes) > 30_000:
        raise ValueError("notes must contain between 1 and 30000 characters")
    by_id = {
        item.get("id"): item
        for item in available_types
        if isinstance(item.get("id"), int)
    }
    if release_type_id not in by_id:
        raise ValueError("Unknown HaloPSA release type ID")
    return {
        "name": name,
        "releasetype_id": release_type_id,
        "note": notes,
        "public_note": notes,
    }
