import { describe, expect, it } from 'vitest'
import type { BuilderDraft } from '../screens/BuilderEditorScreen'
import type { AchievementDoc, CommandDoc, LoreEntryDoc, StatDef } from '../api'
import { validateDraft } from './validate'
import { t } from '../i18n'

function loreEntry(overrides: Partial<LoreEntryDoc> = {}): LoreEntryDoc {
  return {
    title: 'O caderno',
    keywords: ['caderno'],
    body: 'Um caderno preto.',
    scope: 'keyword',
    priority: 0,
    enabled: true,
    ...overrides,
  }
}

function stat(overrides: Partial<StatDef> = {}): StatDef {
  return {
    id: 'rep',
    name: 'Reputação',
    icon: null,
    color: null,
    min: 0,
    max: 100,
    default: 40,
    description: null,
    levels: [],
    ...overrides,
  }
}

function command(overrides: Partial<CommandDoc> = {}): CommandDoc {
  return {
    name: 'fofoca',
    description: 'O que andam dizendo',
    prompt: 'Fora da narrativa, liste o que os NPCs estao comentando.',
    ...overrides,
  }
}

function achievement(overrides: Partial<AchievementDoc> = {}): AchievementDoc {
  return {
    id: 'primeiro-passo',
    name: 'Primeiro passo',
    type: 'achievement',
    rarity: 'common',
    hint: null,
    condition: 'O jogador cruzou o portão da escola.',
    min_turn: null,
    stat_gates: [],
    ...overrides,
  }
}

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
      allow_dynamic_stats: false,
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
    stats: [],
    lorebook: {},
    commands: [],
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

  it('does not flag a scenario with no stats at all', () => {
    const errors = validateDraft(draft({ stats: [] }))
    expect(errors.some((e) => e.tab === 'stats')).toBe(false)
  })

  it('flags a stat id outside the pattern, and allows underscores', () => {
    const errors = validateDraft(draft({ stats: [stat({ id: 'Vida Total' })] }))
    expect(
      errors.some(
        (e) => e.tab === 'stats' && e.field === 'stats.0.id' && e.message === t('builder.field.slugUnderscoreInvalid'),
      ),
    ).toBe(true)

    const okErrors = validateDraft(draft({ stats: [stat({ id: 'vida_total' })] }))
    expect(okErrors.some((e) => e.tab === 'stats' && e.field === 'stats.0.id')).toBe(false)
  })

  it('flags a starting value outside the min/max range', () => {
    const errors = validateDraft(draft({ stats: [stat({ min: 0, max: 10, default: 50 })] }))
    expect(
      errors.some(
        (e) => e.tab === 'stats' && e.field === 'stats.0.default' && e.message === t('builder.validate.statDefaultRange', { min: 0, max: 10 }),
      ),
    ).toBe(true)
  })

  it('silences the derived rules when the range itself is broken', () => {
    const errors = validateDraft(draft({ stats: [stat({ min: 10, max: 5, default: 7 })] }))
    expect(errors.some((e) => e.tab === 'stats' && e.field === 'stats.0.max')).toBe(true)
    expect(errors.some((e) => e.tab === 'stats' && e.field === 'stats.0.default')).toBe(false)
  })

  it('flags levels out of ascending order', () => {
    const errors = validateDraft(
      draft({ stats: [stat({ levels: [{ from: 40, text: 'a' }, { from: 40, text: 'b' }] })] }),
    )
    expect(
      errors.some(
        (e) => e.tab === 'stats' && e.field === 'stats.0.levels.1.from' && e.message === t('builder.validate.levelFromOrder'),
      ),
    ).toBe(true)
    expect(errors.some((e) => e.tab === 'stats' && e.field === 'stats.0.levels.0.from')).toBe(false)
  })

  it('flags an empty level text', () => {
    const errors = validateDraft(draft({ stats: [stat({ levels: [{ from: 0, text: '' }] })] }))
    expect(
      errors.some(
        (e) => e.tab === 'stats' && e.field === 'stats.0.levels.0.text' && e.message === t('builder.field.required'),
      ),
    ).toBe(true)
  })

  it('composes the error label from the stat name, falling back to the id', () => {
    const named = validateDraft(draft({ stats: [stat({ name: 'Reputação', icon: 'too-long' })] }))
    expect(named.find((e) => e.tab === 'stats' && e.field === 'stats.0.icon')?.label.startsWith('Reputação')).toBe(true)

    const unnamed = validateDraft(draft({ stats: [stat({ name: '', id: 'rep' })] }))
    expect(unnamed.find((e) => e.tab === 'stats' && e.field === 'stats.0.name')?.label.startsWith('rep')).toBe(true)
  })

  it('does not flag a delta cap and dynamic stat limit within range', () => {
    const errors = validateDraft(
      draft({
        stats: [stat({ min: 0, max: 100, max_delta: 100 })],
        meta: { ...draft().meta, allow_dynamic_stats: true, max_dynamic_stats: 12 },
      }),
    )
    expect(errors.some((e) => e.field === 'stats.0.max_delta')).toBe(false)
    expect(errors.some((e) => e.field === 'meta.max_dynamic_stats')).toBe(false)
  })

  it('does not flag an absent or null delta cap', () => {
    const absent = validateDraft(draft({ stats: [stat({ min: 0, max: 100 })] }))
    expect(absent.some((e) => e.field === 'stats.0.max_delta')).toBe(false)

    const explicitNull = validateDraft(draft({ stats: [stat({ min: 0, max: 100, max_delta: null })] }))
    expect(explicitNull.some((e) => e.field === 'stats.0.max_delta')).toBe(false)
  })

  it('flags a delta cap of zero', () => {
    const errors = validateDraft(draft({ stats: [stat({ min: 0, max: 100, max_delta: 0 })] }))
    expect(errors.filter((e) => e.field === 'stats.0.max_delta')).toHaveLength(1)
    expect(errors.find((e) => e.field === 'stats.0.max_delta')?.tab).toBe('stats')
  })

  it('flags a delta cap larger than the stat range', () => {
    const errors = validateDraft(draft({ stats: [stat({ min: 0, max: 100, max_delta: 500 })] }))
    expect(
      errors.some(
        (e) => e.field === 'stats.0.max_delta' && e.message === t('builder.validate.maxDeltaSpan', { span: 100 }),
      ),
    ).toBe(true)
  })

  it('does not stack a delta cap span error when the range itself is broken', () => {
    const errors = validateDraft(draft({ stats: [stat({ min: 50, max: 10, max_delta: 500 })] }))
    expect(errors.filter((e) => e.field === 'stats.0.max_delta')).toHaveLength(0)
    expect(errors.some((e) => e.field === 'stats.0.max')).toBe(true)
  })

  it('flags a dynamic stats limit of zero only when the toggle is on', () => {
    const on = validateDraft(draft({ meta: { ...draft().meta, allow_dynamic_stats: true, max_dynamic_stats: 0 } }))
    expect(on.filter((e) => e.field === 'meta.max_dynamic_stats')).toHaveLength(1)
    expect(on.find((e) => e.field === 'meta.max_dynamic_stats')?.tab).toBe('stats')

    const off = validateDraft(draft({ meta: { ...draft().meta, allow_dynamic_stats: false, max_dynamic_stats: 0 } }))
    expect(off.some((e) => e.field === 'meta.max_dynamic_stats')).toBe(false)
  })

  it('does not complain about an empty lorebook', () => {
    const errors = validateDraft(draft({ lorebook: {} }))
    expect(errors.some((e) => e.tab === 'lorebook')).toBe(false)
  })

  it('flags a keyword-scoped entry with no keyword', () => {
    const errors = validateDraft(draft({ lorebook: { caderno: loreEntry({ keywords: [] }) } }))
    expect(
      errors.some(
        (e) =>
          e.tab === 'lorebook' &&
          e.field === 'lorebook.caderno.keywords' &&
          e.message === t('builder.validate.loreKeywordRequired'),
      ),
    ).toBe(true)
  })

  it('does not require a keyword on an always-scoped entry', () => {
    const errors = validateDraft(draft({ lorebook: { caderno: loreEntry({ keywords: [], scope: 'always' }) } }))
    expect(errors.some((e) => e.tab === 'lorebook' && e.field === 'lorebook.caderno.keywords')).toBe(false)
  })

  it('flags an empty title', () => {
    const errors = validateDraft(draft({ lorebook: { caderno: loreEntry({ title: '' }) } }))
    expect(
      errors.some(
        (e) => e.tab === 'lorebook' && e.field === 'lorebook.caderno.title' && e.message === t('builder.field.required'),
      ),
    ).toBe(true)
  })

  it('flags an id outside [a-z0-9-]', () => {
    const errors = validateDraft(draft({ lorebook: { 'Caderno Preto': loreEntry() } }))
    expect(
      errors.some(
        (e) => e.tab === 'lorebook' && e.field === 'lorebook.Caderno Preto' && e.message === t('builder.field.slugInvalid'),
      ),
    ).toBe(true)
  })

  it('accepts an empty body', () => {
    const errors = validateDraft(draft({ lorebook: { caderno: loreEntry({ body: '' }) } }))
    expect(errors.some((e) => e.tab === 'lorebook' && e.field.startsWith('lorebook.caderno'))).toBe(false)
  })

  it('does not complain about a scenario with no commands', () => {
    const errors = validateDraft(draft({ commands: [] }))
    expect(errors.some((e) => e.tab === 'commands')).toBe(false)
  })

  it('flags a command name outside the pattern, and allows underscores', () => {
    const errors = validateDraft(draft({ commands: [command({ name: 'Fofoca' })] }))
    expect(
      errors.some(
        (e) => e.tab === 'commands' && e.field === 'commands.0.name' && e.message === t('builder.field.slugUnderscoreInvalid'),
      ),
    ).toBe(true)

    const okErrors = validateDraft(draft({ commands: [command({ name: 'fofoca_2' })] }))
    expect(okErrors.some((e) => e.tab === 'commands' && e.field === 'commands.0.name')).toBe(false)
  })

  it('flags a duplicated name only from the second command onward', () => {
    const errors = validateDraft(draft({ commands: [command({ name: 'fofoca' }), command({ name: 'fofoca' })] }))
    expect(errors.some((e) => e.tab === 'commands' && e.field === 'commands.0.name')).toBe(false)
    expect(
      errors.some(
        (e) => e.tab === 'commands' && e.field === 'commands.1.name' && e.message === t('builder.field.slugTaken', { slug: 'fofoca' }),
      ),
    ).toBe(true)
  })

  it('flags an empty prompt and accepts an empty description', () => {
    const errors = validateDraft(draft({ commands: [command({ description: '', prompt: '' })] }))
    expect(
      errors.some((e) => e.tab === 'commands' && e.field === 'commands.0.prompt' && e.message === t('builder.field.required')),
    ).toBe(true)
    expect(errors.some((e) => e.tab === 'commands' && e.field === 'commands.0.description')).toBe(false)
  })

  it('does not complain about a start with no achievements', () => {
    const errors = validateDraft(draft())
    expect(errors.some((e) => e.tab === 'achievements')).toBe(false)
  })

  it('flags an empty achievement id with a single error, not also a duplicate error', () => {
    const errors = validateDraft(
      draft({
        starts: {
          default: { ...draft().starts.default, achievements: [achievement({ id: '' }), achievement({ id: '' })] },
        },
      }),
    )
    const idErrors = errors.filter((e) => e.tab === 'achievements' && e.field === 'achievements.default.0.id')
    expect(idErrors).toHaveLength(1)
    expect(idErrors[0].message).toBe(t('builder.field.required'))
  })

  it('flags an achievement id outside the pattern', () => {
    const errors = validateDraft(
      draft({ starts: { default: { ...draft().starts.default, achievements: [achievement({ id: 'Primeiro_Passo' })] } } }),
    )
    expect(
      errors.some(
        (e) => e.tab === 'achievements' && e.field === 'achievements.default.0.id' && e.message === t('builder.field.slugInvalid'),
      ),
    ).toBe(true)
  })

  it('flags a duplicated achievement id within the same start, but not across starts', () => {
    const withDupe = validateDraft(
      draft({
        starts: {
          default: {
            ...draft().starts.default,
            achievements: [achievement({ id: 'a1' }), achievement({ id: 'a1' })],
          },
        },
      }),
    )
    expect(
      withDupe.some(
        (e) =>
          e.tab === 'achievements' &&
          e.field === 'achievements.default.1.id' &&
          e.message === t('builder.validate.achievementIdTaken', { slug: 'a1' }),
      ),
    ).toBe(true)

    const acrossStarts = validateDraft(
      draft({
        starts: {
          default: { ...draft().starts.default, achievements: [achievement({ id: 'a1' })] },
          other: { ...draft().starts.default, id: 'other', achievements: [achievement({ id: 'a1' })] },
        },
      }),
    )
    expect(acrossStarts.some((e) => e.tab === 'achievements')).toBe(false)
  })

  it('flags an empty name and an empty condition', () => {
    const errors = validateDraft(
      draft({
        starts: {
          default: { ...draft().starts.default, achievements: [achievement({ name: '', condition: '' })] },
        },
      }),
    )
    expect(
      errors.some((e) => e.tab === 'achievements' && e.field === 'achievements.default.0.name' && e.message === t('builder.field.required')),
    ).toBe(true)
    expect(
      errors.some(
        (e) => e.tab === 'achievements' && e.field === 'achievements.default.0.condition' && e.message === t('builder.field.required'),
      ),
    ).toBe(true)
  })

  it('flags min_turn 0 and accepts null or absent', () => {
    const zeroErrors = validateDraft(
      draft({ starts: { default: { ...draft().starts.default, achievements: [achievement({ min_turn: 0 })] } } }),
    )
    expect(
      zeroErrors.some(
        (e) =>
          e.tab === 'achievements' &&
          e.field === 'achievements.default.0.min_turn' &&
          e.message === t('builder.validate.minTurnPositive'),
      ),
    ).toBe(true)

    const nullErrors = validateDraft(
      draft({ starts: { default: { ...draft().starts.default, achievements: [achievement({ min_turn: null })] } } }),
    )
    expect(nullErrors.some((e) => e.tab === 'achievements' && e.field === 'achievements.default.0.min_turn')).toBe(false)

    const absentErrors = validateDraft(draft({ starts: { default: { ...draft().starts.default, achievements: undefined } } }))
    expect(absentErrors.some((e) => e.tab === 'achievements')).toBe(false)
  })

  it('flags a gate pointing to a stat that does not exist', () => {
    const errors = validateDraft(
      draft({
        stats: [],
        starts: {
          default: {
            ...draft().starts.default,
            achievements: [achievement({ stat_gates: [{ id: 'rep', at_least: 5 }] })],
          },
        },
      }),
    )
    const gateErrors = errors.filter((e) => e.tab === 'achievements' && e.field === 'achievements.default.0.stat_gates.0.id')
    expect(gateErrors).toHaveLength(1)
    expect(gateErrors[0].message).toBe(t('builder.validate.gateUnknownStat', { id: 'rep' }))
  })

  it('flags two gates for the same stat on the same entry', () => {
    const errors = validateDraft(
      draft({
        stats: [stat({ id: 'rep' })],
        starts: {
          default: {
            ...draft().starts.default,
            achievements: [
              achievement({
                stat_gates: [
                  { id: 'rep', at_least: 5 },
                  { id: 'rep', at_least: 10 },
                ],
              }),
            ],
          },
        },
      }),
    )
    expect(errors.some((e) => e.field === 'achievements.default.0.stat_gates.0.id')).toBe(false)
    const dupeErrors = errors.filter((e) => e.field === 'achievements.default.0.stat_gates.1.id')
    expect(dupeErrors).toHaveLength(1)
    expect(dupeErrors[0].message).toBe(t('builder.validate.gateDuplicate', { id: 'rep' }))
  })

  it('does not stack an unknown-stat error with a duplicate error on the same line', () => {
    const errors = validateDraft(
      draft({
        stats: [],
        starts: {
          default: {
            ...draft().starts.default,
            achievements: [
              achievement({
                stat_gates: [
                  { id: 'rep', at_least: 5 },
                  { id: 'rep', at_least: 10 },
                ],
              }),
            ],
          },
        },
      }),
    )
    const line1Errors = errors.filter((e) => e.field === 'achievements.default.0.stat_gates.1.id')
    expect(line1Errors).toHaveLength(1)
    expect(line1Errors[0].message).toBe(t('builder.validate.gateUnknownStat', { id: 'rep' }))
  })

  it('does not flag two different achievements gating the same stat', () => {
    const errors = validateDraft(
      draft({
        stats: [stat({ id: 'rep' })],
        starts: {
          default: {
            ...draft().starts.default,
            achievements: [
              achievement({ id: 'a1', stat_gates: [{ id: 'rep', at_least: 5 }] }),
              achievement({ id: 'a2', stat_gates: [{ id: 'rep', at_least: 10 }] }),
            ],
          },
        },
      }),
    )
    expect(errors.some((e) => e.tab === 'achievements')).toBe(false)
  })
})
