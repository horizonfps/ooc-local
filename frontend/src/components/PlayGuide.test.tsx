import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PlayGuide } from './PlayGuide'
import { t } from '../i18n'
import type { CommandView } from '../api'

const COMMANDS: CommandView[] = [
  { name: 'fofoca', description: 'O que andam dizendo pelas costas', scope: 'scenario' },
  { name: 'diary', description: 'Diário do jogador sobre o dia', scope: 'global' },
]

describe('PlayGuide', () => {
  it('renders the guide prose and one entry per command', () => {
    render(<PlayGuide playGuide="Você é aluno novo." commands={COMMANDS} />)

    expect(screen.getByText('Você é aluno novo.')).toBeInTheDocument()
    expect(screen.getByText('!fofoca')).toBeInTheDocument()
    expect(screen.getByText('O que andam dizendo pelas costas')).toBeInTheDocument()
    expect(screen.getByText('/diary')).toBeInTheDocument()
    expect(screen.getByText('Diário do jogador sobre o dia')).toBeInTheDocument()
    expect(screen.getByText(t('game.commands.hint'))).toBeInTheDocument()
  })

  it('renders without the command section when commands is empty', () => {
    render(<PlayGuide playGuide="Você é aluno novo." commands={[]} />)

    expect(screen.getByText('Você é aluno novo.')).toBeInTheDocument()
    expect(screen.queryByText(t('game.commands.listLabel'))).toBeNull()
    expect(screen.queryByText(t('game.commands.hint'))).toBeNull()
  })

  it('renders without the prose when playGuide is null', () => {
    render(<PlayGuide playGuide={null} commands={COMMANDS} />)

    expect(screen.getByText('!fofoca')).toBeInTheDocument()
    expect(screen.getByText(t('game.commands.listLabel'))).toBeInTheDocument()
  })

  it('renders nothing when there is neither guide nor commands', () => {
    const { container } = render(<PlayGuide playGuide={null} commands={[]} />)

    expect(container.firstChild).toBeNull()
  })

  it('starts open with a summary reachable by keyboard', () => {
    render(<PlayGuide playGuide="Você é aluno novo." commands={COMMANDS} />)

    const summary = screen.getByText(t('game.guide.label'))
    expect(summary.closest('details')).toHaveAttribute('open')
  })
})
