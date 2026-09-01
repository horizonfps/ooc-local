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
        anchor: false,
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
    const nameInput = document.getElementById('builder-field-starts.name') as HTMLInputElement
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
      play_guide: null,
      suggestions: [],
      hud: { location: 'Yard', time: '09:00', weather: 'clear' },
      characters: null,
    }
    render(<Harness initial={draft} />)

    await user.click(screen.getByRole('button', { name: 'Second start0/3' }))

    await waitFor(() => {
      const nameInput = document.getElementById('builder-field-starts.name')
      expect(nameInput).toHaveFocus()
    })
    const nameInput = document.getElementById('builder-field-starts.name') as HTMLInputElement
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
