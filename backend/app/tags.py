import re

from pydantic import BaseModel

TAG_RE = re.compile(r"\[([A-Z][A-Z0-9_]*):([^\[\]\n]*)\]")

_TRAILING_WHITESPACE_RE = re.compile(r"[ \t]+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \t]+([.,;:!?…])")
_WORD_CHAR_RE = re.compile(r"[^\W_]", re.UNICODE)


class Tag(BaseModel):
    kind: str
    args: list[str]
    raw: str
    valid: bool


def _validate(kind: str, args: list[str]) -> bool:
    if kind == "STAT":
        return len(args) == 2 and bool(re.match(r"^[+-]?[0-9]+$", args[1]))
    if kind == "SPRITE":
        return len(args) == 2 and all(args)
    if kind == "BG":
        return len(args) == 1 and bool(args[0])
    if kind == "LOC":
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

        line = match.string
        before = line[match.start() - 1] if match.start() > 0 else ""
        after = line[match.end()] if match.end() < len(line) else ""
        if before and after and _WORD_CHAR_RE.match(before) and _WORD_CHAR_RE.match(after):
            return " "
        return ""

    out: list[str] = []
    for line in text.split("\n"):
        if not TAG_RE.search(line):
            out.append(line)
            continue
        cleaned = TAG_RE.sub(_replace, line)
        cleaned = _TRAILING_WHITESPACE_RE.sub(" ", cleaned)
        cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
        cleaned = cleaned.strip()
        if cleaned == "":
            continue
        out.append(cleaned)

    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()

    return "\n".join(out), tags
