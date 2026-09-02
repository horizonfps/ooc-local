import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { CommandsTab } from './CommandsTab'
import { validateDraft } from '../../builder/validate'
import type { BuilderDraft } from '../../screens/BuilderEditorScreen'
import type { CommandDoc } from '../../api'
import { t } from '../../i18n'

function command(overrides: Partial<CommandDoc> = {}): CommandDoc {
  return {
    name: 'fofoca',
    description: 'O que andam dizendo',
    prompt: 'Fora da narrativa, liste o que os NPCs estao comentando.',
    ...overrides,
  }
}

function baseDraft(commands: CommandDoc[] = [command()]): BuilderDraft {
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
    stats: [],
    lorebook: {},
    commands,
  }
}

function Harness(props: { initial: BuilderDraft }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return (
    <>
      <CommandsTab scenarioId="school" draft={draft} onChange={setDraft} errors={errors} goToTab={() => {}} />
      <pre data-testid="commands-debug">{JSON.stringify(draft.commands)}</pre>
    </>
  )
}

function commandsDebug(): CommandDoc[] {
  return JSON.parse(screen.getByTestId('commands-debug').textContent ?? '[]')
}

describe('CommandsTab', () => {
  it('writes the name, description and prompt into the draft', () => {
    render(<Harness initial={baseDraft([command({ name: '', description: '', prompt: '' })])} />)

    fireEvent.change(screen.getByLabelText(t('builder.commands.name')), { target: { value: 'fofoca' } })
    fireEvent.change(screen.getByLabelText(t('builder.commands.description')), { target: { value: 'O que andam dizendo' } })
    fireEvent.change(screen.getByLabelText(t('builder.commands.prompt')), {
      target: { value: 'Fora da narrativa, liste o que os NPCs estao comentando.' },
    })

    expect(commandsDebug()).toEqual([
      { name: 'fofoca', description: 'O que andam dizendo', prompt: 'Fora da narrativa, liste o que os NPCs estao comentando.' },
    ])
  })

  it('creates a command with a free suggested name and focuses the name', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft([command({ name: 'command-1' })])} />)

    await user.click(screen.getByRole('button', { name: t('builder.commands.create') }))

    const commands = commandsDebug()
    expect(commands[1]).toEqual({ name: 'command-2', description: '', prompt: '' })
    await waitFor(() => {
      expect(document.getElementById('builder-field-commands.1.name')).toBe(document.activeElement)
    })
  })

  it('selects another command from the list, announces and focuses the name', async () => {
    const user = userEvent.setup()
    const draft = baseDraft([command({ name: 'fofoca' }), command({ name: 'recapitulacao' })])
    render(<Harness initial={draft} />)

    await user.click(screen.getAllByRole('button', { name: /recapitulacao/ })[0])

    await waitFor(() => {
      expect(document.getElementById('builder-field-commands.1.name')).toBe(document.activeElement)
    })
    expect(screen.getByText(t('builder.detail.selected', { name: 'recapitulacao' }))).toBeInTheDocument()
  })

  it('shows the !name invocation live', () => {
    render(<Harness initial={baseDraft([command({ name: '' })])} />)

    const nameInput = screen.getByLabelText(t('builder.commands.name'))
    const invocation = () =>
      (document.querySelector('.builder-commands-detail .builder-commands-invocation') as HTMLElement).textContent

    expect(invocation()).toBe(t('builder.commands.invocation.empty'))

    fireEvent.change(nameInput, { target: { value: 'fofoca' } })
    expect(invocation()).toBe(t('builder.commands.invocation', { name: 'fofoca' }))

    fireEvent.change(nameInput, { target: { value: '' } })
    expect(invocation()).toBe(t('builder.commands.invocation.empty'))
  })

  it('removes a command and moves focus to the one that took its place', async () => {
    const user = userEvent.setup()
    const draft = baseDraft([command({ name: 'a' }), command({ name: 'b' }), command({ name: 'c' })])
    render(<Harness initial={draft} />)

    await user.click(screen.getByRole('button', { name: t('builder.commands.remove.title', { name: 'b' }) }))

    expect(commandsDebug()).toEqual([command({ name: 'a' }), command({ name: 'c' })])
    await waitFor(() => {
      expect(document.getElementById('builder-commands-listItem-1')).toBe(document.activeElement)
    })
    expect((document.getElementById('builder-field-commands.0.name') as HTMLInputElement).value).toBe('a')
    expect(screen.getByText(t('builder.commands.removed', { name: 'b' }))).toBeInTheDocument()
  })

  it('shows the empty state with the invocation hints', () => {
    render(<Harness initial={baseDraft([])} />)

    expect(screen.getByText(t('builder.commands.empty.title'))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('builder.commands.create') })).toBeInTheDocument()
    expect(screen.getByText(t('builder.commands.playGuideHint'))).toBeInTheDocument()
    expect(screen.getByText(t('builder.commands.globalsHint'))).toBeInTheDocument()
  })

  it('removes the only command and moves focus to the create button', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft([command({ name: 'fofoca' })])} />)

    await user.click(screen.getByRole('button', { name: t('builder.commands.remove.title', { name: 'fofoca' }) }))

    expect(await screen.findByText(t('builder.commands.empty.title'))).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: t('builder.commands.create') })).toBe(document.activeElement)
    })
  })

  it('trims the name on blur and keeps the prompt byte for byte', () => {
    render(<Harness initial={baseDraft([command({ name: '', prompt: '' })])} />)

    const nameInput = screen.getByLabelText(t('builder.commands.name'))
    fireEvent.change(nameInput, { target: { value: '  fofoca  ' } })
    fireEvent.blur(nameInput)

    const promptInput = screen.getByLabelText(t('builder.commands.prompt'))
    fireEvent.change(promptInput, { target: { value: 'Line one\nLine two  ' } })

    const commands = commandsDebug()
    expect(commands[0].name).toBe('fofoca')
    expect(commands[0].prompt).toBe('Line one\nLine two  ')
  })

  it('marks a non-selected command with an error in the list', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft([command({ name: 'a' }), command({ name: 'b', prompt: '' })])} />)

    // mounts on the invalid (second) command; switch to the valid one to isolate the marker
    await user.click(document.getElementById('builder-commands-listItem-0') as HTMLElement)

    const invalidMarkers = screen.getAllByText(t('builder.starts.itemInvalid'))
    expect(invalidMarkers).toHaveLength(1)
    const invalidItem = invalidMarkers[0].closest('li')
    expect(invalidItem).toHaveClass('is-invalid')
    expect(invalidItem).not.toHaveClass('is-selected')
  })

  it('opens selecting the first command with an error', () => {
    render(
      <Harness
        initial={baseDraft([command({ name: 'a' }), command({ name: 'b' }), command({ name: 'c', prompt: '' })])}
      />,
    )

    expect(document.getElementById('builder-field-commands.2.name')).toBeInTheDocument()
  })

  it('shows the invocation as text, not as a button', () => {
    render(<Harness initial={baseDraft([command({ name: 'fofoca' })])} />)

    expect(screen.queryByRole('button', { name: /^!fofoca$/ })).toBeNull()
    const invocation = document.querySelector('.builder-commands-detail .builder-commands-invocation') as HTMLElement
    expect(invocation.tagName).toBe('P')
    expect(invocation).not.toHaveAttribute('tabindex')
  })

  it('flags a name with a forbidden character', () => {
    render(<Harness initial={baseDraft([command({ name: '' })])} />)

    const nameInput = screen.getByLabelText(t('builder.commands.name'))
    fireEvent.change(nameInput, { target: { value: 'Fofoca Geral' } })

    const message = screen.getByText(t('builder.field.slugUnderscoreInvalid'))
    expect(message).toHaveAttribute('role', 'alert')
    expect(nameInput).toHaveAttribute('aria-invalid', 'true')
    expect(nameInput.getAttribute('aria-describedby')).toContain(message.id)
  })

  it('accepts underscore in the name', () => {
    render(<Harness initial={baseDraft([command({ name: '' })])} />)

    fireEvent.change(screen.getByLabelText(t('builder.commands.name')), { target: { value: 'boca_de_sino' } })

    expect(screen.queryByText(t('builder.field.slugUnderscoreInvalid'))).toBeNull()
    expect(screen.queryByText(t('builder.field.required'))).toBeNull()
  })

  it('flags a duplicated name on the second command', () => {
    render(<Harness initial={baseDraft([command({ name: 'fofoca' }), command({ name: 'fofoca' })])} />)

    expect(screen.getByText(t('builder.field.slugTaken', { slug: 'fofoca' }))).toBeInTheDocument()
    // mounts on the invalid (second) command, per the first-error-wins initial selection rule
    expect(screen.getByLabelText(t('builder.commands.name'))).toHaveAttribute('aria-invalid', 'true')
  })

  it('flags an empty prompt', () => {
    render(<Harness initial={baseDraft([command({ prompt: '' })])} />)

    const message = screen.getByText(t('builder.field.required'))
    expect(message).toHaveAttribute('role', 'alert')
    const promptInput = screen.getByLabelText(t('builder.commands.prompt'))
    expect(promptInput.getAttribute('aria-describedby')).toContain(message.id)
  })
})
