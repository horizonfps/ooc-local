import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CommandPalette } from './CommandPalette'
import { t } from '../i18n'
import type { CommandView } from '../api'

const COMMANDS: CommandView[] = [
  { name: 'fofoca', description: 'O que andam dizendo pelas costas', scope: 'scenario' },
  { name: 'inventario', description: 'Seus itens', scope: 'scenario' },
  { name: 'diary', description: 'Diário do jogador sobre o dia', scope: 'global' },
]

function renderPalette(props: Partial<React.ComponentProps<typeof CommandPalette>> = {}) {
  return render(
    <CommandPalette
      commands={COMMANDS}
      query="!"
      activeIndex={0}
      listboxId="palette"
      optionId={(i) => `palette-option-${i}`}
      onPick={() => {}}
      {...props}
    />,
  )
}

describe('CommandPalette', () => {
  it('renders one option per command with the sigil, the name and the description', () => {
    renderPalette({ commands: [COMMANDS[0], COMMANDS[1]] })

    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(2)
    expect(screen.getByText('!fofoca')).toBeInTheDocument()
    expect(screen.getByText('O que andam dizendo pelas costas')).toBeInTheDocument()
  })

  it('filters by prefix as the query grows', () => {
    renderPalette({ query: '!fo' })

    expect(screen.getAllByRole('option')).toHaveLength(1)
    expect(screen.getByText('!fofoca')).toBeInTheDocument()
  })

  it('marks the active option with aria-selected', () => {
    renderPalette({ commands: [COMMANDS[0], COMMANDS[1]], activeIndex: 1 })

    const options = screen.getAllByRole('option')
    expect(options[0]).toHaveAttribute('aria-selected', 'false')
    expect(options[1]).toHaveAttribute('aria-selected', 'true')
  })

  it('shows only scenario commands under ! and only global ones under /', () => {
    const { unmount } = renderPalette({ query: '!' })
    expect(screen.getByText('!fofoca')).toBeInTheDocument()
    expect(screen.getByText('!inventario')).toBeInTheDocument()
    expect(screen.queryByText('/diary')).toBeNull()
    unmount()

    renderPalette({ query: '/' })
    expect(screen.getByText('/diary')).toBeInTheDocument()
    expect(screen.queryByText('!fofoca')).toBeNull()
  })

  it('matches case-insensitively', () => {
    renderPalette({ query: '!FO' })

    expect(screen.getAllByRole('option')).toHaveLength(1)
    expect(screen.getByText('!fofoca')).toBeInTheDocument()
  })

  it('shows game.commands.noMatch and no listbox when nothing matches', () => {
    renderPalette({ query: '!zzz' })

    expect(screen.queryByRole('listbox')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent(t('game.commands.noMatch'))
  })

  it('shows game.commands.emptyScenario when the scenario has no commands', () => {
    const { unmount } = renderPalette({ commands: [COMMANDS[2]], query: '!' })
    expect(screen.getByRole('status')).toHaveTextContent(t('game.commands.emptyScenario'))
    unmount()

    renderPalette({ commands: [COMMANDS[0]], query: '/' })
    expect(screen.getByRole('status')).toHaveTextContent(t('game.commands.emptyGlobal'))
  })

  it('calls onPick with the command when an option is clicked', async () => {
    const user = userEvent.setup()
    const onPick = vi.fn()
    renderPalette({ commands: [COMMANDS[0]], onPick })

    await user.click(screen.getByRole('option'))
    expect(onPick).toHaveBeenCalledWith(COMMANDS[0])
  })

  it('does not blur the textarea when an option is pressed', () => {
    render(
      <>
        <input aria-label="side input" autoFocus />
        <CommandPalette
          commands={[COMMANDS[0]]}
          query="!"
          activeIndex={0}
          listboxId="palette"
          optionId={(i) => `palette-option-${i}`}
          onPick={() => {}}
        />
      </>,
    )
    const input = screen.getByRole('textbox', { name: 'side input' })
    input.focus()
    const option = screen.getByRole('option')
    const event = new MouseEvent('mousedown', { bubbles: true, cancelable: true })
    option.dispatchEvent(event)

    expect(document.activeElement).toBe(input)
  })
})
