import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { AchievementsTab } from './AchievementsTab'
import { validateDraft } from '../../builder/validate'
import type { BuilderDraft } from '../../screens/BuilderEditorScreen'
import type { AchievementDoc, StartDoc, StatDef, StatGateDoc } from '../../api'
import { t } from '../../i18n'

function stat(overrides: Partial<StatDef> = {}): StatDef {
  return {
    id: 'reputacao',
    name: 'Reputação',
    icon: null,
    color: null,
    min: -100,
    max: 100,
    default: 0,
    description: null,
    levels: [],
    max_delta: null,
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
    condition: 'O jogador cruzou o portão.',
    min_turn: null,
    stat_gates: [],
    ...overrides,
  }
}

function start(overrides: Partial<StartDoc> = {}): StartDoc {
  return {
    id: 'default',
    name: 'Default start',
    prologue: 'It begins.',
    opening_scene: 'A hallway.',
    conflict: null,
    mission: null,
    play_guide: null,
    suggestions: [],
    hud: { location: 'Hallway', time: '08:00', weather: 'clear' },
    characters: null,
    ...overrides,
  }
}

function baseDraft(starts: Record<string, StartDoc> = { default: start() }, stats: StatDef[] = []): BuilderDraft {
  return {
    meta: {
      name: 'The School',
      tagline: null,
      description: null,
      locale: 'en',
      tags: [],
      default_start: 'default',
      world_mode: 'guided',
      allow_dynamic_stats: false,
    },
    world: 'A dusty old school.',
    starts,
    characters: {},
    stats,
    lorebook: {},
    commands: [],
  }
}

function Harness(props: { initial: BuilderDraft }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return (
    <>
      <AchievementsTab scenarioId="school" draft={draft} onChange={setDraft} errors={errors} goToTab={() => {}} />
      <pre data-testid="achievements-debug">{JSON.stringify(draft.starts)}</pre>
    </>
  )
}

function startsDebug(): Record<string, StartDoc> {
  return JSON.parse(screen.getByTestId('achievements-debug').textContent ?? '{}')
}

describe('AchievementsTab', () => {
  it('creates, edits and reflects fields in the draft', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft({ default: start({ achievements: [] }) })} />)

    await user.click(screen.getByRole('button', { name: t('builder.achievements.create') }))
    fireEvent.change(screen.getByLabelText(t('builder.achievements.name')), { target: { value: 'First step' } })
    fireEvent.click(screen.getByLabelText(t('builder.achievements.type.ending')))
    fireEvent.change(screen.getByLabelText(t('builder.achievements.rarity')), { target: { value: 'rare' } })
    fireEvent.change(screen.getByLabelText(t('builder.achievements.condition')), { target: { value: 'Something happened.' } })

    const entries = startsDebug().default.achievements
    expect(entries).toHaveLength(1)
    expect(entries?.[0]).toMatchObject({
      id: 'conquista-1',
      name: 'First step',
      type: 'ending',
      rarity: 'rare',
      condition: 'Something happened.',
      stat_gates: [],
    })
  })

  it('announces create, select and remove', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={baseDraft({ default: start({ achievements: [achievement({ id: 'a1', name: 'a' }), achievement({ id: 'a2', name: 'b' })] }) })}
      />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.achievements.create') }))
    expect(screen.getByText(t('builder.achievements.added', { name: 'conquista-1' }))).toBeInTheDocument()

    await user.click(document.getElementById('builder-achievements-listItem-1') as HTMLElement)
    expect(screen.getByText(t('builder.detail.selected', { name: 'b' }))).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: t('builder.achievements.remove.title', { name: 'b' }) }))
    expect(screen.getByText(t('builder.achievements.removed', { name: 'b' }))).toBeInTheDocument()
  })

  it('switching start swaps the list and resets selection', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={baseDraft({
          default: start({ achievements: [achievement({ id: 'a1', name: 'From default' })] }),
          other: start({ id: 'other', name: 'Other start', achievements: [achievement({ id: 'b1', name: 'From other' })] }),
        })}
      />,
    )

    expect(screen.getByText('From default')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText(t('builder.achievements.startLabel')), 'other')

    expect(screen.getByText('From other')).toBeInTheDocument()
    expect(screen.queryByText('From default')).toBeNull()
  })

  it('minimum turn: empty is null, 7 is 7', () => {
    render(<Harness initial={baseDraft({ default: start({ achievements: [achievement()] }) })} />)

    const minTurnInput = screen.getByLabelText(t('builder.achievements.minTurn'))
    fireEvent.change(minTurnInput, { target: { value: '7' } })
    expect(startsDebug().default.achievements?.[0].min_turn).toBe(7)

    fireEvent.change(minTurnInput, { target: { value: '' } })
    expect(startsDebug().default.achievements?.[0].min_turn).toBeNull()
  })

  it('empty hint becomes null', () => {
    render(<Harness initial={baseDraft({ default: start({ achievements: [achievement({ hint: 'Look around' })] }) })} />)

    const hintInput = screen.getByLabelText(t('builder.achievements.hint'))
    fireEvent.change(hintInput, { target: { value: '' } })
    fireEvent.blur(hintInput)
    expect(startsDebug().default.achievements?.[0].hint).toBeNull()
  })

  it('editing the name preserves loaded stat_gates', () => {
    const gates: StatGateDoc[] = [{ id: 'rep', at_least: 5 }]
    render(<Harness initial={baseDraft({ default: start({ achievements: [achievement({ stat_gates: gates })] }) })} />)

    fireEvent.change(screen.getByLabelText(t('builder.achievements.name')), { target: { value: 'Changed' } })

    expect(startsDebug().default.achievements?.[0].stat_gates).toEqual(gates)
  })

  it('adds a gate, edits its stat and value, then removes it', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={baseDraft({ default: start({ achievements: [achievement()] }) }, [stat(), stat({ id: 'coragem', name: 'Coragem' })])}
      />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.achievements.gates.add') }))
    let gate = startsDebug().default.achievements?.[0].stat_gates?.[0]
    expect(gate).toEqual({ id: 'reputacao', at_least: 0 })
    await waitFor(() => {
      expect(document.getElementById('builder-field-achievements.default.0.stat_gates.0.id')).toBe(document.activeElement)
    })

    const select = screen.getByLabelText(t('builder.achievements.gates.stat')) as HTMLSelectElement
    await user.selectOptions(select, 'coragem')
    gate = startsDebug().default.achievements?.[0].stat_gates?.[0]
    expect(gate?.id).toBe('coragem')

    const atLeast = screen.getByLabelText(t('builder.achievements.gates.atLeast'))
    fireEvent.change(atLeast, { target: { value: '50' } })
    gate = startsDebug().default.achievements?.[0].stat_gates?.[0]
    expect(gate?.at_least).toBe(50)

    await user.click(screen.getByRole('button', { name: t('builder.achievements.gates.remove.title', { id: 'coragem' }) }))
    expect(startsDebug().default.achievements?.[0].stat_gates).toEqual([])
    await waitFor(() => {
      expect(screen.getByRole('button', { name: t('builder.achievements.gates.add') })).toBe(document.activeElement)
    })
  })

  it('supports two gates on the same entry', () => {
    const gates: StatGateDoc[] = [
      { id: 'reputacao', at_least: 10 },
      { id: 'coragem', at_least: -5 },
    ]
    render(
      <Harness
        initial={baseDraft({ default: start({ achievements: [achievement({ stat_gates: gates })] }) }, [
          stat(),
          stat({ id: 'coragem', name: 'Coragem' }),
        ])}
      />,
    )

    expect(startsDebug().default.achievements?.[0].stat_gates).toEqual(gates)
    const atLeastInputs = screen.getAllByLabelText(t('builder.achievements.gates.atLeast'))
    expect(atLeastInputs).toHaveLength(2)
  })

  it('accepts a negative at_least value', () => {
    render(
      <Harness
        initial={baseDraft({ default: start({ achievements: [achievement({ stat_gates: [{ id: 'reputacao', at_least: 0 }] })] }) }, [
          stat(),
        ])}
      />,
    )

    const atLeast = screen.getByLabelText(t('builder.achievements.gates.atLeast'))
    fireEvent.change(atLeast, { target: { value: '-5' } })
    expect(startsDebug().default.achievements?.[0].stat_gates?.[0].at_least).toBe(-5)
  })

  it('removing a middle gate focuses the row that took its place, and removing the last focuses add', async () => {
    const user = userEvent.setup()
    const gates: StatGateDoc[] = [
      { id: 'reputacao', at_least: 1 },
      { id: 'coragem', at_least: 2 },
    ]
    render(
      <Harness
        initial={baseDraft({ default: start({ achievements: [achievement({ stat_gates: gates })] }) }, [
          stat(),
          stat({ id: 'coragem', name: 'Coragem' }),
        ])}
      />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.achievements.gates.remove.title', { id: 'reputacao' }) }))
    await waitFor(() => {
      expect(document.getElementById('builder-field-achievements.default.0.stat_gates.0.id')).toBe(document.activeElement)
    })

    await user.click(screen.getByRole('button', { name: t('builder.achievements.gates.remove.title', { id: 'coragem' }) }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: t('builder.achievements.gates.add') })).toBe(document.activeElement)
    })
  })

  it('scenario without stats disables the add button, shows the hint, and still renders an orphan gate', () => {
    const gates: StatGateDoc[] = [{ id: 'rep', at_least: 5 }]
    render(<Harness initial={baseDraft({ default: start({ achievements: [achievement({ stat_gates: gates })] }) }, [])} />)

    expect(screen.getByRole('button', { name: t('builder.achievements.gates.add') })).toBeDisabled()
    expect(screen.getByText(t('builder.achievements.gates.noStats'))).toBeInTheDocument()
    const select = screen.getByLabelText(t('builder.achievements.gates.stat')) as HTMLSelectElement
    expect(select.value).toBe('rep')
  })

  it('pending text for a gate in one start is not shared with the same position in another start', async () => {
    render(
      <Harness
        initial={baseDraft(
          {
            default: start({ achievements: [achievement({ id: 'a1', stat_gates: [{ id: 'reputacao', at_least: 1 }] })] }),
            other: start({
              id: 'other',
              name: 'Other start',
              achievements: [achievement({ id: 'b1', stat_gates: [{ id: 'reputacao', at_least: 2 }] })],
            }),
          },
          [stat()],
        )}
      />,
    )

    const atLeast = screen.getByLabelText(t('builder.achievements.gates.atLeast'))
    fireEvent.change(atLeast, { target: { value: 'abc' } })
    expect(screen.getByText(t('builder.validate.integerRequired'))).toBeInTheDocument()

    await userEvent.setup().selectOptions(screen.getByLabelText(t('builder.achievements.startLabel')), 'other')
    expect(screen.queryByText(t('builder.validate.integerRequired'))).not.toBeInTheDocument()
    const otherAtLeast = screen.getByLabelText(t('builder.achievements.gates.atLeast')) as HTMLInputElement
    expect(otherAtLeast.value).toBe('2')
  })

  it('clearing at_least renders integerRequired from the component and keeps the draft unchanged', () => {
    render(
      <Harness
        initial={baseDraft({ default: start({ achievements: [achievement({ stat_gates: [{ id: 'reputacao', at_least: 5 }] })] }) }, [
          stat(),
        ])}
      />,
    )

    const atLeast = screen.getByLabelText(t('builder.achievements.gates.atLeast'))
    fireEvent.change(atLeast, { target: { value: '' } })

    const message = screen.getByText(t('builder.validate.integerRequired'))
    expect(message).toHaveAttribute('role', 'alert')
    expect(atLeast.getAttribute('aria-describedby')).toContain(message.id)
    expect(startsDebug().default.achievements?.[0].stat_gates?.[0].at_least).toBe(5)
  })

  it('shows the empty state when the start has no achievements', () => {
    render(<Harness initial={baseDraft({ default: start({ achievements: [] }) })} />)

    expect(screen.getByText(t('builder.achievements.empty.title'))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('builder.achievements.create') })).toBeInTheDocument()
  })

  it('shows an alert linked to the invalid field', () => {
    render(<Harness initial={baseDraft({ default: start({ achievements: [achievement({ name: '' })] }) })} />)

    const message = screen.getByText(t('builder.field.required'))
    expect(message).toHaveAttribute('role', 'alert')
    const nameInput = screen.getByLabelText(t('builder.achievements.name'))
    expect(nameInput.getAttribute('aria-describedby')).toContain(message.id)
  })

  it('removes the selected entry and keeps a coherent focus', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={baseDraft({
          default: start({ achievements: [achievement({ id: 'a1', name: 'a' }), achievement({ id: 'a2', name: 'b' })] }),
        })}
      />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.achievements.remove.title', { name: 'a' }) }))

    expect(startsDebug().default.achievements).toEqual([achievement({ id: 'a2', name: 'b' })])
    await waitFor(() => {
      expect(document.getElementById('builder-field-achievements.default.0.id')).toBe(document.activeElement)
    })
  })
})
