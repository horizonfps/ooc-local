import { describe, expect, it } from 'vitest'
import { parseGuidedWorld, serializeGuidedWorld, WORLD_HEADINGS, type GuidedWorld } from './worldMarkdown'

describe('worldMarkdown', () => {
  it('round-trips all five fields', () => {
    const w: GuidedWorld = {
      universe: 'A city built on the ruins of the old world.',
      tone: 'Tense, quiet, no jokes.',
      rules: 'No magic. Guns jam a lot.',
      conflict: 'Two factions fight over the last reservoir.',
      mission: 'Find the missing engineer.',
    }
    const md = serializeGuidedWorld(w)
    expect(parseGuidedWorld(md)).toEqual(w)
  })

  it('omits empty sections and recovers them as empty strings', () => {
    const w: GuidedWorld = { universe: 'Only this.', tone: '', rules: '', conflict: '', mission: '' }
    const md = serializeGuidedWorld(w)
    expect(md).toBe('## Universe\n\nOnly this.')
    expect(parseGuidedWorld(md)).toEqual(w)
  })

  it('returns null when a heading is out of order', () => {
    const md = '## Tone\n\ntext\n\n## Universe\n\ntext2'
    expect(parseGuidedWorld(md)).toBeNull()
  })

  it('returns null when there is prose before the first heading', () => {
    const md = 'Some intro text\n\n## Universe\n\ntext'
    expect(parseGuidedWorld(md)).toBeNull()
  })

  it('returns null on an unknown heading', () => {
    const md = '## Universe\n\ntext\n\n## Extra\n\nmore'
    expect(parseGuidedWorld(md)).toBeNull()
  })

  it('preserves accented body text byte for byte', () => {
    const w: GuidedWorld = {
      universe: 'Uma cidade à beira do abismo, com árvores retorcidas e neblina.',
      tone: '',
      rules: '',
      conflict: '',
      mission: '',
    }
    const md = serializeGuidedWorld(w)
    expect(parseGuidedWorld(md)?.universe).toBe(w.universe)
  })

  it('exposes the canonical headings in order', () => {
    expect(WORLD_HEADINGS).toEqual(['Universe', 'Tone', 'Rules', 'Conflict', 'Mission'])
  })

  it('parses empty and whitespace-only input as five empty guided fields', () => {
    const empty: GuidedWorld = { universe: '', tone: '', rules: '', conflict: '', mission: '' }
    expect(parseGuidedWorld('')).toEqual(empty)
    expect(parseGuidedWorld('   \n  ')).toEqual(empty)
    expect(serializeGuidedWorld(empty)).toBe('')
  })
})
