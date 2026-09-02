import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { WorldTab } from './WorldTab'
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
    world: '## Universe\n\nA dusty old school.',
    starts: {
      default: {
        id: 'default',
        name: 'Default start',
        prologue: '',
        opening_scene: '',
        conflict: null,
        mission: null,
        play_guide: null,
        suggestions: [],
        hud: { location: 'Hallway', time: '08:00', weather: 'clear' },
        characters: [],
      },
    },
    characters: {},
  }
}

function Harness(props: { initial: BuilderDraft; goToTab?: (tab: string) => void }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return (
    <>
      <WorldTab
        scenarioId="school"
        draft={draft}
        onChange={setDraft}
        errors={errors}
        goToTab={(props.goToTab as never) ?? (() => {})}
      />
      <pre data-testid="world-debug">{draft.world}</pre>
      <pre data-testid="world-mode-debug">{draft.meta.world_mode}</pre>
    </>
  )
}

describe('WorldTab', () => {
  it('filling the guided fields updates world with the canonical headings', () => {
    render(<Harness initial={baseDraft()} />)

    const toneInput = screen.getByLabelText(t('builder.world.tone'))
    fireEvent.change(toneInput, { target: { value: 'Grim and quiet.' } })

    expect(screen.getByLabelText(t('builder.world.universe'))).toHaveValue('A dusty old school.')
    const universeInput = screen.getByLabelText(t('builder.world.universe')) as HTMLTextAreaElement
    expect(universeInput.value).toContain('A dusty old school.')
    expect(screen.getByTestId('world-debug').textContent).toBe(
      '## Universe\n\nA dusty old school.\n\n## Tone\n\nGrim and quiet.',
    )
  })

  it('inserting a variable writes it at the cursor position', async () => {
    const draft = baseDraft()
    draft.meta.world_mode = 'custom'
    draft.world = 'Hello  world'
    const user = userEvent.setup()
    render(<Harness initial={draft} />)

    const textarea = screen.getByLabelText(t('builder.world.custom.label')) as HTMLTextAreaElement
    textarea.focus()
    textarea.setSelectionRange(6, 6)

    await user.click(screen.getByRole('button', { name: t('builder.world.variables.insert', { name: 'player' }) }))

    expect(textarea.value).toBe('Hello {{player}} world')
  })

  it('a hand-written world.md that does not match the guided headers opens in custom mode with a warning', () => {
    const draft = baseDraft()
    draft.meta.world_mode = 'guided'
    draft.world = 'Just some free-form prose, no headings.'
    render(<Harness initial={draft} />)

    expect(screen.getByText(t('builder.world.mode.fallback.title'))).toBeInTheDocument()
    expect(screen.getByLabelText(t('builder.world.custom.label'))).toHaveValue(draft.world)
  })

  it('switching from guided to custom shows the notice and keeps the text', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('radio', { name: t('builder.world.mode.custom') }))

    expect(screen.getByText(t('builder.world.mode.switchToCustom'))).toBeInTheDocument()
    const textarea = screen.getByLabelText(t('builder.world.custom.label')) as HTMLTextAreaElement
    expect(textarea.value).toContain('A dusty old school.')
  })

  it('switching from custom to guided without confirming keeps custom mode', async () => {
    const draft = baseDraft()
    draft.meta.world_mode = 'custom'
    draft.world = 'A free-form prompt.'
    const user = userEvent.setup()
    render(<Harness initial={draft} />)

    await user.click(screen.getByRole('radio', { name: t('builder.world.mode.guided') }))
    expect(screen.getByText(t('builder.world.mode.switchToGuidedTitle'))).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: t('common.cancel') }))

    expect(screen.getByLabelText(t('builder.world.custom.label'))).toBeInTheDocument()
    expect(screen.queryByLabelText(t('builder.world.universe'))).not.toBeInTheDocument()
  })

  it('an unclosed {{ produces a blocking validation error', () => {
    const draft = baseDraft()
    draft.meta.world_mode = 'custom'
    draft.world = 'Hello {{player world'
    const errors = validateDraft(draft)

    expect(errors.some((e) => e.tab === 'world' && e.message === t('builder.world.variables.unbalanced'))).toBe(true)
  })

  it('clicking "keep as custom" in the fallback banner records world_mode custom', async () => {
    const draft = baseDraft()
    draft.meta.world_mode = 'guided'
    draft.world = 'Just some free-form prose, no headings.'
    const user = userEvent.setup()
    render(<Harness initial={draft} />)

    await user.click(screen.getByRole('button', { name: t('builder.world.mode.fallback.keepCustom') }))

    expect(screen.getByTestId('world-mode-debug').textContent).toBe('custom')
  })

  it('confirming the switch from custom to guided shows the three fields empty', async () => {
    const draft = baseDraft()
    draft.meta.world_mode = 'custom'
    draft.world = 'A free-form prompt.'
    const user = userEvent.setup()
    render(<Harness initial={draft} />)

    await user.click(screen.getByRole('radio', { name: t('builder.world.mode.guided') }))
    await user.click(screen.getByRole('button', { name: t('builder.world.mode.switchToGuidedSubmit') }))

    expect(screen.getByLabelText(t('builder.world.universe'))).toHaveValue('')
    expect(screen.getByLabelText(t('builder.world.tone'))).toHaveValue('')
    expect(screen.getByLabelText(t('builder.world.rules'))).toHaveValue('')
    expect(screen.getByTestId('world-debug').textContent).toBe('')
    expect(screen.getByTestId('world-mode-debug').textContent).toBe('guided')
  })

  it('the guided mode no longer has Conflict or Mission, and shows no lore blocks', () => {
    render(<Harness initial={baseDraft()} />)

    expect(screen.queryByLabelText('Central conflict')).toBeNull()
    expect(screen.queryByLabelText('Player mission')).toBeNull()
    expect(screen.getByLabelText(t('builder.world.universe'))).toBeInTheDocument()
    expect(screen.getByLabelText(t('builder.world.tone'))).toBeInTheDocument()
    expect(screen.getByLabelText(t('builder.world.rules'))).toBeInTheDocument()
    expect(screen.getByText(t('builder.world.lore.empty'))).toBeInTheDocument()
  })

  it('adding a lore block focuses its title and announces it', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('button', { name: t('builder.world.lore.add') }))

    await waitFor(() => {
      const titleInput = document.getElementById('builder-field-world.lore.0.title')
      expect(document.activeElement).toBe(titleInput)
    })
    expect(screen.getByText(t('builder.world.lore.added', { index: 1 }))).toBeInTheDocument()
  })

  it('filling a lore block writes it to world.md', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('button', { name: t('builder.world.lore.add') }))
    const titleInput = document.getElementById('builder-field-world.lore.0.title') as HTMLInputElement
    fireEvent.change(titleInput, { target: { value: 'Factions' } })
    const bodyInput = document.getElementById('builder-field-world.lore.0.body') as HTMLTextAreaElement
    fireEvent.change(bodyInput, { target: { value: 'Two.' } })

    expect(screen.getByTestId('world-debug').textContent).toBe('## Universe\n\nA dusty old school.\n\n## Factions\n\nTwo.')
  })

  it('removing a block in the middle moves focus to the block that shifted up', async () => {
    const user = userEvent.setup()
    const draft = baseDraft()
    draft.world = '## Universe\n\nA dusty old school.\n\n## One\n\nA.\n\n## Two\n\nB.\n\n## Three\n\nC.'
    render(<Harness initial={draft} />)

    const removeSecond = screen.getByRole('button', { name: t('builder.world.lore.remove', { index: 2 }) })
    await user.click(removeSecond)

    const titleInput = document.getElementById('builder-field-world.lore.1.title') as HTMLInputElement
    await waitFor(() => expect(document.activeElement).toBe(titleInput))
    expect(titleInput).toHaveValue('Three')
    expect(screen.getByText(t('builder.world.lore.removed', { index: 2 }))).toBeInTheDocument()
  })

  it('removing the only block returns focus to the add button', async () => {
    const user = userEvent.setup()
    const draft = baseDraft()
    draft.world = '## Universe\n\nA dusty old school.\n\n## Factions\n\nTwo.'
    render(<Harness initial={draft} />)

    const removeButton = screen.getByRole('button', { name: t('builder.world.lore.remove', { index: 1 }) })
    await user.click(removeButton)

    const addButton = screen.getByRole('button', { name: t('builder.world.lore.add') })
    await waitFor(() => expect(document.activeElement).toBe(addButton))
  })

  it('a reserved title does not fall back to custom mode', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    await user.click(screen.getByRole('button', { name: t('builder.world.lore.add') }))
    const titleInput = document.getElementById('builder-field-world.lore.0.title') as HTMLInputElement
    fireEvent.change(titleInput, { target: { value: 'Universe' } })

    expect(titleInput).toHaveValue('Universe')
    expect(screen.getByText(t('builder.world.lore.title.reserved', { title: 'Universe' }))).toBeInTheDocument()
    expect(screen.queryByText(t('builder.world.mode.fallback.title'))).toBeNull()
    expect(screen.getByLabelText(t('builder.world.universe'))).toBeInTheDocument()
    expect(screen.getByTestId('world-debug').textContent).toBe('## Universe\n\nA dusty old school.\n\n## ')

    fireEvent.change(titleInput, { target: { value: 'Universo antigo' } })
    expect(screen.queryByText(t('builder.world.lore.title.reserved', { title: 'Universe' }))).toBeNull()
    expect(screen.getByTestId('world-debug').textContent).toBe(
      '## Universe\n\nA dusty old school.\n\n## Universo antigo',
    )
  })

  it('a duplicated title shows the inline error on the second block, with aria-invalid', () => {
    const draft = baseDraft()
    draft.world = '## Universe\n\nA dusty old school.\n\n## Notas\n\nOne.\n\n## Notas\n\nTwo.'
    render(<Harness initial={draft} />)

    const secondTitle = document.getElementById('builder-field-world.lore.1.title') as HTMLInputElement
    expect(secondTitle).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText(t('builder.world.lore.title.duplicate'))).toBeInTheDocument()
  })

  it('the moved-hint note takes the user to Starts', async () => {
    const user = userEvent.setup()
    const goToTab = vi.fn()
    render(<Harness initial={baseDraft()} goToTab={goToTab} />)

    await user.click(screen.getByRole('button', { name: t('builder.world.guided.goToStarts') }))

    expect(goToTab).toHaveBeenCalledWith('starts')
  })

  it('an old world.md file opens with two lore blocks', () => {
    const draft = baseDraft()
    draft.world = '## Universe\n\nA dusty old school.\n\n## Conflict\n\nThe reservoir.\n\n## Mission\n\nFind the engineer.'
    render(<Harness initial={draft} />)

    expect(screen.queryByText(t('builder.world.mode.fallback.title'))).toBeNull()
    const firstTitle = document.getElementById('builder-field-world.lore.0.title') as HTMLInputElement
    const secondTitle = document.getElementById('builder-field-world.lore.1.title') as HTMLInputElement
    expect(firstTitle).toHaveValue('Conflict')
    expect(secondTitle).toHaveValue('Mission')
    const firstBody = document.getElementById('builder-field-world.lore.0.body') as HTMLTextAreaElement
    const secondBody = document.getElementById('builder-field-world.lore.1.body') as HTMLTextAreaElement
    expect(firstBody).toHaveValue('The reservoir.')
    expect(secondBody).toHaveValue('Find the engineer.')
  })

  it('a known heading after a lore block falls back to custom mode', () => {
    const draft = baseDraft()
    draft.world = '## Universe\n\nA dusty old school.\n\n## Factions\n\nTwo.\n\n## Tone\n\nGrim.'
    render(<Harness initial={draft} />)

    expect(screen.getByText(t('builder.world.mode.fallback.title'))).toBeInTheDocument()
    expect(screen.getByLabelText(t('builder.world.custom.label'))).toHaveValue(draft.world)
  })

  it('the token counter appears in both guided and custom mode', () => {
    const guidedDraft = baseDraft()
    const { unmount } = render(<Harness initial={guidedDraft} />)
    expect(
      screen.getByText(t('builder.world.tokens', { count: Math.ceil(guidedDraft.world.length / 4) })),
    ).toBeInTheDocument()
    unmount()

    const customDraft = baseDraft()
    customDraft.meta.world_mode = 'custom'
    customDraft.world = 'x'.repeat(100)
    render(<Harness initial={customDraft} />)
    expect(
      screen.getByText(t('builder.world.tokens', { count: Math.ceil(customDraft.world.length / 4) })),
    ).toBeInTheDocument()
  })

  it('the budget warning crosses the limit and does not disable Save', () => {
    const draft = baseDraft()
    draft.meta.world_mode = 'custom'
    draft.world = 'x'.repeat(7000)
    render(<Harness initial={draft} />)

    expect(screen.getByText(t('builder.world.tokens', { count: 1750 }))).toBeInTheDocument()
    expect(screen.queryByText(t('builder.world.tokens.over', { max: 2000 }))).toBeNull()

    const textarea = screen.getByLabelText(t('builder.world.custom.label')) as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'x'.repeat(9000) } })

    const overWarning = screen.getByText(t('builder.world.tokens.over', { max: 2000 }))
    expect(overWarning).toBeInTheDocument()
    expect(overWarning).toHaveAttribute('aria-live', 'polite')

    const nextDraft = { ...draft, world: 'x'.repeat(9000) }
    expect(validateDraft(nextDraft).filter((e) => e.tab === 'world')).toHaveLength(0)
  })
})
