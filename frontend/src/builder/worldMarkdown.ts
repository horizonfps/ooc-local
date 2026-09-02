export type LoreBlock = { title: string; body: string }
export type GuidedWorld = { universe: string; tone: string; rules: string; lore: LoreBlock[] }

export const WORLD_HEADINGS = ['Universe', 'Tone', 'Rules'] as const

const FIELD_OF_HEADING: Record<(typeof WORLD_HEADINGS)[number], Exclude<keyof GuidedWorld, 'lore'>> = {
  Universe: 'universe',
  Tone: 'tone',
  Rules: 'rules',
}

export function serializeGuidedWorld(w: GuidedWorld): string {
  const knownSections = WORLD_HEADINGS.map((heading) => [heading, w[FIELD_OF_HEADING[heading]].trim()] as const)
    .filter(([, text]) => text !== '')
    .map(([heading, text]) => `## ${heading}\n\n${text}`)

  const loreSections = w.lore.map((block) => {
    const title = block.title.trim()
    const body = block.body.trim()
    return body === '' ? `## ${title}` : `## ${title}\n\n${body}`
  })

  return [...knownSections, ...loreSections].join('\n\n')
}

export function parseGuidedWorld(md: string): GuidedWorld | null {
  if (!md.trim()) return { universe: '', tone: '', rules: '', lore: [] }

  const lines = md.split('\n')
  const result: GuidedWorld = { universe: '', tone: '', rules: '', lore: [] }
  const lore: LoreBlock[] = []

  type Section = { kind: 'known'; field: Exclude<keyof GuidedWorld, 'lore'> } | { kind: 'lore'; index: number }
  let current: Section | null = null
  let currentLines: string[] = []
  let lastHeadingIndex = -1
  let sawHeading = false
  let inLore = false

  function flush() {
    if (!current) return
    const body = currentLines.join('\n').trim()
    if (current.kind === 'known') result[current.field] = body
    else lore[current.index].body = body
  }

  for (const line of lines) {
    const headingMatch = /^##(?:\s+(.*))?\s*$/.exec(line)
    if (headingMatch) {
      const heading = (headingMatch[1] ?? '').trim()
      const isKnown = (WORLD_HEADINGS as readonly string[]).includes(heading)
      flush()
      sawHeading = true
      if (isKnown) {
        if (inLore) return null
        const headingIndex = WORLD_HEADINGS.indexOf(heading as (typeof WORLD_HEADINGS)[number])
        if (headingIndex <= lastHeadingIndex) return null
        lastHeadingIndex = headingIndex
        current = { kind: 'known', field: FIELD_OF_HEADING[heading as (typeof WORLD_HEADINGS)[number]] }
      } else {
        inLore = true
        lore.push({ title: heading, body: '' })
        current = { kind: 'lore', index: lore.length - 1 }
      }
      currentLines = []
      continue
    }
    if (!sawHeading) {
      if (line.trim() !== '') return null
      continue
    }
    currentLines.push(line)
  }
  flush()

  if (!sawHeading) return null
  result.lore = lore
  return result
}
