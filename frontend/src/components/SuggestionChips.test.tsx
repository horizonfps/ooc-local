import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SuggestionChips } from './SuggestionChips'
import { t } from '../i18n'

describe('SuggestionChips', () => {
  it('renders one chip per suggestion with the text as the button label', () => {
    render(<SuggestionChips suggestions={['Pegar o caderno', 'Perguntar para a Chloe']} onSend={vi.fn()} onEdit={vi.fn()} />)

    expect(screen.getByRole('button', { name: t('game.suggest.send.aria', { text: 'Pegar o caderno' }) })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('game.suggest.send.aria', { text: 'Perguntar para a Chloe' }) })).toBeInTheDocument()
  })

  it('calls onSend with the exact suggestion text', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<SuggestionChips suggestions={['Pegar o caderno']} onSend={onSend} onEdit={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: t('game.suggest.send.aria', { text: 'Pegar o caderno' }) }))

    expect(onSend).toHaveBeenCalledWith('Pegar o caderno')
  })

  it('calls onEdit with the exact text', async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()
    render(<SuggestionChips suggestions={['Pegar o caderno', 'Perguntar para a Chloe']} onSend={vi.fn()} onEdit={onEdit} />)

    await user.click(screen.getByRole('button', { name: t('game.suggest.edit.aria', { text: 'Perguntar para a Chloe' }) }))

    expect(onEdit).toHaveBeenCalledWith('Perguntar para a Chloe')
  })

  it('gives each edit button a distinct accessible name', () => {
    render(<SuggestionChips suggestions={['A', 'B', 'C']} onSend={vi.fn()} onEdit={vi.fn()} />)

    const names = ['A', 'B', 'C'].map(
      (text) => screen.getByRole('button', { name: t('game.suggest.edit.aria', { text }) }).getAttribute('aria-label'),
    )
    expect(new Set(names).size).toBe(3)
  })

  it('renders nothing for an empty list', () => {
    const { container } = render(<SuggestionChips suggestions={[]} onSend={vi.fn()} onEdit={vi.fn()} />)

    expect(container.firstChild).toBeNull()
  })

  it('drops whitespace-only entries', () => {
    render(<SuggestionChips suggestions={['a', '   ', 'b']} onSend={vi.fn()} onEdit={vi.fn()} />)

    expect(screen.getByRole('button', { name: t('game.suggest.send.aria', { text: 'a' }) })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('game.suggest.send.aria', { text: 'b' }) })).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(4)
  })

  it('renders at most three chips', () => {
    render(<SuggestionChips suggestions={['a', 'b', 'c', 'd', 'e']} onSend={vi.fn()} onEdit={vi.fn()} />)

    expect(screen.getAllByRole('button')).toHaveLength(6)
    expect(screen.getByRole('button', { name: t('game.suggest.send.aria', { text: 'a' }) })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('game.suggest.send.aria', { text: 'c' }) })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t('game.suggest.send.aria', { text: 'd' }) })).toBeNull()
  })

  it('keeps a long suggestion whole', () => {
    const long = 'x'.repeat(120)
    render(<SuggestionChips suggestions={[long]} onSend={vi.fn()} onEdit={vi.fn()} />)

    expect(screen.getByRole('button', { name: t('game.suggest.send.aria', { text: long }) })).toBeInTheDocument()
  })

  it('exposes the block as a labelled group', () => {
    render(<SuggestionChips suggestions={['a']} onSend={vi.fn()} onEdit={vi.fn()} />)

    expect(screen.getByRole('group', { name: t('game.suggest.regionLabel') })).toBeInTheDocument()
  })
})
