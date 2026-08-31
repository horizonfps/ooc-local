import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GameScreen } from './GameScreen'
import { t } from '../i18n'
import type { SessionDetail } from '../api'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function session(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    id: 'sess-1',
    scenarioId: 'school',
    scenarioName: 'The School',
    prologue: 'Once upon a time.',
    playGuide: null,
    turns: [],
    hud: { turn: 0, location: 'Hallway', time: 'Night', weather: 'clear' },
    ...overrides,
  }
}

function mockFetch(handler: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(async () => handler())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  location.hash = ''
  document.title = 'ooc-local'
})

afterEach(() => {
  vi.unstubAllGlobals()
  location.hash = ''
})

describe('GameScreen', () => {
  it('renders prologue and turns in order with role labels', async () => {
    const detail = session({
      turns: [
        { index: 1, role: 'player', text: 'I open the door.' },
        { index: 2, role: 'narrator', text: 'The door creaks open.' },
      ],
    })
    mockFetch(() => jsonResponse(detail))
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    expect(screen.getByText(t('game.prologue.label'))).toBeInTheDocument()
    expect(screen.getByText('I open the door.')).toBeInTheDocument()
    expect(screen.getByText('The door creaks open.')).toBeInTheDocument()
    expect(screen.getAllByText(t('game.turn.playerLabel'))).toHaveLength(1)
    expect(screen.getAllByText(t('game.turn.narratorLabel'))).toHaveLength(1)
  })

  it('renders speaker names from TurnText markup without the pipe', async () => {
    const detail = session({ prologue: '**Chloe** | Hello there.' })
    mockFetch(() => jsonResponse(detail))
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Hello there.')
    expect(screen.getByText('Chloe')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('|')
  })

  it('navigates back to the sessions hash from the back button', async () => {
    const user = userEvent.setup()
    mockFetch(() => jsonResponse(session()))
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    await user.click(screen.getByRole('button', { name: t('game.back') }))
    expect(location.hash).toBe('#/')
  })

  it('shows the empty hint below the prologue when there are no turns', async () => {
    mockFetch(() => jsonResponse(session({ turns: [] })))
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    expect(screen.getByText(t('game.empty.hint'))).toBeInTheDocument()
  })

  it('feeds the hud with null while loading and the real hud once loaded', async () => {
    let resolve: (value: Response) => void = () => {}
    const pending = new Promise<Response>((r) => {
      resolve = r
    })
    mockFetch(() => pending)
    render(<GameScreen sessionId="sess-1" />)

    expect(screen.getAllByText(t('hud.placeholder')).length).toBeGreaterThan(0)
    resolve(jsonResponse(session()))
    await screen.findByText('Hallway')
  })

  it('shows a not-found state without a retry button on 404', async () => {
    mockFetch(() => jsonResponse({}, 404))
    render(<GameScreen sessionId="missing" />)

    expect(await screen.findByText(t('game.notFound.title'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t('common.retry') })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('common.back') })).toBeInTheDocument()
  })

  it('shows an ErrorState with working retry on a 500', async () => {
    const user = userEvent.setup()
    let callCount = 0
    mockFetch(() => {
      callCount += 1
      return callCount === 1 ? jsonResponse({}, 500) : jsonResponse(session())
    })
    render(<GameScreen sessionId="sess-1" />)

    await user.click(await screen.findByRole('button', { name: t('common.retry') }))
    await screen.findByText('Once upon a time.')
    expect(callCount).toBe(2)
  })

  it('shows the offline error family when fetch rejects', async () => {
    mockFetch(() => {
      throw new TypeError('Failed to fetch')
    })
    render(<GameScreen sessionId="sess-1" />)

    expect(await screen.findByText(t('error.offline.title'))).toBeInTheDocument()
  })

  it('sets the document title to the interpolated scenario name and restores it on unmount', async () => {
    mockFetch(() => jsonResponse(session({ scenarioName: 'The School' })))
    const { unmount } = render(<GameScreen sessionId="sess-1" />)

    await waitFor(() => expect(document.title).toBe(t('game.documentTitle', { scenario: 'The School' })))
    unmount()
    expect(document.title).toBe('ooc-local')
  })

  it('moves focus to the heading on mount', async () => {
    mockFetch(() => jsonResponse(session()))
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1 }))
  })

  it('refetches without mixing history when the sessionId prop changes', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/sessions/sess-1') return jsonResponse(session({ prologue: 'First session.' }))
      return jsonResponse(session({ id: 'sess-2', prologue: 'Second session.' }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('First session.')
    rerender(<GameScreen sessionId="sess-2" />)

    await screen.findByText('Second session.')
    expect(screen.queryByText('First session.')).not.toBeInTheDocument()
  })
})
