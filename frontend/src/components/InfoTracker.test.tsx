import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { InfoTracker } from './InfoTracker'
import { t } from '../i18n'
import type { CastMember, MindView } from '../api'

const aiko: CastMember = { id: 'aiko', name: 'Aiko' }
const chloe: CastMember = { id: 'chloe', name: 'Chloe' }

function mind(overrides: Partial<MindView> = {}): MindView {
  return { attitude: 'desconfiada, mas curiosa', emoji: '🤨', event: 'viu você pegar o caderno', ...overrides }
}

describe('InfoTracker', () => {
  it('renders one row per cast member with emoji, name, attitude and last event', () => {
    render(<InfoTracker cast={[chloe]} minds={{ chloe: mind() }} />)

    expect(screen.getByText('🤨')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByText('Chloe')).toBeInTheDocument()
    expect(screen.getByText('desconfiada, mas curiosa')).toBeInTheDocument()
    expect(screen.getByText(t('game.info.event', { event: 'viu você pegar o caderno' }))).toBeInTheDocument()
  })

  it('follows the cast order, not the minds map order', () => {
    const { container } = render(
      <InfoTracker
        cast={[aiko, chloe]}
        minds={{ chloe: mind({ attitude: 'curiosa' }), aiko: mind({ attitude: 'neutra' }) }}
      />,
    )
    const names = Array.from(container.querySelectorAll('.info__name')).map((el) => el.textContent)
    expect(names).toEqual(['Aiko', 'Chloe'])
  })

  it('ignores minds entries for characters that left the scene', () => {
    render(<InfoTracker cast={[aiko]} minds={{ aiko: mind(), chloe: mind() }} />)
    expect(screen.queryByText('Chloe')).toBeNull()
  })

  it('shows game.info.unknown for a cast member without a mind yet', () => {
    render(<InfoTracker cast={[aiko, chloe]} minds={{ aiko: mind() }} />)
    expect(screen.getByText(t('game.info.unknown'))).toBeInTheDocument()
    expect(screen.getByText('desconfiada, mas curiosa')).toBeInTheDocument()
  })

  it('shows game.info.pending when nobody in the cast has been read', () => {
    render(<InfoTracker cast={[aiko, chloe]} minds={{}} />)
    expect(screen.getByText(t('game.info.pending'))).toBeInTheDocument()
  })

  it('shows game.cast.empty when the cast is empty', () => {
    render(<InfoTracker cast={[]} minds={{}} />)
    expect(screen.getByText(t('game.cast.empty'))).toBeInTheDocument()
  })

  it('renders nothing when cast is null', () => {
    const { container } = render(<InfoTracker cast={null} minds={{}} />)
    expect(container.firstChild).toBeNull()
  })

  it('falls back to the id when name is empty', () => {
    render(<InfoTracker cast={[{ id: 'unknown-1', name: '' }]} minds={{ 'unknown-1': mind() }} />)
    expect(screen.getByText('unknown-1')).toBeInTheDocument()
  })

  it('omits the event line when the event field is empty', () => {
    render(<InfoTracker cast={[chloe]} minds={{ chloe: mind({ event: '' }) }} />)
    expect(screen.queryByText(/^Último:/)).toBeNull()
    expect(screen.queryByText(/^Last:/)).toBeNull()
  })

  it('exposes the disclosure as a summary reachable by keyboard and starts open', () => {
    const { container } = render(<InfoTracker cast={[chloe]} minds={{ chloe: mind() }} />)
    expect(screen.getByText(t('game.info.label')).closest('summary')).not.toBeNull()
    expect(container.querySelector('details')).toHaveAttribute('open')
  })

  it('applies aria-busy when busy', () => {
    render(<InfoTracker cast={[chloe]} minds={{ chloe: mind() }} busy />)
    const group = screen.getByRole('group', { name: t('game.info.regionLabel') })
    expect(group).toHaveAttribute('aria-busy', 'true')
  })
})
