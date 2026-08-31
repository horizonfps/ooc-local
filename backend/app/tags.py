import re

from pydantic import BaseModel

TAG_RE = re.compile(r"\[([A-Z][A-Z0-9_]*):([^\]\n]*)\]")

_TRAILING_WHITESPACE_RE = re.compile(r"[ \t]+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \t]+([.,;:!?…])")


class Tag(BaseModel):
    kind: str
    args: list[str]
    raw: str
    valid: bool


def _validate(kind: str, args: list[str]) -> bool:
    if kind == "STAT":
        return len(args) == 2 and bool(re.match(r"^[+-]?\d+$", args[1]))
    if kind == "SPRITE":
        return len(args) == 2 and all(args)
    if kind == "BG":
        return len(args) == 1 and bool(args[0])
    return True


def parse_tags(text: str) -> tuple[str, list[Tag]]:
    tags: list[Tag] = []

    def _replace(match: re.Match[str]) -> str:
        kind = match.group(1)
        raw_args = match.group(2)
        args = [part.strip() for part in raw_args.split(":")] if raw_args else []
        valid = _validate(kind, args)
        tags.append(Tag(kind=kind, args=args, raw=match.group(0), valid=valid))
        return ""

    stripped = TAG_RE.sub(_replace, text)

    lines = stripped.split("\n")
    original_lines = text.split("\n")
    cleaned_lines: list[str] = []
    for original, line in zip(original_lines, lines):
        line = _TRAILING_WHITESPACE_RE.sub(" ", line)
        line = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", line)
        line = line.strip()
        if line == "" and original.strip() != "":
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines), tags
