import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { CharactersTab } from './CharactersTab'
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
        characters: ['luca'],
      },
    },
    characters: {
      luca: {
        name: 'Luca',
        role: 'Janitor',
        appearance: 'Tall, gray coveralls.',
        personality: 'Quiet, watchful.',
        voice: 'Short sentences.',
        mind: { feeling: 'Bored', goal: 'Finish the round', opinion_of_player: null, secret_plan: null },
        sprite: null,
        power_tier: null,
        emotions: ['default'],
      },
    },
    stats: [],
    lorebook: {},
    commands: [],
  }
}

function Harness(props: { initial: BuilderDraft }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return (
    <>
      <CharactersTab scenarioId="school" draft={draft} onChange={setDraft} errors={errors} goToTab={() => {}} />
      <pre data-testid="characters-debug">{JSON.stringify(draft.characters)}</pre>
      <pre data-testid="starts-debug">{JSON.stringify(draft.starts)}</pre>
    </>
  )
}

describe('CharactersTab', () => {
  it('creating a character and filling the ten text fields reflects in the draft', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('button', { name: t('builder.characters.create') }))
    fireEvent.change(screen.getByLabelText(t('builder.characters.create.idLabel')), { target: { value: 'mira' } })
    const nameInputs = screen.getAllByLabelText(t('builder.characters.name'))
    fireEvent.change(nameInputs[nameInputs.length - 1], { target: { value: 'Mira' } })
    await user.click(screen.getByRole('button', { name: t('builder.characters.create.submit') }))

    fireEvent.change(screen.getByLabelText(t('builder.characters.role')), { target: { value: 'Student' } })
    fireEvent.change(screen.getByLabelText(t('builder.characters.appearance')), { target: { value: 'Short hair.' } })
    fireEvent.change(screen.getByLabelText(t('builder.characters.personality')), { target: { value: 'Curious.' } })
    fireEvent.change(screen.getByLabelText(t('builder.characters.voice')), { target: { value: 'Fast talker.' } })
    fireEvent.change(screen.getByLabelText(t('builder.characters.mind.feeling')), { target: { value: 'Nervous' } })
    fireEvent.change(screen.getByLabelText(t('builder.characters.mind.goal')), { target: { value: 'Pass the exam' } })
    fireEvent.change(screen.getByLabelText(new RegExp(t('builder.characters.mind.opinion'))), { target: { value: 'Curious about them' } })
    fireEvent.change(screen.getByLabelText(new RegExp(t('builder.characters.mind.secretPlan'))), { target: { value: 'Skip class' } })
    fireEvent.change(screen.getByLabelText(new RegExp(t('builder.characters.sprite'))), { target: { value: 'mira' } })

    const characters = JSON.parse(screen.getByTestId('characters-debug').textContent ?? '{}')
    expect(characters.mira).toMatchObject({
      name: 'Mira',
      role: 'Student',
      appearance: 'Short hair.',
      personality: 'Curious.',
      voice: 'Fast talker.',
      mind: { feeling: 'Nervous', goal: 'Pass the exam', opinion_of_player: 'Curious about them', secret_plan: 'Skip class' },
      sprite: 'mira',
      power_tier: null,
      emotions: ['default'],
    })
  })

  it('adds an emotion via the suggestion menu and via Enter, default stays first without a remove button', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('button', { name: 'smile' }))
    const addInput = screen.getByLabelText(t('builder.characters.emotions.add'))
    fireEvent.change(addInput, { target: { value: 'sad' } })
    fireEvent.keyDown(addInput, { key: 'Enter' })

    const characters = JSON.parse(screen.getByTestId('characters-debug').textContent ?? '{}')
    expect(characters.luca.emotions).toEqual(['default', 'smile', 'sad'])

    const defaultChip = screen.getByTitle(t('builder.characters.emotions.defaultLocked'))
    expect(within(defaultChip).queryByRole('button')).toBeNull()
  })

  it('setting a power tier shows the badge in the list', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    const tierSelect = screen.getByLabelText(new RegExp(t('builder.characters.tier')))
    await user.selectOptions(tierSelect, '1')

    expect(screen.getByText(t('builder.characters.tierBadge', { tier: 1 }))).toBeInTheDocument()
    const characters = JSON.parse(screen.getByTestId('characters-debug').textContent ?? '{}')
    expect(characters.luca.power_tier).toBe(1)
  })

  it('a duplicate emotion is ignored and an invalid one is rejected', async () => {
    render(<Harness initial={baseDraft()} />)

    const addInput = screen.getByLabelText(t('builder.characters.emotions.add'))
    fireEvent.change(addInput, { target: { value: 'default' } })
    fireEvent.keyDown(addInput, { key: 'Enter' })

    let characters = JSON.parse(screen.getByTestId('characters-debug').textContent ?? '{}')
    expect(characters.luca.emotions).toEqual(['default'])

    fireEvent.change(addInput, { target: { value: 'Feliz' } })
    fireEvent.keyDown(addInput, { key: 'Enter' })

    expect(screen.getAllByText(t('builder.field.slugInvalid')).length).toBeGreaterThan(0)
    characters = JSON.parse(screen.getByTestId('characters-debug').textContent ?? '{}')
    expect(characters.luca.emotions).toEqual(['default'])
  })

  it('removing an emotion warns that its file stays on disk', async () => {
    const draft = baseDraft()
    draft.characters.luca.emotions = ['default', 'smile']
    render(<Harness initial={draft} />)

    await userEvent.setup().click(screen.getByRole('button', { name: t('builder.characters.emotions.remove', { emotion: 'smile' }) }))

    expect(screen.getByText(t('builder.characters.emotions.hasAsset', { emotion: 'smile' }))).toBeInTheDocument()
    const characters = JSON.parse(screen.getByTestId('characters-debug').textContent ?? '{}')
    expect(characters.luca.emotions).toEqual(['default'])
  })

  it('blank optional mind fields save as null', () => {
    const draft = baseDraft()
    draft.characters.luca.mind.opinion_of_player = 'Something'
    render(<Harness initial={draft} />)

    const opinion = screen.getByLabelText(new RegExp(t('builder.characters.mind.opinion')))
    fireEvent.change(opinion, { target: { value: '   ' } })

    const characters = JSON.parse(screen.getByTestId('characters-debug').textContent ?? '{}')
    expect(characters.luca.mind.opinion_of_player).toBeNull()
  })

  it('deleting a character cited by a start removes the citation and announces it', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    const deleteButton = screen.getByRole('button', { name: t('builder.characters.delete.title', { name: 'Luca' }) })
    await user.click(deleteButton)

    const dialog = screen.getByRole('heading', { name: t('builder.characters.delete.title', { name: 'Luca' }) }).closest('dialog')
    expect(dialog).not.toBeNull()
    await user.click(within(dialog as HTMLElement).getByRole('button', { name: t('builder.characters.delete') }))

    const starts = JSON.parse(screen.getByTestId('starts-debug').textContent ?? '{}')
    expect(starts.default.characters).toEqual([])
    expect(screen.getByText(t('builder.characters.delete.castUpdated', { name: 'Luca', starts: 'Default start' }))).toBeInTheDocument()
  })

  it('a draft without characters is valid — characters: {} is an accepted payload', () => {
    const draft = baseDraft()
    draft.characters = {}
    const errors = validateDraft(draft)

    expect(errors.some((e) => e.tab === 'characters' && e.field === 'characters')).toBe(false)
  })

  it('a legacy character with blank role/appearance/personality/voice/mind saves without errors', () => {
    const draft = baseDraft()
    draft.characters.luca = {
      name: 'Luca',
      role: '',
      appearance: '',
      personality: '',
      voice: '',
      mind: { feeling: '', goal: '', opinion_of_player: null, secret_plan: null },
      sprite: null,
      power_tier: null,
      emotions: ['default'],
    }
    const errors = validateDraft(draft)

    expect(errors.some((e) => e.tab === 'characters' && e.field.startsWith('characters.luca'))).toBe(false)
  })

  it('refuses to add an emotion once the cap is reached', async () => {
    const draft = baseDraft()
    draft.characters.luca.emotions = ['default', ...Array.from({ length: 19 }, (_, i) => `e${i}`)]
    render(<Harness initial={draft} />)

    const addInput = screen.getByLabelText(t('builder.characters.emotions.add'))
    fireEvent.change(addInput, { target: { value: 'one-too-many' } })
    fireEvent.keyDown(addInput, { key: 'Enter' })

    expect(screen.getByText(t('builder.characters.emotions.max', { max: 19 }))).toBeInTheDocument()
    const characters = JSON.parse(screen.getByTestId('characters-debug').textContent ?? '{}')
    expect(characters.luca.emotions).toHaveLength(20)
  })

  it('resets the emotion input, error and notice when switching to another character', async () => {
    const user = userEvent.setup()
    const draft = baseDraft()
    draft.characters.luca.emotions = ['default', 'smile']
    draft.characters.mira = {
      name: 'Mira',
      role: 'Student',
      appearance: 'x',
      personality: 'y',
      voice: 'z',
      mind: { feeling: 'x', goal: 'y', opinion_of_player: null, secret_plan: null },
      sprite: null,
      power_tier: null,
      emotions: ['default', 'smile'],
    }
    render(<Harness initial={draft} />)

    const addInput = screen.getByLabelText(t('builder.characters.emotions.add'))
    fireEvent.change(addInput, { target: { value: 'Feliz' } })
    fireEvent.keyDown(addInput, { key: 'Enter' })
    expect(screen.getAllByText(t('builder.field.slugInvalid')).length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: t('builder.characters.emotions.remove', { emotion: 'smile' }) }))
    expect(screen.getByText(t('builder.characters.emotions.hasAsset', { emotion: 'smile' }))).toBeInTheDocument()

    await user.click(screen.getByText('Mira', { selector: '.builder-characters-listItemName' }))

    expect(screen.queryByText(t('builder.field.slugInvalid'))).toBeNull()
    expect(screen.queryByText(t('builder.characters.emotions.hasAsset', { emotion: 'smile' }))).toBeNull()
    expect(screen.getByLabelText(t('builder.characters.emotions.add'))).toHaveValue('')
  })

  it('trims the sprite value as it is typed', () => {
    render(<Harness initial={baseDraft()} />)

    const sprite = screen.getByLabelText(new RegExp(t('builder.characters.sprite')))
    fireEvent.change(sprite, { target: { value: '  luca-sprite  ' } })

    const characters = JSON.parse(screen.getByTestId('characters-debug').textContent ?? '{}')
    expect(characters.luca.sprite).toBe('luca-sprite')
  })

  it('trims the name on blur', () => {
    render(<Harness initial={baseDraft()} />)

    const name = document.getElementById('builder-field-characters.luca.name') as HTMLInputElement
    fireEvent.change(name, { target: { value: '  Luca Jr  ' } })
    fireEvent.blur(name)

    const characters = JSON.parse(screen.getByTestId('characters-debug').textContent ?? '{}')
    expect(characters.luca.name).toBe('Luca Jr')
  })

  it('selecting an item moves focus to the first field and announces it', async () => {
    const user = userEvent.setup()
    const draft = baseDraft()
    draft.characters.mira = {
      name: 'Mira',
      role: 'Student',
      appearance: 'x',
      personality: 'y',
      voice: 'z',
      mind: { feeling: 'x', goal: 'y', opinion_of_player: null, secret_plan: null },
      sprite: null,
      power_tier: null,
      emotions: ['default'],
    }
    render(<Harness initial={draft} />)

    await user.click(screen.getByText('Mira', { selector: '.builder-characters-listItemName' }))

    await waitFor(() => {
      const nameInput = document.getElementById('builder-field-characters.mira.name')
      expect(nameInput).toHaveFocus()
    })
    expect(screen.getByText(t('builder.detail.selected', { name: 'Mira' }))).toBeInTheDocument()
  })

  it('a duplicate id in the create dialog shows the slug taken message', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('button', { name: t('builder.characters.create') }))
    fireEvent.change(screen.getByLabelText(t('builder.characters.create.idLabel')), { target: { value: 'luca' } })
    await user.click(screen.getByRole('button', { name: t('builder.characters.create.submit') }))

    expect(screen.getByText(t('builder.field.slugTaken', { slug: 'luca' }))).toBeInTheDocument()
  })
})
