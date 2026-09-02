import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { StartsTab } from './StartsTab'
import { validateDraft } from '../../builder/validate'
import type { BuilderDraft } from '../../screens/BuilderEditorScreen'
import { t } from '../../i18n'

function baseDraft(): BuilderDraft {
  return {
    meta: {
      name: 'The School',
      tagline: null,
      description: null,
      locale: 'en',
      tags: [],
      default_start: 'default',
      world_mode: 'guided',
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
    characters: {
      luca: {
        name: 'Luca',
        role: 'Janitor',
        appearance: '',
        personality: '',
        voice: '',
        mind: { feeling: '', goal: '', opinion_of_player: null, secret_plan: null },
        sprite: null,
        power_tier: null,
        emotions: [],
      },
    },
  }
}

function Harness(props: { initial: BuilderDraft; goToTab?: (tab: string) => void }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return (
    <>
      <StartsTab
        scenarioId="school"
        draft={draft}
        onChange={setDraft}
        errors={errors}
        goToTab={(props.goToTab as never) ?? (() => {})}
      />
      <pre data-testid="starts-debug">{JSON.stringify(draft.starts)}</pre>
      <pre data-testid="default-debug">{draft.meta.default_start}</pre>
    </>
  )
}

describe('StartsTab', () => {
  it('filling prologue, opening scene, HUD and suggestions reflects in the draft', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    const prologue = screen.getByLabelText(t('builder.starts.prologue'))
    fireEvent.change(prologue, { target: { value: 'A new beginning.' } })

    const location = screen.getByLabelText(t('builder.starts.hud.location'))
    fireEvent.change(location, { target: { value: 'Courtyard' } })

    await user.click(screen.getByRole('button', { name: t('builder.starts.suggestions.add') }))
    const suggestionInput = screen.getByLabelText(t('builder.starts.suggestions.item', { index: 1 }))
    fireEvent.change(suggestionInput, { target: { value: 'Look around' } })

    const starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts.default.prologue).toBe('A new beginning.')
    expect(starts.default.hud.location).toBe('Courtyard')
    expect(starts.default.suggestions).toEqual(['Look around'])
  })

  it('creating a start with the suggested id copies the default HUD and selects it', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('button', { name: t('builder.starts.create') }))
    expect(screen.getByLabelText(t('builder.starts.create.idLabel'))).toHaveValue('start-2')

    fireEvent.change(screen.getByLabelText(t('builder.starts.create.idLabel')), { target: { value: 'start-2' } })
    const nameInputs = screen.getAllByLabelText(t('builder.starts.name'))
    fireEvent.change(nameInputs[nameInputs.length - 1], { target: { value: 'Second start' } })

    await user.click(screen.getByRole('button', { name: t('builder.starts.create.submit') }))

    const starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts['start-2']).toBeTruthy()
    expect(starts['start-2'].hud).toEqual(starts.default.hud)
    expect(starts['start-2'].prologue).toBe('')
    const nameInput = document.getElementById('builder-field-starts.start-2.name') as HTMLInputElement
    expect(nameInput.value).toBe('Second start')
  })

  it('selects another start from the list and moves focus + announces', async () => {
    const user = userEvent.setup()
    const draft = baseDraft()
    draft.starts['start-2'] = {
      id: 'start-2',
      name: 'Second start',
      prologue: 'x',
      opening_scene: 'y',
      conflict: null,
      mission: null,
      play_guide: null,
      suggestions: [],
      hud: { location: 'Yard', time: '09:00', weather: 'clear' },
      characters: null,
    }
    render(<Harness initial={draft} />)

    await user.click(screen.getByRole('button', { name: 'Second start0/3' }))

    await waitFor(() => {
      const nameInput = document.getElementById('builder-field-starts.start-2.name')
      expect(nameInput).toHaveFocus()
    })
    const nameInput = document.getElementById('builder-field-starts.start-2.name') as HTMLInputElement
    expect(nameInput.value).toBe('Second start')
    expect(screen.getByText(t('builder.detail.selected', { name: 'Second start' }))).toBeInTheDocument()

    const radio = screen.getByRole('radio', { name: t('builder.starts.defaultToggle') })
    await user.click(radio)
    expect(screen.getByTestId('default-debug').textContent).toBe('start-2')
  })

  it('the third suggestion disables the add button', async () => {
    const user = userEvent.setup()
    const draft = baseDraft()
    draft.starts.default.suggestions = ['a', 'b']
    render(<Harness initial={draft} />)

    const addButton = screen.getByRole('button', { name: t('builder.starts.suggestions.add') })
    expect(addButton).not.toBeDisabled()
    await user.click(addButton)
    expect(addButton).toBeDisabled()
  })

  it('a duplicate id in the create dialog shows the slug taken message', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('button', { name: t('builder.starts.create') }))
    fireEvent.change(screen.getByLabelText(t('builder.starts.create.idLabel')), { target: { value: 'default' } })
    await user.click(screen.getByRole('button', { name: t('builder.starts.create.submit') }))

    expect(screen.getByText(t('builder.field.slugTaken', { slug: 'default' }))).toBeInTheDocument()
  })

  it('an invalid hud.time produces a validation error', () => {
    const draft = baseDraft()
    draft.starts.default.hud.time = '25:00'
    const errors = validateDraft(draft)

    expect(
      errors.some((e) => e.tab === 'starts' && e.field === 'starts.default.hud.time' && e.message === t('builder.field.time.invalid')),
    ).toBe(true)
  })

  it('marks a non-selected start with an error as invalid in the master list', () => {
    const draft = baseDraft()
    draft.starts['start-2'] = {
      id: 'start-2',
      name: '',
      prologue: 'x',
      opening_scene: 'y',
      conflict: null,
      mission: null,
      play_guide: null,
      suggestions: [],
      hud: { location: 'Yard', time: '09:00', weather: 'clear' },
      characters: null,
    }
    render(<Harness initial={draft} />)

    const item = screen.getByText(t('builder.starts.itemInvalid')).closest('li')
    expect(item).toHaveClass('is-invalid')
    expect(within(item as HTMLElement).getByText('start-2')).toBeInTheDocument()

    const defaultItem = screen.getByText('Default start').closest('li')
    expect(defaultItem).not.toHaveClass('is-invalid')
  })

  it('blanking play_guide down to whitespace saves it as null', () => {
    const draft = baseDraft()
    draft.starts.default.play_guide = 'A note.'
    render(<Harness initial={draft} />)

    const playGuide = screen.getByLabelText(new RegExp(t('builder.starts.playGuide')))
    fireEvent.change(playGuide, { target: { value: '   ' } })

    const starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts.default.play_guide).toBeNull()
  })

  it('typing conflict and mission saves them to the draft', () => {
    render(<Harness initial={baseDraft()} />)

    const conflict = screen.getByLabelText(new RegExp(t('builder.starts.conflict')))
    fireEvent.change(conflict, { target: { value: 'Duas facções, um poço' } })

    const mission = screen.getByLabelText(new RegExp(t('builder.starts.mission')))
    fireEvent.change(mission, { target: { value: 'Achar a fonte' } })

    const starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts.default.conflict).toBe('Duas facções, um poço')
    expect(starts.default.mission).toBe('Achar a fonte')
  })

  it('blanking conflict down to whitespace saves it as null', () => {
    const draft = baseDraft()
    draft.starts.default.conflict = 'Algo'
    render(<Harness initial={draft} />)

    const conflict = screen.getByLabelText(new RegExp(t('builder.starts.conflict')))
    fireEvent.change(conflict, { target: { value: '   ' } })

    const starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts.default.conflict).toBeNull()
  })

  it('a start without conflict or mission opens with empty textareas and no alert', () => {
    render(<Harness initial={baseDraft()} />)

    const conflict = screen.getByLabelText(new RegExp(t('builder.starts.conflict')))
    const mission = screen.getByLabelText(new RegExp(t('builder.starts.mission')))
    expect(conflict).toHaveValue('')
    expect(mission).toHaveValue('')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('switching starts swaps the conflict and mission values', async () => {
    const user = userEvent.setup()
    const draft = baseDraft()
    draft.starts.default.conflict = 'First conflict'
    draft.starts['start-2'] = {
      id: 'start-2',
      name: 'Second start',
      prologue: 'x',
      opening_scene: 'y',
      conflict: 'Second conflict',
      mission: null,
      play_guide: null,
      suggestions: [],
      hud: { location: 'Yard', time: '09:00', weather: 'clear' },
      characters: null,
    }
    render(<Harness initial={draft} />)

    await user.click(screen.getByRole('button', { name: 'Second start0/3' }))

    await waitFor(() => {
      const conflict = document.getElementById('builder-field-starts.start-2.conflict') as HTMLTextAreaElement
      expect(conflict.value).toBe('Second conflict')
    })
  })

  it('the conflict and mission fields sit between opening scene and play guide in the DOM', () => {
    render(<Harness initial={baseDraft()} />)

    const textareas = Array.from(document.querySelectorAll('.builder-field textarea'))
    const labels = textareas.map((el) => el.id)
    const openingIndex = labels.indexOf('builder-field-starts.default.opening_scene')
    const conflictIndex = labels.indexOf('builder-field-starts.default.conflict')
    const missionIndex = labels.indexOf('builder-field-starts.default.mission')
    const playGuideIndex = labels.indexOf('builder-field-starts.default.play_guide')

    expect(openingIndex).toBeLessThan(conflictIndex)
    expect(conflictIndex).toBeLessThan(missionIndex)
    expect(missionIndex).toBeLessThan(playGuideIndex)
  })

  it('the conflict and mission textareas are linked to their hints via aria-describedby', () => {
    render(<Harness initial={baseDraft()} />)

    const conflict = screen.getByLabelText(new RegExp(t('builder.starts.conflict')))
    expect(conflict.getAttribute('aria-describedby')).toContain('builder-field-starts.default.conflict-hint')
    expect(document.getElementById('builder-field-starts.default.conflict-hint')?.textContent).toBe(
      t('builder.starts.conflict.hint'),
    )

    const mission = screen.getByLabelText(new RegExp(t('builder.starts.mission')))
    expect(mission.getAttribute('aria-describedby')).toContain('builder-field-starts.default.mission-hint')
    expect(document.getElementById('builder-field-starts.default.mission-hint')?.textContent).toBe(
      t('builder.starts.mission.hint'),
    )
  })

  it('a new start is born with conflict and mission null', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('button', { name: t('builder.starts.create') }))
    fireEvent.change(screen.getByLabelText(t('builder.starts.create.idLabel')), { target: { value: 'start-2' } })
    const nameInputs = screen.getAllByLabelText(t('builder.starts.name'))
    fireEvent.change(nameInputs[nameInputs.length - 1], { target: { value: 'Second start' } })
    await user.click(screen.getByRole('button', { name: t('builder.starts.create.submit') }))

    const starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts['start-2'].conflict).toBeNull()
    expect(starts['start-2'].mission).toBeNull()
    const conflict = document.getElementById('builder-field-starts.start-2.conflict') as HTMLTextAreaElement
    const mission = document.getElementById('builder-field-starts.start-2.mission') as HTMLTextAreaElement
    expect(conflict.value).toBe('')
    expect(mission.value).toBe('')
  })

  it('a scenario without characters shows the cast empty hint that calls goToTab', async () => {
    const user = userEvent.setup()
    const draft = baseDraft()
    draft.characters = {}
    const goToTab = vi.fn()
    render(<Harness initial={draft} goToTab={goToTab} />)

    const link = screen.getByRole('button', { name: t('builder.starts.cast.empty') })
    await user.click(link)

    expect(goToTab).toHaveBeenCalledWith('characters')
  })

  it('cast mode switches between whole cast and an explicit selection', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    expect(screen.getByRole('radio', { name: t('builder.starts.cast.all') })).toBeChecked()
    expect(screen.queryByRole('checkbox', { name: 'Luca' })).toBeNull()

    await user.click(screen.getByRole('radio', { name: t('builder.starts.cast.custom') }))
    let starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts.default.characters).toEqual([])

    await user.click(screen.getByRole('checkbox', { name: 'Luca' }))
    starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts.default.characters).toEqual(['luca'])

    await user.click(screen.getByRole('checkbox', { name: 'Luca' }))
    starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts.default.characters).toEqual([])

    await user.click(screen.getByRole('radio', { name: t('builder.starts.cast.all') }))
    starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts.default.characters).toBeNull()
  })

  it('deleting the only start is impossible: the button is disabled with the reason', () => {
    render(<Harness initial={baseDraft()} />)

    const deleteButton = screen.getByRole('button', { name: t('builder.starts.delete.title', { name: 'Default start' }) })
    expect(deleteButton).toBeDisabled()
    expect(deleteButton).toHaveAttribute('title', t('builder.starts.delete.lastDisabled'))
  })

  it('deleting the default start promotes another and announces the swap', async () => {
    const user = userEvent.setup()
    const draft = baseDraft()
    draft.starts['start-2'] = {
      id: 'start-2',
      name: 'Second start',
      prologue: 'x',
      opening_scene: 'y',
      conflict: null,
      mission: null,
      play_guide: null,
      suggestions: [],
      hud: { location: 'Yard', time: '09:00', weather: 'clear' },
      characters: null,
    }
    render(<Harness initial={draft} />)

    const deleteButton = screen.getByRole('button', { name: t('builder.starts.delete.title', { name: 'Default start' }) })
    await user.click(deleteButton)

    const dialog = screen.getByRole('heading', { name: t('builder.starts.delete.title', { name: 'Default start' }) }).closest('dialog')
    expect(dialog).not.toBeNull()
    await user.click(within(dialog as HTMLElement).getByRole('button', { name: t('builder.starts.delete') }))

    expect(screen.getByTestId('default-debug').textContent).toBe('start-2')
    expect(screen.getByText(t('builder.starts.delete.defaultMoved', { name: 'Second start' }))).toBeInTheDocument()
  })
})
