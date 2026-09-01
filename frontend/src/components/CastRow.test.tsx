import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CastRow } from './CastRow'
import { t } from '../i18n'

describe('CastRow', () => {
  it('renders one chip per cast member and the label', () => {
    render(<CastRow cast={[{ id: 'aiko', name: 'Aiko' }, { id: 'cydonia', name: 'Cydonia' }]} />)

    expect(screen.getByText(t('game.cast.label'))).toBeInTheDocument()
    expect(screen.getByText('Aiko')).toBeInTheDocument()
    expect(screen.getByText('Cydonia')).toBeInTheDocument()
  })

  it('shows the empty chip when cast is an empty list', () => {
    render(<CastRow cast={[]} />)

    expect(screen.getByText(t('game.cast.empty'))).toBeInTheDocument()
  })

  it('shows the placeholder with the unavailable title when cast is null', () => {
    render(<CastRow cast={null} />)

    const chip = screen.getByText(t('hud.placeholder'))
    expect(chip).toHaveAttribute('title', t('game.cast.unavailable'))
  })

  it('applies aria-busy and exposes a labelled group when busy', () => {
    render(<CastRow cast={[{ id: 'aiko', name: 'Aiko' }]} busy />)

    const group = screen.getByRole('group', { name: t('game.cast.regionLabel') })
    expect(group).toHaveAttribute('aria-busy', 'true')
  })

  it('falls back to the id when name is empty', () => {
    render(<CastRow cast={[{ id: 'unknown-1', name: '' }]} />)

    expect(screen.getByText('unknown-1')).toBeInTheDocument()
  })
})
