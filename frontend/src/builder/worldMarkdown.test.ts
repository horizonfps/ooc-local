import { describe, expect, it } from 'vitest'
import { parseGuidedWorld, serializeGuidedWorld, WORLD_HEADINGS, type GuidedWorld } from './worldMarkdown'

describe('worldMarkdown', () => {
  it('round-trips the guided fields and the lore blocks', () => {
    const w: GuidedWorld = {
      universe: 'A city built on the ruins of the old world.',
      tone: 'Tense, quiet, no jokes.',
      rules: 'No magic. Guns jam a lot.',
      lore: [
        { title: 'Factions', body: 'Two factions fight over the last reservoir.' },
        { title: 'History', body: 'Find the missing engineer.' },
      ],
    }
    const md = serializeGuidedWorld(w)
    expect(parseGuidedWorld(md)).toEqual(w)
  })

  it('starts with the canonical order and only then the lore blocks', () => {
    const w: GuidedWorld = {
      universe: 'U',
      tone: 'T',
      rules: 'R',
      lore: [
        { title: 'Factions', body: 'F' },
        { title: 'History', body: 'H' },
      ],
    }
    const md = serializeGuidedWorld(w)
    expect(md).toBe('## Universe\n\nU\n\n## Tone\n\nT\n\n## Rules\n\nR\n\n## Factions\n\nF\n\n## History\n\nH')
  })

  it('omits empty sections and recovers them as empty strings', () => {
    const w: GuidedWorld = { universe: 'Only this.', tone: '', rules: '', lore: [] }
    const md = serializeGuidedWorld(w)
    expect(md).toBe('## Universe\n\nOnly this.')
    expect(parseGuidedWorld(md)).toEqual(w)
  })

  it('opens an old world.md with Conflict/Mission as two lore blocks, and round-trips byte for byte', () => {
    const md = '## Universe\n\nU\n\n## Tone\n\nT\n\n## Rules\n\nR\n\n## Conflict\n\nC\n\n## Mission\n\nM'
    const parsed = parseGuidedWorld(md)
    expect(parsed?.lore).toEqual([
      { title: 'Conflict', body: 'C' },
      { title: 'Mission', body: 'M' },
    ])
    expect(serializeGuidedWorld(parsed as GuidedWorld)).toBe(md)
  })

  it('returns null when a known heading follows a lore block', () => {
    const md = '## Universe\n\nU\n\n## Factions\n\nF\n\n## Tone\n\nT'
    expect(parseGuidedWorld(md)).toBeNull()
  })

  it('returns null when a heading is out of order', () => {
    const md = '## Tone\n\ntext\n\n## Universe\n\ntext2'
    expect(parseGuidedWorld(md)).toBeNull()
  })

  it('returns null when there is prose before the first heading', () => {
    const md = 'Some intro text\n\n## Universe\n\ntext'
    expect(parseGuidedWorld(md)).toBeNull()
  })

  it('round-trips an empty lore title as the "## " line, without leaking the body into the previous section', () => {
    const w: GuidedWorld = { universe: '', tone: '', rules: '', lore: [{ title: '', body: 'texto' }] }
    const md = serializeGuidedWorld(w)
    expect(md).toBe('## \n\ntexto')
    expect(parseGuidedWorld(md)).toEqual(w)
  })

  it('parses "##" without a trailing space as an empty title; "### Sub" and "# H1" stay as body', () => {
    const md = '##\n\ntext\n\n### Sub\n\n# H1'
    expect(parseGuidedWorld(md)).toEqual({
      universe: '',
      tone: '',
      rules: '',
      lore: [{ title: '', body: 'text\n\n### Sub\n\n# H1' }],
    })
  })

  it('lets duplicated lore titles survive the parse (the ban is a validation rule, not a parse rule)', () => {
    const md = '## Notas\n\nOne.\n\n## Notas\n\nTwo.'
    expect(parseGuidedWorld(md)?.lore).toEqual([
      { title: 'Notas', body: 'One.' },
      { title: 'Notas', body: 'Two.' },
    ])
  })

  it('preserves accented body and title text byte for byte', () => {
    const w: GuidedWorld = {
      universe: 'Uma cidade à beira do abismo, com árvores retorcidas e neblina.',
      tone: '',
      rules: '',
      lore: [{ title: 'História', body: 'Ração racionada, café raro.' }],
    }
    const md = serializeGuidedWorld(w)
    const parsed = parseGuidedWorld(md)
    expect(parsed?.universe).toBe(w.universe)
    expect(parsed?.lore).toEqual(w.lore)
  })

  it('exposes the canonical headings in order', () => {
    expect(WORLD_HEADINGS).toEqual(['Universe', 'Tone', 'Rules'])
  })

  it('parses empty and whitespace-only input as three empty guided fields and no lore', () => {
    const empty: GuidedWorld = { universe: '', tone: '', rules: '', lore: [] }
    expect(parseGuidedWorld('')).toEqual(empty)
    expect(parseGuidedWorld('   \n  ')).toEqual(empty)
    expect(serializeGuidedWorld(empty)).toBe('')
  })
})
