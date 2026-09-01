import { describe, expect, it } from 'vitest'
import type { BuilderDraft } from '../screens/BuilderEditorScreen'
import { validateDraft } from './validate'
import { t } from '../i18n'

function draft(overrides: Partial<BuilderDraft> = {}): BuilderDraft {
  return {
    meta: {
      name: 'Test scenario',
      tagline: null,
      description: null,
      locale: 'en',
      tags: [],
      default_start: 'default',
      world_mode: 'guided',
    },
    world: '## Universe\n\nA quiet town.',
    starts: {
      default: {
        id: 'default',
        name: 'Default start',
        prologue: 'It begins in a quiet town.',
        opening_scene: 'The square at dusk.',
        play_guide: null,
        suggestions: [],
        hud: { location: 'Town square', time: '08:00', weather: 'clear' },
        characters: ['ally'],
      },
    },
    characters: {
      ally: {
        name: 'Ally',
        role: 'A friendly local',
        appearance: 'Short and freckled.',
        personality: 'Helpful, curious.',
        voice: 'Warm, chatty.',
        mind: { feeling: 'Content', goal: 'Help the player settle in', opinion_of_player: null, secret_plan: null },
        sprite: null,
        power_tier: null,
        emotions: ['default'],
      },
    },
    ...overrides,
  }
}

describe('validateDraft', () => {
  it('returns no errors for a coherent document', () => {
    expect(validateDraft(draft())).toEqual([])
  })

  it('flags a default_start that does not exist among the starts', () => {
    const errors = validateDraft(draft({ meta: { ...draft().meta, default_start: 'missing' } }))
    expect(errors.some((e) => e.tab === 'starts' && e.field === 'default_start')).toBe(true)
  })

  it('flags a start referencing a character id that is not in the document', () => {
    const base = draft()
    const errors = validateDraft({
      ...base,
      starts: { default: { ...base.starts.default, characters: ['ghost'] } },
    })
    expect(errors.some((e) => e.tab === 'starts' && e.message.includes('ghost'))).toBe(true)
  })

  it('flags a start key that does not match [a-z0-9-]+', () => {
    const base = draft()
    const errors = validateDraft({
      ...base,
      meta: { ...base.meta, default_start: 'Start Um' },
      starts: { 'Start Um': { ...base.starts.default, id: 'Start Um', characters: [] } },
    })
    expect(errors.some((e) => e.tab === 'starts' && e.field === 'starts.Start Um')).toBe(true)
  })

  it('flags an empty starts map', () => {
    const errors = validateDraft(draft({ starts: {} }))
    expect(errors.some((e) => e.tab === 'starts' && e.field === 'starts')).toBe(true)
  })

  it('does not flag a missing universe when guided world_mode holds hand-written, non-canonical text', () => {
    const errors = validateDraft(draft({ world: 'Just some free-form prose, no headings.' }))
    expect(errors.some((e) => e.tab === 'world')).toBe(false)
  })

  it('flags "}} text {{" as an unbalanced variable', () => {
    const errors = validateDraft(draft({ world: '## Universe\n\n}} text {{' }))
    expect(errors.some((e) => e.tab === 'world' && e.message === t('builder.world.variables.unbalanced'))).toBe(true)
  })
})
