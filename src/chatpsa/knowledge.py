"""File-backed guides and private, query-scoped tenant memory."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import project_root

GUIDES_DIR = project_root() / "knowledge" / "guides"
TENANT_GUIDES_DIR = project_root() / "knowledge" / "tenant"
TENANT_SOURCE_FILES: tuple[Path, ...] = ()
WORD_PATTERN = re.compile(r"[a-zA-ZÀ-ÿ0-9_-]{2,}")
HEADING_PATTERN = re.compile(r"(?m)^#{1,4}\s+.+$")
SECRET_LINE_PATTERN = re.compile(
    r"(?im)^.*(?:secret|password|passwd|api[_ -]?key|access[_ -]?token|"
    r"authorization)\s*[:=].*$"
)
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


@dataclass(frozen=True)
class Guide:
    guide_id: str
    title: str
    summary: str
    tags: tuple[str, ...]
    body: str

    def public_dict(self, *, include_body: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "id": self.guide_id,
            "title": self.title,
            "summary": self.summary,
            "tags": list(self.tags),
        }
        if include_body:
            result["body"] = self.body
        return result


def _parse_guide(path: Path) -> Guide | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    try:
        metadata_text, body = text[4:].split("\n---\n", 1)
    except ValueError:
        return None
    metadata: dict[str, str] = {}
    for line in metadata_text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip().casefold()] = value.strip()
    title = metadata.get("title", "").strip()
    summary = metadata.get("summary", "").strip()
    guide_id = metadata.get("id", path.stem).strip()
    if not title or not summary or not guide_id:
        return None
    tags = tuple(
        item.strip().casefold()
        for item in metadata.get("tags", "").split(",")
        if item.strip()
    )
    return Guide(
        guide_id=guide_id,
        title=title,
        summary=summary,
        tags=tags,
        body=body.strip(),
    )


def load_guides(directory: Path | None = None) -> list[Guide]:
    # Packaged guides are safe to expose as full Guide objects. Tenant-private
    # notes must only travel through search_tenant_memory(), which bounds and
    # redacts their excerpts before they can reach an external model.
    directories = [directory] if directory else [GUIDES_DIR]
    paths = [
        path
        for guide_dir in directories
        if guide_dir is not None and guide_dir.is_dir()
        for path in sorted(guide_dir.glob("*.md"))
    ]
    guides = [guide for path in paths if (guide := _parse_guide(path))]
    return guides


def search_guides(query: str, *, limit: int = 4) -> list[Guide]:
    terms = {match.group(0).casefold() for match in WORD_PATTERN.finditer(query)}
    guides = load_guides()
    if not terms:
        return guides[:limit]

    ranked: list[tuple[int, Guide]] = []
    for guide in guides:
        title = guide.title.casefold()
        summary = guide.summary.casefold()
        tags = set(guide.tags)
        body = guide.body.casefold()
        score = sum(
            8 * (term in title)
            + 6 * (term in tags)
            + 3 * (term in summary)
            + (term in body)
            for term in terms
        )
        if score:
            ranked.append((score, guide))
    ranked.sort(key=lambda item: (-item[0], item[1].title.casefold()))
    return [guide for _, guide in ranked[:limit]]


def _redact_secrets(text: str) -> str:
    """Remove credential-shaped lines before any tenant note reaches an LLM."""

    text = SECRET_LINE_PATTERN.sub("[riga credenziale rimossa]", text)
    return BEARER_PATTERN.sub("Bearer [REDACTED]", text)


def _markdown_sections(text: str, *, max_chars: int = 6_000) -> list[str]:
    starts = [match.start() for match in HEADING_PATTERN.finditer(text)]
    if not starts:
        return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]
    starts.append(len(text))
    sections: list[str] = []
    for index in range(len(starts) - 1):
        section = text[starts[index] : starts[index + 1]].strip()
        sections.extend(
            section[offset : offset + max_chars]
            for offset in range(0, len(section), max_chars)
        )
    return sections


def search_tenant_memory(
    query: str,
    *,
    limit: int = 6,
    max_total_chars: int = 18_000,
) -> list[dict[str, str]]:
    """Retrieve relevant private notes without copying them into public Git.

    Only an explicit allowlist is read. Credential files such as ``.env`` and
    ``.env.txt`` are deliberately impossible to load through this function.
    """

    terms = {match.group(0).casefold() for match in WORD_PATTERN.finditer(query)}
    if not terms:
        return []
    ranked: list[tuple[int, str, str]] = []
    for path in (*TENANT_SOURCE_FILES, *sorted(TENANT_GUIDES_DIR.glob("*.md"))):
        if not path.is_file():
            continue
        text = _redact_secrets(path.read_text(encoding="utf-8", errors="replace"))
        for section in _markdown_sections(text):
            lowered = section.casefold()
            score = sum(4 * lowered.count(term) for term in terms)
            heading = section.splitlines()[0] if section else path.stem
            score += sum(8 for term in terms if term in heading.casefold())
            if score:
                ranked.append((score, path.name, section))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2][:80]))
    selected: list[dict[str, str]] = []
    used = 0
    for _, source, content in ranked:
        remaining = max_total_chars - used
        if remaining <= 0 or len(selected) >= limit:
            break
        excerpt = content[:remaining]
        selected.append({"source": source, "excerpt": excerpt})
        used += len(excerpt)
    return selected
