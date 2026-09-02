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
        conflict: null,
        mission: null,
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

  it('flags an empty lore block title and blocks saving', () => {
    const errors = validateDraft(draft({ world: '## Universe\n\nA quiet town.\n\n## \n\nSome written body.' }))
    expect(
      errors.some(
        (e) => e.tab === 'world' && e.field === 'world.lore.0.title' && e.message === t('builder.world.lore.title.required'),
      ),
    ).toBe(true)
  })

  it('does not flag an oversized world.md as an error', () => {
    const errors = validateDraft(draft({ world: '## Universe\n\n' + 'x'.repeat(20000) }))
    expect(errors.some((e) => e.tab === 'world')).toBe(false)
  })

  it('flags a duplicated lore block title only on the second occurrence', () => {
    const errors = validateDraft(
      draft({ world: '## Universe\n\nA quiet town.\n\n## Notas\n\nOne.\n\n## notas\n\nTwo.' }),
    )
    expect(errors.some((e) => e.tab === 'world' && e.field === 'world.lore.0.title')).toBe(false)
    expect(
      errors.some(
        (e) => e.tab === 'world' && e.field === 'world.lore.1.title' && e.message === t('builder.world.lore.title.duplicate'),
      ),
    ).toBe(true)
  })

  it('does not validate lore blocks in custom mode', () => {
    const errors = validateDraft(
      draft({
        meta: { ...draft().meta, world_mode: 'custom' },
        world: '## Universe\n\nA quiet town.\n\n## \n\nBody.',
      }),
    )
    expect(errors.some((e) => e.tab === 'world' && e.field.startsWith('world.lore.'))).toBe(false)
  })

  it('does not validate lore blocks when the world.md falls back to custom mode', () => {
    const errors = validateDraft(draft({ world: 'Just some free-form prose, no headings.' }))
    expect(errors.some((e) => e.tab === 'world' && e.field.startsWith('world.lore.'))).toBe(false)
  })

  it('still requires the universe with lore blocks present', () => {
    const errors = validateDraft(draft({ world: '## Rules\n\nNo magic.\n\n## Factions\n\nTwo of them.' }))
    expect(errors.some((e) => e.tab === 'world' && e.field === 'universe')).toBe(true)
  })

  it('does not require conflict or mission on a start', () => {
    const errors = validateDraft(draft())
    expect(errors.some((e) => e.tab === 'starts' && e.field.endsWith('.conflict'))).toBe(false)
    expect(errors.some((e) => e.tab === 'starts' && e.field.endsWith('.mission'))).toBe(false)
  })

  it('does not flag a long conflict text as an error', () => {
    const base = draft()
    const errors = validateDraft({
      ...base,
      starts: { default: { ...base.starts.default, conflict: 'x'.repeat(5000) } },
    })
    expect(errors).toEqual([])
  })
})
