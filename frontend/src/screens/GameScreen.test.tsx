import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

function sseStream(lines: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(line))
      controller.close()
    },
  })
}

function sseResponse(events: Array<Record<string, unknown> | '[DONE]'>, status = 200): Response {
  const lines = events.map((event) => `data: ${event === '[DONE]' ? '[DONE]' : JSON.stringify(event)}\n\n`)
  return { ok: status >= 200 && status < 300, status, body: sseStream(lines) } as unknown as Response
}

function mockRoutedFetch(opts: {
  get: () => Response | Promise<Response>
  post: (message: string) => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as { message: string }
      return opts.post(body.message)
    }
    return opts.get()
  })
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

describe('GameScreen turns', () => {
  it('plays a happy turn: optimistic player line, streaming deltas, hud update on [DONE]', async () => {
    const user = userEvent.setup()
    const fetchMock = mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () =>
        sseResponse([
          { delta: 'It ' },
          { delta: 'creaks ' },
          { delta: 'open.' },
          { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear' } },
          '[DONE]',
        ]),
    })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'I open the door.{Enter}')

    expect(screen.getByText('I open the door.')).toBeInTheDocument()
    await screen.findByText('It creaks open.')
    await screen.findByText('Yard')

    const posts = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
    expect(posts).toHaveLength(1)
    expect((textarea as HTMLTextAreaElement).value).toBe('')
  })

  it('plays two turns in a row with correct indices and focus back on the input each time', async () => {
    const user = userEvent.setup()
    let call = 0
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => {
        call += 1
        return sseResponse([
          { delta: `turn ${call}` },
          { hud: { turn: call, location: 'Yard', time: 'Day', weather: 'clear' } },
          '[DONE]',
        ])
      },
    })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })

    await user.type(textarea, 'first{Enter}')
    await screen.findByText('turn 1')
    await waitFor(() => expect(document.activeElement).toBe(textarea))

    await user.type(textarea, 'second{Enter}')
    await screen.findByText('turn 2')
    await waitFor(() => expect(document.activeElement).toBe(textarea))

    expect(screen.getByText('first')).toBeInTheDocument()
    expect(screen.getByText('second')).toBeInTheDocument()
  })

  it('marks the hud stale when the stream ends without a hud event', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({
      get: () => jsonResponse(session({ hud: { turn: 3, location: 'Hallway', time: 'Night', weather: 'clear' } })),
      post: () => sseResponse([{ delta: 'Silence.' }, '[DONE]']),
    })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'wait{Enter}')

    await screen.findByText('Silence.')
    expect(screen.getByText('Hallway')).toBeInTheDocument()
    expect(screen.getByText(t('hud.stale'))).toBeInTheDocument()
  })

  it('filters inline tags out of streamed deltas', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () =>
        sseResponse([
          { delta: 'Chloe looks sad. [SPRITE:chloe:sad]' },
          { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear' } },
          '[DONE]',
        ]),
    })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'look{Enter}')

    await screen.findByText('Chloe looks sad.')
    expect(document.body.textContent).not.toContain('SPRITE')
  })

  it('keeps the send button disabled and sends no POST for a blank message', async () => {
    const fetchMock = mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => sseResponse(['[DONE]']),
    })
    const user = userEvent.setup()
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    const button = screen.getByRole('button', { name: t('game.input.send') })
    expect(button).toBeDisabled()

    await user.type(textarea, '   ')
    expect(button).toBeDisabled()
    await user.keyboard('{Enter}')

    const posts = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
    expect(posts).toHaveLength(0)
  })

  it('sends a single POST for two rapid Enter presses', async () => {
    const fetchMock = mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => sseResponse([{ delta: 'ok' }, { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear' } }, '[DONE]']),
    })
    const user = userEvent.setup()
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'go')
    fireEvent.keyDown(textarea, { key: 'Enter' })
    fireEvent.keyDown(textarea, { key: 'Enter' })

    await screen.findByText('ok')
    const posts = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
    expect(posts).toHaveLength(1)
  })

  it('keeps typed text after pressing Escape in the textarea', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({ get: () => jsonResponse(session()), post: () => sseResponse(['[DONE]']) })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'still here')
    await user.keyboard('{Escape}')

    expect((textarea as HTMLTextAreaElement).value).toBe('still here')
  })

  it('shows an error mid-stream with the partial text and cause, and retry completes the turn', async () => {
    const user = userEvent.setup()
    let call = 0
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => {
        call += 1
        if (call === 1) return sseResponse([{ delta: 'Half a sen' }, { error: 'model timeout' }, '[DONE]'])
        return sseResponse([
          { delta: 'Full sentence.' },
          { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear' } },
          '[DONE]',
        ])
      },
    })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'push through{Enter}')

    await screen.findByText(t('game.turn.error'))
    expect(screen.getByText(t('game.turn.partial'))).toBeInTheDocument()
    expect(screen.getByText('Half a sen')).toBeInTheDocument()
    expect(screen.getByText(t('hud.stale'))).toBeInTheDocument()
    await user.click(screen.getByText(t('common.details')))
    expect(screen.getByText('model timeout')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: t('common.retry') }))
    await screen.findByText('Full sentence.')
    expect(screen.queryByText(t('game.turn.error'))).not.toBeInTheDocument()
  })

  it('shows the chat-disabled error family on a 503 without dropping the player message', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({ get: () => jsonResponse(session()), post: () => jsonResponse({}, 503) })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'try anyway{Enter}')

    expect(await screen.findByText(t('error.chatDisabled.title'))).toBeInTheDocument()
    expect(screen.getByText('try anyway', { selector: '.game-turn-text' })).toBeInTheDocument()
  })

  it('shows the not-found state with a back button and no retry on a 404, keeping the typed text', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({ get: () => jsonResponse(session()), post: () => jsonResponse({}, 404) })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'still typed{Enter}')

    expect(await screen.findAllByText(t('game.notFound.title'))).not.toHaveLength(0)
    expect(screen.queryByRole('button', { name: t('common.retry') })).not.toBeInTheDocument()
    expect((textarea as HTMLTextAreaElement).value).toBe('still typed')
  })
})
