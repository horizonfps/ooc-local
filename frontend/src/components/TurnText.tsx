import { useMemo } from 'react'
import { t } from '../i18n'
import './turnText.css'

// Mirrors TAG_RE in backend/app/tags.py (TCK-004); divergence is a contract bug.
export const TAG_RE = /\[([A-Z][A-Z0-9_]*):([^\]\n]*)\]/g

const SPEAKER_RE = /^\*\*(.+?)\*\*\s*\|\s*(.*)$/
const TRAILING_WHITESPACE_RE = /[ \t]+/g
const SPACE_BEFORE_PUNCT_RE = /[ \t]+([.,;:!?…])/g

type Block =
  | { kind: 'narration'; text: string; raw?: boolean }
  | { kind: 'speech'; name: string; text: string }

function cleanLine(line: string): string {
  let out = line.replace(TAG_RE, '')
  out = out.replace(TRAILING_WHITESPACE_RE, ' ')
  out = out.replace(SPACE_BEFORE_PUNCT_RE, '$1')
  return out.trim()
}

function findUnclosedBracket(text: string): number {
  const openIdx = text.lastIndexOf('[')
  if (openIdx === -1) return -1
  return text.indexOf(']', openIdx) === -1 ? openIdx : -1
}

function buildBlocks(text: string): Block[] {
  const blocks: Block[] = []
  for (const line of text.split('\n')) {
    const cleaned = cleanLine(line)
    if (cleaned === '') continue
    const match = SPEAKER_RE.exec(cleaned)
    if (match && match[1].trim() !== '') {
      blocks.push({ kind: 'speech', name: match[1].trim(), text: match[2] })
    } else {
      blocks.push({ kind: 'narration', text: cleaned })
    }
  }
  return blocks
}

function parseTurnText(text: string, streaming: boolean): Block[] {
  const normalized = text.replace(/\r\n/g, '\n')
  if (normalized.trim() === '') return []

  const unclosedIdx = findUnclosedBracket(normalized)
  if (unclosedIdx === -1) {
    return buildBlocks(normalized)
  }

  // Only the line carrying the unclosed bracket is affected; earlier lines parse normally.
  const lineStart = normalized.lastIndexOf('\n', unclosedIdx) + 1
  const blocks = buildBlocks(normalized.slice(0, lineStart))
  const brokenLine = normalized.slice(lineStart)

  if (streaming) {
    const prefix = cleanLine(brokenLine.slice(0, unclosedIdx - lineStart))
    if (prefix !== '') {
      const match = SPEAKER_RE.exec(prefix)
      if (match && match[1].trim() !== '') {
        blocks.push({ kind: 'speech', name: match[1].trim(), text: match[2] })
      } else {
        blocks.push({ kind: 'narration', text: prefix })
      }
    }
    return blocks
  }

  if (brokenLine.trim() !== '') {
    blocks.push({ kind: 'narration', text: brokenLine, raw: true })
  }
  return blocks
}

export function TurnText({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const blocks = useMemo(() => {
    try {
      return parseTurnText(text, streaming)
    } catch {
      return text.trim() === '' ? [] : [{ kind: 'narration' as const, text, raw: true }]
    }
  }, [text, streaming])

  if (blocks.length === 0) return null

  return (
    <div className="turnText">
      {blocks.map((block, index) =>
        block.kind === 'speech' ? (
          <p key={index} className="turnText-line turnText-line--speech">
            <span className="turnText-srLabel">{t('turnText.speakerLabel', { name: block.name })}</span>
            <strong className="turnText-speaker">{block.name}</strong>
            <span className="turnText-speech">{block.text}</span>
          </p>
        ) : (
          <p
            key={index}
            className="turnText-line turnText-line--narration"
            title={block.raw ? t('turnText.rawFallback') : undefined}
          >
            <span className="turnText-srLabel">{t('turnText.narrationLabel')}</span>
            <em>{block.text}</em>
          </p>
        ),
      )}
    </div>
  )
}
