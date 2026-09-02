// Mirrors strip_engine_echo in backend/app/cleanup.py (TCK-026); divergence is a contract bug.
const HEADING_RE = /^#{1,6}\s*(turno|turn|hud|estado do jogo|game state)\b/i
const HUD_LABEL_RE = /^\*\*\s*(hud|estado do jogo|game state)\s*\*\*\s*:?/i
const HUD_FIELD_RE = /^\s*(?:[-*]\s*)?(?:\*\*)?\s*(turno|turn|local|location|hora|time|clima|weather)\s*(?:\*\*)?\s*[::]\s*\S/i
const PLAYER_ECHO_RE = /^\*\*\s*(voce|você|you|player|jogador)\s*\*\*\s*\|/i
const SEPARATOR_RE = /^[-*_=#~\s]+$/

const LINE_PATTERNS = [HEADING_RE, HUD_LABEL_RE, HUD_FIELD_RE, PLAYER_ECHO_RE, SEPARATOR_RE]

export function isEngineEchoLine(line: string): boolean {
  const stripped = line.trim()
  return LINE_PATTERNS.some((pattern) => pattern.test(stripped))
}
