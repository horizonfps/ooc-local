import { describe, expect, it } from 'vitest'
import type { BuilderDraft } from '../screens/BuilderEditorScreen'
import { validateDraft } from './validate'

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
    world: '',
    starts: {
      default: {
        id: 'default',
        name: 'Default start',
        prologue: '',
        opening_scene: '',
        play_guide: null,
        suggestions: [],
        hud: { location: '', time: '08:00', weather: 'clear' },
        characters: ['ally'],
      },
    },
    characters: {
      ally: {
        name: 'Ally',
        role: '',
        appearance: '',
        personality: '',
        voice: '',
        mind: { feeling: '', goal: '', opinion_of_player: null, secret_plan: null },
        sprite: null,
        anchor: false,
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
})
