import re

# A narration line that literally starts with "Hora: " is sacrificed on purpose:
# it is indistinguishable from HUD echo and vanishingly rare in second-person prose.

_HEADING_RE = re.compile(r"^#{1,6}\s*(turno|turn|hud|estado do jogo|game state)\b.*$", re.IGNORECASE)
_HUD_LABEL_RE = re.compile(r"^\*\*\s*(hud|estado do jogo|game state)\s*\*\*\s*:?\s*.*$", re.IGNORECASE)
_HUD_FIELD_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?\s*(turno|turn|local|location|hora|time|clima|weather)\s*(?:\*\*)?\s*:\s*\S.*$",
    re.IGNORECASE,
)
_PLAYER_ECHO_RE = re.compile(r"^\*\*\s*(voce|você|you|player|jogador)\s*\*\*\s*\|.*$", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"^[-*_=#~\s]+$")

_LINE_PATTERNS = (_HEADING_RE, _HUD_LABEL_RE, _HUD_FIELD_RE, _PLAYER_ECHO_RE, _SEPARATOR_RE)


def _is_engine_echo(line: str) -> bool:
    stripped = line.strip()
    return any(pattern.match(stripped) for pattern in _LINE_PATTERNS)


def strip_engine_echo(text: str) -> tuple[str, int]:
    """Returns the text without engine-echo lines and how many lines were dropped."""
    out: list[str] = []
    dropped = 0
    for line in text.split("\n"):
        if _is_engine_echo(line):
            dropped += 1
            continue
        out.append(line)

    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()

    return "\n".join(out), dropped
