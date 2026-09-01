import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
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
        play_guide: null,
        suggestions: [],
        hud: { location: 'Hallway', time: '08:00', weather: 'clear' },
        characters: [],
      },
    },
    characters: {},
  }
}

function Harness(props: { initial: BuilderDraft }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return <WorldTab scenarioId="school" draft={draft} onChange={setDraft} errors={errors} goToTab={() => {}} />
}

describe('WorldTab', () => {
  it('filling the guided fields updates world with the canonical headings', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    const toneInput = screen.getByLabelText(t('builder.world.tone'))
    await user.type(toneInput, 'Grim and quiet.')

    expect(screen.getByLabelText(t('builder.world.universe'))).toHaveValue('A dusty old school.')
    const universeInput = screen.getByLabelText(t('builder.world.universe')) as HTMLTextAreaElement
    expect(universeInput.value).toContain('A dusty old school.')
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
})
