import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ModeSelector } from './ModeSelector'
import type { InputMode } from '../api'
import { t } from '../i18n'

describe('ModeSelector', () => {
  it('renders a radiogroup with the three modes and checks the current one', () => {
    render(<ModeSelector value="do" onChange={vi.fn()} name="mode-a" />)

    expect(screen.getByRole('radiogroup', { name: t('game.mode.regionLabel') })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: t('game.mode.do') })).toBeChecked()
    expect(screen.getByRole('radio', { name: t('game.mode.say') })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: t('game.mode.story') })).not.toBeChecked()
  })

  it('calls onChange when another mode is picked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ModeSelector value="do" onChange={onChange} name="mode-b" />)

    await user.click(screen.getByRole('radio', { name: t('game.mode.say') }))

    expect(onChange).toHaveBeenCalledWith('say')
  })

  it('moves the selection with the arrow keys', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ModeSelector value="do" onChange={onChange} name="mode-c" />)

    screen.getByRole('radio', { name: t('game.mode.do') }).focus()
    await user.keyboard('{ArrowRight}')

    expect(onChange).toHaveBeenCalledWith('say')
  })

  it('shows the hint of the selected mode', () => {
    render(<ModeSelector value="say" onChange={vi.fn()} name="mode-d" />)

    const hint = screen.getByText(t('game.mode.say.hint'))
    expect(hint).toBeInTheDocument()
    const group = screen.getByRole('radiogroup', { name: t('game.mode.regionLabel') })
    expect(group).toHaveAttribute('aria-describedby', hint.id)
  })

  it('disables the three radios when disabled', () => {
    render(<ModeSelector value="do" onChange={vi.fn()} name="mode-e" disabled />)

    expect(screen.getByRole('radio', { name: t('game.mode.do') })).toBeDisabled()
    expect(screen.getByRole('radio', { name: t('game.mode.say') })).toBeDisabled()
    expect(screen.getByRole('radio', { name: t('game.mode.story') })).toBeDisabled()
  })

  it('isolates two instances that get different names', async () => {
    const user = userEvent.setup()
    function TwoPanels() {
      const [a, setA] = useState<InputMode>('do')
      const [b, setB] = useState<InputMode>('do')
      return (
        <>
          <ModeSelector value={a} onChange={setA} name="panel-a" />
          <ModeSelector value={b} onChange={setB} name="panel-b" />
        </>
      )
    }
    render(<TwoPanels />)

    const sayRadios = screen.getAllByRole('radio', { name: t('game.mode.say') })
    await user.click(sayRadios[0])

    expect(sayRadios[0]).toBeChecked()
    expect(sayRadios[1]).not.toBeChecked()
  })
})
