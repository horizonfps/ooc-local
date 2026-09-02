import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { StatsTab } from './StatsTab'
import { validateDraft } from '../../builder/validate'
import type { BuilderDraft } from '../../screens/BuilderEditorScreen'
import type { StatDef } from '../../api'
import { t } from '../../i18n'

function stat(overrides: Partial<StatDef> = {}): StatDef {
  return {
    id: 'stat-1',
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

function baseDraft(stats: StatDef[] = [stat()]): BuilderDraft {
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
    starts: {
      default: {
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
      },
    },
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
      <StatsTab scenarioId="school" draft={draft} onChange={setDraft} errors={errors} goToTab={() => {}} />
      <pre data-testid="stats-debug">{JSON.stringify(draft.stats)}</pre>
      <pre data-testid="dynamic-debug">{String(draft.meta.allow_dynamic_stats)}</pre>
    </>
  )
}

describe('StatsTab', () => {
  it('filling name, minimum, maximum and starting value reflects in the draft', () => {
    render(<Harness initial={baseDraft()} />)

    fireEvent.change(screen.getByLabelText(t('builder.stats.name')), { target: { value: 'Reputação' } })
    fireEvent.change(screen.getByLabelText(t('builder.stats.min')), { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText(t('builder.stats.max')), { target: { value: '100' } })
    fireEvent.change(screen.getByLabelText(t('builder.stats.default')), { target: { value: '40' } })

    const stats = JSON.parse(screen.getByTestId('stats-debug').textContent ?? '[]')
    expect(stats[0]).toMatchObject({ name: 'Reputação', min: 0, max: 100, default: 40 })
  })

  it('creates a stat with a free suggested id and focuses the name', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft([stat({ id: 'stat-1' })])} />)

    await user.click(screen.getByRole('button', { name: t('builder.stats.create') }))

    const stats = JSON.parse(screen.getByTestId('stats-debug').textContent ?? '[]')
    expect(stats[1]).toMatchObject({ id: 'stat-2', min: 0, max: 100, default: 50, levels: [] })
    await waitFor(() => {
      expect(document.getElementById('builder-field-stats.1.name')).toBe(document.activeElement)
    })
  })

  it('selects another stat from the list, announces and focuses the name', async () => {
    const user = userEvent.setup()
    const draft = baseDraft([stat({ id: 'stat-1', name: 'Reputação' }), stat({ id: 'stat-2', name: 'Energia' })])
    render(<Harness initial={draft} />)

    await user.click(screen.getAllByRole('button', { name: /Energia/ })[0])

    await waitFor(() => {
      expect(document.getElementById('builder-field-stats.1.name')).toBe(document.activeElement)
    })
    expect(screen.getByText(t('builder.detail.selected', { name: 'Energia' }))).toBeInTheDocument()
  })

  it('adds a level with a derived from and focuses the text', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft([stat({ min: 0, max: 100, levels: [] })])} />)

    await user.click(screen.getByRole('button', { name: t('builder.stats.levels.add') }))
    let stats = JSON.parse(screen.getByTestId('stats-debug').textContent ?? '[]')
    expect(stats[0].levels).toEqual([{ from: 0, text: '' }])
    await waitFor(() => {
      expect(document.getElementById('builder-field-stats.0.levels.0.text')).toBe(document.activeElement)
    })

    await user.click(screen.getByRole('button', { name: t('builder.stats.levels.add') }))
    stats = JSON.parse(screen.getByTestId('stats-debug').textContent ?? '[]')
    expect(stats[0].levels[1]).toEqual({ from: 1, text: '' })
  })

  it('marks the dynamic stats toggle', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('checkbox', { name: t('builder.stats.allowDynamic') }))

    expect(screen.getByTestId('dynamic-debug').textContent).toBe('true')
  })

  it('shows the empty state with the toggle still visible', () => {
    render(<Harness initial={baseDraft([])} />)

    expect(screen.getByText(t('builder.stats.empty.title'))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('builder.stats.create') })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: t('builder.stats.allowDynamic') })).toBeInTheDocument()
  })

  it('restores the saved value when a numeric field is cleared', () => {
    render(<Harness initial={baseDraft([stat({ max: 100 })])} />)

    const maxInput = screen.getByLabelText(t('builder.stats.max')) as HTMLInputElement
    fireEvent.change(maxInput, { target: { value: '' } })

    expect(screen.getByText(t('builder.validate.integerRequired'))).toBeInTheDocument()
    let stats = JSON.parse(screen.getByTestId('stats-debug').textContent ?? '[]')
    expect(stats[0].max).toBe(100)

    fireEvent.blur(maxInput)
    expect(maxInput).toHaveValue(100)
    stats = JSON.parse(screen.getByTestId('stats-debug').textContent ?? '[]')
    expect(stats[0].max).toBe(100)
  })

  it('stores empty icon and description as null', () => {
    render(<Harness initial={baseDraft([stat({ icon: null, description: null })])} />)

    const iconInput = screen.getByLabelText(t('builder.stats.icon'))
    fireEvent.change(iconInput, { target: { value: '⭐' } })
    fireEvent.change(iconInput, { target: { value: '' } })

    const descriptionInput = screen.getByLabelText(t('builder.stats.description'))
    fireEvent.change(descriptionInput, { target: { value: 'Some text' } })
    fireEvent.change(descriptionInput, { target: { value: '' } })

    const stats = JSON.parse(screen.getByTestId('stats-debug').textContent ?? '[]')
    expect(stats[0].icon).toBeNull()
    expect(stats[0].description).toBeNull()
  })

  it('marks a non-selected stat with an error in the list', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft([stat({ id: 'stat-1', name: 'Reputação' }), stat({ id: 'stat-2', name: '' })])} />)

    // mounts on the invalid stat (first-error-wins); switch to the valid one to isolate the marker
    await user.click(screen.getAllByRole('button', { name: /Reputação/ })[0])

    const invalidMarkers = screen.getAllByText(t('builder.starts.itemInvalid'))
    expect(invalidMarkers).toHaveLength(1)
    const invalidItem = invalidMarkers[0].closest('li')
    expect(invalidItem).toHaveClass('is-invalid')
    expect(invalidItem).not.toHaveClass('is-selected')
  })

  it('opens selecting the first stat with an error', () => {
    render(
      <Harness
        initial={baseDraft([
          stat({ id: 'stat-1', name: 'Reputação' }),
          stat({ id: 'stat-2', name: 'Energia' }),
          stat({ id: 'stat-3', name: '' }),
        ])}
      />,
    )

    expect(document.getElementById('builder-field-stats.2.name')).toBeInTheDocument()
  })

  it('removes a level from the middle and moves focus to the one that took its place', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={baseDraft([
          stat({
            levels: [
              { from: 0, text: 'a' },
              { from: 10, text: 'b' },
              { from: 20, text: 'c' },
            ],
          }),
        ])}
      />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.stats.levels.remove', { index: 2 }) }))

    await waitFor(() => {
      expect(document.getElementById('builder-field-stats.0.levels.1.text')).toBe(document.activeElement)
    })
    expect(screen.getByText(t('builder.stats.levels.removed', { index: 2 }))).toBeInTheDocument()
  })

  it('keeps the selected stat when an earlier one is removed', async () => {
    const user = userEvent.setup()
    const draft = baseDraft([
      stat({ id: 'a', name: 'Aaa' }),
      stat({ id: 'b', name: 'Bbb' }),
      stat({ id: 'c', name: 'Ccc' }),
    ])
    render(<Harness initial={draft} />)
    await user.click(screen.getAllByRole('button', { name: /Ccc/ })[0])
    await waitFor(() => {
      expect(document.getElementById('builder-field-stats.2.name')).toBe(document.activeElement)
    })

    await user.click(screen.getByRole('button', { name: t('builder.stats.remove.title', { name: 'Aaa' }) }))

    expect((document.getElementById('builder-field-stats.1.name') as HTMLInputElement).value).toBe('Ccc')
  })

  it('removes the only stat and moves focus to the create button', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft([stat({ id: 'stat-1', name: 'Reputação' })])} />)

    await user.click(screen.getByRole('button', { name: t('builder.stats.remove.title', { name: 'Reputação' }) }))

    expect(await screen.findByText(t('builder.stats.empty.title'))).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: t('builder.stats.create') })).toBe(document.activeElement)
    })
  })

  it('flags a duplicated id on the second stat', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft([stat({ id: 'vida', name: 'Vida A' }), stat({ id: 'vida', name: 'Vida B' })])} />)

    expect(screen.getByText(t('builder.field.slugTaken', { slug: 'vida' }))).toBeInTheDocument()
    // mounts on the invalid (second) stat, per the first-error-wins initial selection rule
    expect(screen.getByLabelText(t('builder.stats.id'))).toHaveAttribute('aria-invalid', 'true')

    await user.click(screen.getAllByRole('button', { name: /Vida A/ })[0])
    expect(screen.getByLabelText(t('builder.stats.id'))).not.toHaveAttribute('aria-invalid', 'true')
  })

  it('flags a maximum below the minimum', () => {
    render(<Harness initial={baseDraft([stat({ min: 10, max: 5 })])} />)

    const message = screen.getByText(t('builder.validate.statMaxAboveMin'))
    expect(message).toHaveAttribute('role', 'alert')
    const maxInput = screen.getByLabelText(t('builder.stats.max'))
    expect(maxInput).toHaveAttribute('aria-describedby', message.id)
  })

  it('flags an invalid color without rewriting the field', () => {
    render(<Harness initial={baseDraft([stat({ color: null })])} />)

    fireEvent.change(screen.getByLabelText(t('builder.stats.color')), { target: { value: '#zzz' } })

    expect(screen.getByText(t('builder.validate.colorInvalid'))).toBeInTheDocument()
    const stats = JSON.parse(screen.getByTestId('stats-debug').textContent ?? '[]')
    expect(stats[0].color).toBe('#zzz')
  })

  it('flags a level out of the stat range', () => {
    render(<Harness initial={baseDraft([stat({ min: 0, max: 100, levels: [{ from: 200, text: 'x' }] })])} />)

    expect(screen.getByText(t('builder.validate.levelFromRange', { min: 0, max: 100 }))).toBeInTheDocument()
  })
})
