from __future__ import annotations

import re
import unicodedata

from app.compact import estimate_tokens
from app.llm.base import ChatMessage
from app.scenario import LoadedScenario, LoreEntry

LORE_BUDGET_TOKENS = 1200
LORE_SCAN_TURNS = 2

_HEADING_RE = re.compile(r"^(#{1,6})([ \t].*)$")


def normalize_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def keyword_matches(keyword: str, text: str) -> bool:
    needle = normalize_text(keyword)
    if not needle:
        return False
    haystack = normalize_text(text)
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def build_scan_text(window: list[ChatMessage], message: str) -> str:
    tail = window[-(LORE_SCAN_TURNS * 2) :]
    parts = [msg.content for msg in tail] + [message]
    return "\n".join(parts)


def _neutralize_headings(text: str) -> str:
    lines = text.split("\n")
    result = []
    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            level = min(len(match.group(1)) + 3, 6)
            result.append(f"{'#' * level}{match.group(2)}")
        else:
            result.append(line)
    return "\n".join(result)


def _render_one(entry: LoreEntry) -> str:
    title = " ".join(entry.title.split())
    body = _neutralize_headings(entry.body.strip())
    return f"### {title}\n{body}" if body else f"### {title}"


def select_lore(scenario: LoadedScenario, scan_text: str) -> list[LoreEntry]:
    candidates = [(entry_id, entry) for entry_id, entry in scenario.lorebook.items() if entry.enabled]

    selected = [
        (entry_id, entry)
        for entry_id, entry in candidates
        if entry.scope == "always"
        or (entry.scope == "keyword" and any(keyword_matches(keyword, scan_text) for keyword in entry.keywords))
    ]

    selected.sort(key=lambda pair: (-pair[1].priority, pair[0]))

    # Budget is measured on the rendered section, separators included, so it matches
    # estimate_tokens(render_lore(result)).
    result: list[LoreEntry] = []
    rendered_parts: list[str] = []
    for _entry_id, entry in selected:
        candidate = "\n\n".join([*rendered_parts, _render_one(entry)])
        if estimate_tokens(candidate) > LORE_BUDGET_TOKENS:
            break
        rendered_parts.append(_render_one(entry))
        result.append(entry)

    return result


def lore_ids(scenario: LoadedScenario, entries: list[LoreEntry]) -> list[str]:
    """Maps entries back to their scenario ids by identity, not equality."""
    ids: list[str] = []
    for entry in entries:
        for entry_id, candidate in scenario.lorebook.items():
            if candidate is entry:
                ids.append(entry_id)
                break
    return ids


def render_lore(entries: list[LoreEntry]) -> str | None:
    if not entries:
        return None
    return "\n\n".join(_render_one(entry) for entry in entries)
