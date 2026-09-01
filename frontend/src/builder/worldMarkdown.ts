export type GuidedWorld = { universe: string; tone: string; rules: string; conflict: string; mission: string }

export const WORLD_HEADINGS = ['Universe', 'Tone', 'Rules', 'Conflict', 'Mission'] as const

const FIELD_OF_HEADING: Record<(typeof WORLD_HEADINGS)[number], keyof GuidedWorld> = {
  Universe: 'universe',
  Tone: 'tone',
  Rules: 'rules',
  Conflict: 'conflict',
  Mission: 'mission',
}

export function serializeGuidedWorld(w: GuidedWorld): string {
  return WORLD_HEADINGS.map((heading) => [heading, w[FIELD_OF_HEADING[heading]].trim()] as const)
    .filter(([, text]) => text !== '')
    .map(([heading, text]) => `## ${heading}\n\n${text}`)
    .join('\n\n')
}

export function parseGuidedWorld(md: string): GuidedWorld | null {
  const lines = md.split('\n')
  const result: GuidedWorld = { universe: '', tone: '', rules: '', conflict: '', mission: '' }
  let currentField: keyof GuidedWorld | null = null
  let currentLines: string[] = []
  let lastHeadingIndex = -1
  let sawHeading = false

  function flush() {
    if (currentField) result[currentField] = currentLines.join('\n').trim()
  }

  for (const line of lines) {
    const headingMatch = /^##\s+(.*)$/.exec(line)
    if (headingMatch) {
      const heading = headingMatch[1].trim()
      if (!(WORLD_HEADINGS as readonly string[]).includes(heading)) return null
      const headingIndex = WORLD_HEADINGS.indexOf(heading as (typeof WORLD_HEADINGS)[number])
      if (headingIndex <= lastHeadingIndex) return null
      flush()
      lastHeadingIndex = headingIndex
      sawHeading = true
      currentField = FIELD_OF_HEADING[heading as (typeof WORLD_HEADINGS)[number]]
      currentLines = []
      continue
    }
    if (!sawHeading) {
      if (line.trim() !== '') return null
      continue
    }
    if (currentField) currentLines.push(line)
  }
  flush()

  if (!sawHeading) return null
  return result
}
