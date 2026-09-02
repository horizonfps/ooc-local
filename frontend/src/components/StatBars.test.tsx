import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { StatBars } from './StatBars'
import { t } from '../i18n'
import type { StatView } from '../api'

function stat(overrides: Partial<StatView> = {}): StatView {
  return {
    id: 'reputacao',
    name: 'Reputação',
    icon: '⭐',
    color: null,
    value: 55,
    min: 0,
    max: 100,
    level: null,
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('StatBars', () => {
  it('renders one row per StatView with name, value/max and the level line', () => {
    const stats = [
      stat({ id: 'reputacao', name: 'Reputação', value: 55, max: 100, level: 'Você é um aluno comum.' }),
      stat({ id: 'energia', name: 'Energia', icon: '⚡', value: 80, max: 100, level: null }),
    ]
    render(<StatBars stats={stats} />)

    expect(screen.getByText('Reputação')).toBeInTheDocument()
    expect(screen.getByText('Energia')).toBeInTheDocument()
    expect(screen.getByText(t('hud.stat.value', { value: 55, max: 100 }))).toBeInTheDocument()
    expect(screen.getByText(t('hud.stat.value', { value: 80, max: 100 }))).toBeInTheDocument()
    expect(screen.getByText(t('hud.stat.level', { level: 'Você é um aluno comum.' }))).toBeInTheDocument()
  })

  it('fills the bar proportionally to min and max', () => {
    const { container } = render(<StatBars stats={[stat({ min: -50, max: 50, value: 0 })]} />)
    const fill = container.querySelector('.statBars__fill') as HTMLElement
    expect(fill.style.width).toBe('50%')
  })

  it('applies the author color to the fill and leaves it to the CSS when color is null', () => {
    const { container, rerender } = render(<StatBars stats={[stat({ color: '#f5c542' })]} />)
    const fill = container.querySelector('.statBars__fill') as HTMLElement
    expect(fill.style.background).toContain('rgb(245, 197, 66)')

    rerender(<StatBars stats={[stat({ color: null })]} />)
    const fillNoColor = container.querySelector('.statBars__fill') as HTMLElement
    expect(fillNoColor.style.background).toBe('')
  })

  it('clamps the fill to 0% and 100% but prints the raw value', () => {
    const { container } = render(<StatBars stats={[stat({ value: 150, max: 100, min: 0 })]} />)
    const fill = container.querySelector('.statBars__fill') as HTMLElement
    expect(fill.style.width).toBe('100%')
    expect(screen.getByText(t('hud.stat.value', { value: 150, max: 100 }))).toBeInTheDocument()
  })

  it('renders without a NaN width when max equals min', () => {
    const { container } = render(<StatBars stats={[stat({ min: 5, max: 5, value: 5 })]} />)
    const fill = container.querySelector('.statBars__fill') as HTMLElement
    expect(fill.style.width).toBe('0%')
  })

  it('omits the level line but keeps the row height when level is null', () => {
    const { container } = render(<StatBars stats={[stat({ level: null })]} />)
    expect(container.querySelector('.statBars__level')).toBeNull()
    expect(container.querySelector('.statBars__levelSlot')).not.toBeNull()
  })

  it('renders nothing when stats is an empty list', () => {
    const { container } = render(<StatBars stats={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when stats is null', () => {
    const { container } = render(<StatBars stats={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('highlights only the stat whose value changed and clears it after 600ms', () => {
    vi.useFakeTimers()
    const stats = [stat({ id: 'reputacao', value: 55 }), stat({ id: 'energia', name: 'Energia', value: 80 })]
    const { rerender, container } = render(<StatBars stats={stats} />)

    act(() => {
      rerender(<StatBars stats={[stats[0], { ...stats[1], value: 90 }]} />)
    })

    const reputacao = container.querySelector('[data-stat="reputacao"]')
    const energia = container.querySelector('[data-stat="energia"]')
    expect(reputacao?.className).not.toContain('statBars__item--highlight')
    expect(energia?.className).toContain('statBars__item--highlight')

    act(() => {
      vi.advanceTimersByTime(600)
    })
    expect(energia?.className).not.toContain('statBars__item--highlight')
  })

  it('highlights by id, not by position', () => {
    vi.useFakeTimers()
    const stats = [stat({ id: 'reputacao', value: 55 }), stat({ id: 'energia', name: 'Energia', value: 80 })]
    const { rerender, container } = render(<StatBars stats={stats} />)

    act(() => {
      rerender(<StatBars stats={[stat({ id: 'dinamico', name: 'Dinâmico', value: 1 }), ...stats]} />)
    })

    const reputacao = container.querySelector('[data-stat="reputacao"]')
    const energia = container.querySelector('[data-stat="energia"]')
    const dinamico = container.querySelector('[data-stat="dinamico"]')
    expect(reputacao?.className).not.toContain('statBars__item--highlight')
    expect(energia?.className).not.toContain('statBars__item--highlight')
    expect(dinamico?.className).not.toContain('statBars__item--highlight')
  })

  it('does not warn about setState after unmount while the highlight timer is pending', () => {
    vi.useFakeTimers()
    const stats = [stat({ id: 'reputacao', value: 55 })]
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { rerender, unmount } = render(<StatBars stats={stats} />)
    act(() => {
      rerender(<StatBars stats={[{ ...stats[0], value: 60 }]} />)
    })
    unmount()
    act(() => {
      vi.advanceTimersByTime(600)
    })
    expect(errorSpy).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('hides the icon and the bar from assistive tech', () => {
    const { container } = render(<StatBars stats={[stat()]} />)
    expect(container.querySelector('.statBars__icon')).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('.statBars__track')).toHaveAttribute('aria-hidden', 'true')
  })

  it('has no focusable or interactive elements', () => {
    const { container } = render(<StatBars stats={[stat()]} />)
    expect(container.querySelectorAll('button, a, input, [tabindex]')).toHaveLength(0)
  })

  it('applies aria-busy on the group when busy', () => {
    render(<StatBars stats={[stat()]} busy />)
    const group = screen.getByRole('group', { name: t('hud.stats.regionLabel') })
    expect(group).toHaveAttribute('aria-busy', 'true')
  })

  it('does not render a second stale sentence', () => {
    render(<StatBars stats={[stat()]} stale />)
    expect(screen.queryByText(t('hud.stale'))).toBeNull()
  })
})
