import { createElement, StrictMode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GameScreen } from './GameScreen'
import { t } from '../i18n'
import type { SessionDetail } from '../api'
import type { HudView } from '../components/Hud'

const { hudCalls } = vi.hoisted(() => ({ hudCalls: [] as (HudView | null)[] }))

vi.mock('../components/Hud', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../components/Hud')>()
  return {
    ...actual,
    Hud: (props: Parameters<typeof actual.Hud>[0]) => {
      hudCalls.push(props.hud)
      return createElement(actual.Hud, props)
    },
  }
})

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
    assets: { sprites: {}, backgrounds: {} },
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

function stubRaf() {
  let nextId = 0
  const callbacks = new Map<number, FrameRequestCallback>()
  const raf = vi.fn((cb: FrameRequestCallback) => {
    nextId += 1
    callbacks.set(nextId, cb)
    return nextId
  })
  const caf = vi.fn((id: number) => {
    callbacks.delete(id)
  })
  vi.stubGlobal('requestAnimationFrame', raf)
  vi.stubGlobal('cancelAnimationFrame', caf)
  return {
    raf,
    flush() {
      const pending = [...callbacks.values()]
      callbacks.clear()
      for (const cb of pending) cb(0)
    },
  }
}

function stubScrollTo() {
  const scrollTo = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', { value: scrollTo, writable: true, configurable: true })
  return scrollTo
}

function stubReducedMotion(matches: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches }) as MediaQueryList),
  )
}

function hangingStreamFetch(opts: {
  get: (url: string) => Response | Promise<Response>
  onAbortSignal?: (signal: AbortSignal | null | undefined) => void
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') {
      opts.onAbortSignal?.(init.signal)
      let controller: ReadableStreamDefaultController<Uint8Array> | null = null
      const stream = new ReadableStream<Uint8Array>({
        start(c) {
          controller = c
          c.enqueue(new TextEncoder().encode('data: {"delta":"stale text "}\n\n'))
        },
      })
      init.signal?.addEventListener('abort', () => {
        controller?.error(new DOMException('The operation was aborted.', 'AbortError'))
      })
      return { ok: true, status: 200, body: stream } as unknown as Response
    }
    return opts.get(String(input))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
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
  hudCalls.length = 0
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

  it('never passes a null hud to Hud once the session data has arrived', async () => {
    let resolve: (value: Response) => void = () => {}
    const pending = new Promise<Response>((r) => {
      resolve = r
    })
    mockFetch(() => pending)
    render(<GameScreen sessionId="sess-1" />)

    resolve(jsonResponse(session()))
    await screen.findByText('Hallway')

    const firstRealIndex = hudCalls.findIndex((h) => h !== null)
    expect(firstRealIndex).toBeGreaterThanOrEqual(0)
    expect(hudCalls.slice(firstRealIndex).every((h) => h !== null)).toBe(true)
  })

  it('shows a not-found state without a retry button on 404', async () => {
    mockFetch(() => jsonResponse({}, 404))
    render(<GameScreen sessionId="missing" />)

    expect(await screen.findByText(t('game.notFound.title'))).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: t('common.back') })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t('common.retry') })).not.toBeInTheDocument()
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

  it('shows the chat-disabled error family on a 503 without dropping the player message, with the backend detail in the technical details', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({ get: () => jsonResponse(session()), post: () => jsonResponse({ detail: 'chat disabled by flag' }, 503) })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'try anyway{Enter}')

    expect(await screen.findByText(t('error.chatDisabled.title'))).toBeInTheDocument()
    expect(screen.getByText('try anyway', { selector: '.game-turn-text' })).toBeInTheDocument()

    await user.click(screen.getByText(t('common.details')))
    expect(screen.getByText('HTTP 503 — chat disabled by flag')).toBeInTheDocument()
  })

  it('does not throw and keeps message plain when the error body is not JSON', async () => {
    mockFetch(
      () =>
        ({
          ok: false,
          status: 500,
          json: async () => {
            throw new SyntaxError('unexpected token')
          },
        }) as unknown as Response,
    )
    render(<GameScreen sessionId="sess-1" />)

    expect(await screen.findByText(t('error.unexpected.title'))).toBeInTheDocument()
  })

  it('ignores a list-shaped detail from a pydantic 422 and keeps the plain HTTP message', async () => {
    mockFetch(() => jsonResponse({ detail: [{ msg: 'field required' }] }, 500))
    render(<GameScreen sessionId="sess-1" />)

    const user = userEvent.setup()
    await user.click(await screen.findByText(t('common.details')))
    expect(screen.getByText('HTTP 500')).toBeInTheDocument()
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

  it('records a single player/narrator pair per turn under StrictMode', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => sseResponse([{ delta: 'The hall answers.' }, { hud: { turn: 1, location: 'Hallway', time: 'Night', weather: 'clear' } }, '[DONE]']),
    })
    render(
      <StrictMode>
        <GameScreen sessionId="sess-1" />
      </StrictMode>,
    )

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'knock{Enter}')

    await screen.findByText('The hall answers.')
    await waitFor(() => {
      expect(screen.getAllByText('knock', { selector: '.game-turn-text' })).toHaveLength(1)
      expect(screen.getAllByText('The hall answers.')).toHaveLength(1)
    })
  })

  it('clears the textarea after a successful retry of a pre-stream error', async () => {
    const user = userEvent.setup()
    let failNext = true
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => {
        if (failNext) {
          failNext = false
          return jsonResponse({}, 503)
        }
        return sseResponse([{ delta: 'It works now.' }, { hud: { turn: 1, location: 'Hallway', time: 'Night', weather: 'clear' } }, '[DONE]'])
      },
    })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'try again{Enter}')

    await screen.findByText(t('error.chatDisabled.title'))
    expect((textarea as HTMLTextAreaElement).value).toBe('try again')

    await user.click(screen.getByRole('button', { name: t('common.retry') }))
    await screen.findByText('It works now.')
    expect((textarea as HTMLTextAreaElement).value).toBe('')
  })

  it('coalesces streamed scroll updates to at most one per animation frame, all in auto mode', async () => {
    const user = userEvent.setup()
    const scrollTo = stubScrollTo()
    const { flush } = stubRaf()
    const deltas = Array.from({ length: 50 }, (_, i) => ({ delta: `d${i} ` }))
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => sseResponse([...deltas, { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear' } }, '[DONE]']),
    })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    scrollTo.mockClear()
    await user.type(textarea, 'go{Enter}')
    await screen.findByText('Yard')

    expect(scrollTo).not.toHaveBeenCalled()
    flush()
    expect(scrollTo).toHaveBeenCalledTimes(1)
    expect(scrollTo).toHaveBeenCalledWith({ top: expect.any(Number), behavior: 'auto' })
  })

  it('pauses autoscroll on scroll-up, shows the floating jump button, and resumes with a smooth scroll on click', async () => {
    const user = userEvent.setup()
    const scrollTo = stubScrollTo()
    mockFetch(() => jsonResponse(session({ turns: [{ index: 1, role: 'narrator', text: 'the hallway' }] })))
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const history = screen.getByRole('list')
    Object.defineProperty(history, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(history, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(history, 'scrollTop', { value: 100, writable: true, configurable: true })
    fireEvent.scroll(history)

    const button = await screen.findByRole('button', { name: t('game.scrollToLatest') })
    expect(button.className).toContain('game-scrollLatest--floating')
    expect(button.closest('ol')).toBeNull()

    scrollTo.mockClear()
    await user.click(button)
    expect(scrollTo).toHaveBeenCalledWith({ top: expect.any(Number), behavior: 'smooth' })
    expect(screen.queryByRole('button', { name: t('game.scrollToLatest') })).not.toBeInTheDocument()
  })

  it('jumps to latest instantly when prefers-reduced-motion is set', async () => {
    stubReducedMotion(true)
    const user = userEvent.setup()
    const scrollTo = stubScrollTo()
    mockFetch(() => jsonResponse(session({ turns: [{ index: 1, role: 'narrator', text: 'the hallway' }] })))
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const history = screen.getByRole('list')
    Object.defineProperty(history, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(history, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(history, 'scrollTop', { value: 100, writable: true, configurable: true })
    fireEvent.scroll(history)

    const button = await screen.findByRole('button', { name: t('game.scrollToLatest') })
    scrollTo.mockClear()
    await user.click(button)
    expect(scrollTo).toHaveBeenCalledWith({ top: expect.any(Number), behavior: 'auto' })
  })

  it('aborts the fetch on unmount mid-stream without an ErrorState or a console.error', async () => {
    const user = userEvent.setup()
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    let capturedSignal: AbortSignal | null | undefined
    hangingStreamFetch({
      get: () => jsonResponse(session()),
      onAbortSignal: (signal) => {
        capturedSignal = signal
      },
    })
    const { unmount } = render(<GameScreen sessionId="sess-1" />)


    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'go{Enter}')
    await screen.findByText('stale text', { exact: false })

    unmount()
    await waitFor(() => expect(capturedSignal?.aborted).toBe(true))
    expect(screen.queryByText(t('game.turn.error'))).not.toBeInTheDocument()
    expect(errorSpy).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('aborts the previous stream and does not mix history when sessionId changes mid-stream', async () => {
    const user = userEvent.setup()
    let capturedSignal: AbortSignal | null | undefined
    hangingStreamFetch({
      get: (url) =>
        url === '/api/sessions/sess-1'
          ? jsonResponse(session({ prologue: 'First session.' }))
          : jsonResponse(session({ id: 'sess-2', prologue: 'Second session.' })),
      onAbortSignal: (signal) => {
        capturedSignal = signal
      },
    })

    const { rerender } = render(<GameScreen sessionId="sess-1" />)
    await screen.findByText('First session.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'go{Enter}')
    await screen.findByText('stale text', { exact: false })

    rerender(<GameScreen sessionId="sess-2" />)
    await screen.findByText('Second session.')
    await waitFor(() => expect(capturedSignal?.aborted).toBe(true))
    expect(screen.queryByText('stale text', { exact: false })).not.toBeInTheDocument()
  })

  it('treats an externally aborted fetch (signal not aborted) as a normal stream error', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => {
        throw new DOMException('The operation was aborted.', 'AbortError')
      },
    })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'go{Enter}')

    expect(await screen.findByText(t('error.unexpected.title'))).toBeInTheDocument()
  })

  it('shows the offline error family when the turn POST rejects, preserving the message and retrying', async () => {
    const user = userEvent.setup()
    let callCount = 0
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => {
        callCount += 1
        if (callCount === 1) throw new TypeError('Failed to fetch')
        return sseResponse([{ delta: 'ok now' }, { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear' } }, '[DONE]'])
      },
    })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'reach out{Enter}')

    expect(await screen.findByText(t('error.offline.title'))).toBeInTheDocument()
    expect(screen.getByText('reach out', { selector: '.game-turn-text' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: t('common.retry') }))
    await screen.findByText('ok now')
  })

  it('exposes aria-busy on submit, aria-live=off while streaming and role=status while thinking, and announces completion', async () => {
    const user = userEvent.setup()
    const ref: { c: ReadableStreamDefaultController<Uint8Array> | null } = { c: null }
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        ref.c = c
      },
    })
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => ({ ok: true, status: 200, body: stream }) as unknown as Response,
    })
    render(<GameScreen sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    const button = screen.getByRole('button', { name: t('game.input.send') })
    await user.type(textarea, 'go{Enter}')

    expect(button).toHaveAttribute('aria-busy', 'true')
    const thinking = screen.getByText(t('game.turn.thinking'))
    expect(thinking).toHaveAttribute('role', 'status')
    expect(document.querySelector('[aria-live="off"]')).not.toBeNull()

    ref.c?.enqueue(new TextEncoder().encode('data: {"delta":"It creaks."}\n\n'))
    await screen.findByText('It creaks.')
    expect(screen.queryByText(t('game.turn.thinking'))).not.toBeInTheDocument()

    ref.c?.enqueue(new TextEncoder().encode('data: {"hud":{"turn":1,"location":"Yard","time":"Day","weather":"clear"}}\n\n'))
    ref.c?.enqueue(new TextEncoder().encode('data: [DONE]\n\n'))
    ref.c?.close()

    await waitFor(() => expect(screen.getByText(t('game.turn.done', { index: 1 }))).toBeInTheDocument())
  })
})
