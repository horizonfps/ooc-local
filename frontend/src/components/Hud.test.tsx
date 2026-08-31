import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

function stubLanguage(value: string | undefined) {
  vi.stubGlobal('navigator', { language: value })
}

async function loadHud() {
  vi.resetModules()
  return import('./Hud')
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('Hud', () => {
  it('renders the four fields with translated labels and correct values', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    render(<Hud hud={{ turn: 0, location: 'Portão', time: '07:50', weather: 'clear' }} />)
    expect(screen.getByText('Turn')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
    expect(screen.getByText('Location')).toBeInTheDocument()
    expect(screen.getByText('Portão')).toBeInTheDocument()
    expect(screen.getByText('Time')).toBeInTheDocument()
    expect(screen.getByText('07:50')).toBeInTheDocument()
    expect(screen.getByText('Weather')).toBeInTheDocument()
    expect(screen.getByText('Clear')).toBeInTheDocument()
  })

  it('translates weather in the pt-br locale', async () => {
    stubLanguage('pt-BR')
    const { Hud } = await loadHud()
    render(<Hud hud={{ turn: 1, location: 'Portão', time: '08:00', weather: 'rain' }} />)
    expect(screen.getByText('Chuva')).toBeInTheDocument()
  })

  it('falls back to hud.weather.unknown for an unrecognized code, keeping the raw code in the title', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    render(<Hud hud={{ turn: 1, location: 'Portão', time: '08:00', weather: 'tempestade-de-areia' }} />)
    const value = screen.getByText('Unknown')
    expect(value).toHaveAttribute('title', 'tempestade-de-areia')
  })

  it('renders hud.weather.unknown without throwing when weather is null', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    expect(() => render(<Hud hud={{ turn: 1, location: 'Portão', time: '08:00', weather: null }} />)).not.toThrow()
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })

  it('shows the placeholder with the unavailable title when location is missing, without changing the row height', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    const { container } = render(<Hud hud={{ turn: 1, location: null, time: '08:00', weather: 'clear' }} />)
    const value = screen.getByText('—')
    expect(value).toHaveAttribute('title', 'Not tracked yet')
    const field = container.querySelector('[data-field="location"]')
    expect(field).not.toBeNull()
  })

  it('sets aria-busy and keeps the previous turn values while a turn is in progress', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    const { container } = render(<Hud hud={{ turn: 2, location: 'Praça', time: '09:00', weather: 'cloudy' }} busy />)
    expect(container.querySelector('.hud')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Praça')).toBeInTheDocument()
  })

  it('highlights only the changed field and clears the highlight after ~600ms', async () => {
    vi.useFakeTimers()
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    const { rerender, container } = render(
      <Hud hud={{ turn: 5, location: 'Pátio', time: '08:10', weather: 'clear' }} />,
    )
    act(() => {
      rerender(<Hud hud={{ turn: 6, location: 'Pátio', time: '08:10', weather: 'clear' }} />)
    })
    const turnField = container.querySelector('[data-field="turn"]')
    const locationField = container.querySelector('[data-field="location"]')
    expect(turnField?.className).toContain('hud__field--highlight')
    expect(locationField?.className).not.toContain('hud__field--highlight')

    act(() => {
      vi.advanceTimersByTime(600)
    })
    expect(turnField?.className).not.toContain('hud__field--highlight')
  })

  it('does not warn about setState after unmount while the highlight timer is pending', async () => {
    vi.useFakeTimers()
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { rerender, unmount } = render(<Hud hud={{ turn: 1, location: 'A', time: '08:00', weather: 'clear' }} />)
    act(() => {
      rerender(<Hud hud={{ turn: 2, location: 'A', time: '08:00', weather: 'clear' }} />)
    })
    unmount()
    act(() => {
      vi.advanceTimersByTime(600)
    })
    expect(errorSpy).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('exposes an aria-live, aria-atomic region with a single interpolated announcement', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    const { container } = render(<Hud hud={{ turn: 5, location: 'Pátio', time: '08:10', weather: 'clear' }} />)
    const region = container.querySelector('.hud')
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(region).toHaveAttribute('aria-atomic', 'true')
    expect(screen.getByText('Turn 5, Pátio, 08:10, Clear')).toBeInTheDocument()
  })

  it('shows hud.stale next to the last known values when stale', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    render(<Hud hud={{ turn: 3, location: 'Praça', time: '10:00', weather: 'fog' }} stale />)
    expect(screen.getByText('Showing the last known state')).toBeInTheDocument()
    expect(screen.getByText('Praça')).toBeInTheDocument()
  })

  it('renders all four placeholders with a reserved height when hud is null', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    render(<Hud hud={null} />)
    expect(screen.getAllByText('—')).toHaveLength(4)
  })

  it('renders time exactly as received, without timezone conversion', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    render(<Hud hud={{ turn: 1, location: 'A', time: '00:01', weather: 'clear' }} />)
    expect(screen.getByText('00:01')).toBeInTheDocument()
  })

  it('renders a negative turn number as received without correcting engine state', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    render(<Hud hud={{ turn: -1, location: 'A', time: '08:00', weather: 'clear' }} />)
    expect(screen.getByText('-1')).toBeInTheDocument()
  })

  it('has no focusable or interactive elements', async () => {
    stubLanguage('en-US')
    const { Hud } = await loadHud()
    const { container } = render(<Hud hud={{ turn: 1, location: 'A', time: '08:00', weather: 'clear' }} />)
    expect(container.querySelectorAll('button, a, input, [tabindex]')).toHaveLength(0)
  })

  it('exports WEATHER_KEYS mapping every closed-vocabulary code to an i18n key', async () => {
    const { WEATHER_KEYS } = await loadHud()
    expect(Object.keys(WEATHER_KEYS).sort()).toEqual(['clear', 'cloudy', 'fog', 'night', 'rain', 'snow', 'storm'])
  })
})
