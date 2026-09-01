import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GamePanel } from './GamePanel'
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
    assets: { sprites: {}, backgrounds: {} },
    ...overrides,
  }
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
  get: (url: string) => Response | Promise<Response>
  post: (message: string) => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as { message: string }
      return opts.post(body.message)
    }
    return opts.get(String(input))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  location.hash = ''
})

afterEach(() => {
  vi.unstubAllGlobals()
  location.hash = ''
})

describe('GamePanel', () => {
  it('loads the session, plays a turn and updates the hud', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () =>
        sseResponse([
          { delta: 'It creaks open.' },
          { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear' } },
          '[DONE]',
        ]),
    })
    render(<GamePanel sessionId="sess-1" />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'I open the door.{Enter}')

    await screen.findByText('It creaks open.')
    await screen.findByText('Yard')
  })

  it('keeps two instances with different sessionIds isolated in history and label targets', async () => {
    mockRoutedFetch({
      get: (url) =>
        url.includes('sess-a')
          ? jsonResponse(session({ id: 'sess-a', prologue: 'Prologue A.' }))
          : jsonResponse(session({ id: 'sess-b', prologue: 'Prologue B.' })),
      post: () => sseResponse(['[DONE]']),
    })
    render(
      <>
        <GamePanel sessionId="sess-a" />
        <GamePanel sessionId="sess-b" />
      </>,
    )

    await screen.findByText('Prologue A.')
    await screen.findByText('Prologue B.')

    const textareas = screen.getAllByRole('textbox', { name: t('game.input.label') })
    expect(textareas).toHaveLength(2)
    const labels = screen.getAllByText(t('game.input.label'))
    expect(labels).toHaveLength(2)
    labels.forEach((label, i) => {
      expect(label.getAttribute('for')).toBe(textareas[i].id)
    })
    expect(textareas[0].id).not.toBe(textareas[1].id)
  })

  it('does not steal focus on mount when autoFocusInput is false', async () => {
    mockRoutedFetch({ get: () => jsonResponse(session()), post: () => sseResponse(['[DONE]']) })
    render(<GamePanel sessionId="sess-1" autoFocusInput={false} />)

    await screen.findByText('Once upon a time.')
    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    expect(document.activeElement).not.toBe(textarea)
  })

  it('calls onTurnsChanged with the played turn count as history changes', async () => {
    const user = userEvent.setup()
    const onTurnsChanged = vi.fn()
    mockRoutedFetch({
      get: () => jsonResponse(session()),
      post: () => sseResponse([{ delta: 'It creaks open.' }, '[DONE]']),
    })
    render(<GamePanel sessionId="sess-1" onTurnsChanged={onTurnsChanged} />)

    await screen.findByText('Once upon a time.')
    expect(onTurnsChanged).toHaveBeenCalledWith(0)

    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'I open the door.{Enter}')

    await screen.findByText('It creaks open.')
    expect(onTurnsChanged).toHaveBeenLastCalledWith(1)
  })

  it('calls onNotFound once on a 404 and does not render a back button', async () => {
    const onNotFound = vi.fn()
    mockRoutedFetch({ get: () => jsonResponse({}, 404), post: () => jsonResponse({}, 404) })
    render(<GamePanel sessionId="missing" onNotFound={onNotFound} />)

    await screen.findByText(t('game.notFound.title'))
    expect(onNotFound).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: t('common.back') })).not.toBeInTheDocument()
  })

  describe('scene', () => {
    const assets = {
      sprites: { chloe: { default: '/media/chloe/default.png', sad: '/media/chloe/sad.png' } },
      backgrounds: { patio: '/media/backgrounds/patio.png' },
    }

    afterEach(() => {
      localStorage.clear()
    })

    it('renders the background layer and a sprite with an interpolated alt when a turn carries tags', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () => jsonResponse(session({ assets })),
        post: () => sseResponse([{ delta: '[BG:patio] [SPRITE:chloe:sad] She looks up.' }, '[DONE]']),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      const sprite = await screen.findByAltText(t('game.sprite.alt', { character: 'chloe', emotion: 'sad' }))
      expect(sprite).toBeInTheDocument()
      expect(document.querySelector('.game-stage-bg')).not.toBeNull()
    })

    it('renders no background layer and no sprite band when the session has no assets', async () => {
      mockRoutedFetch({ get: () => jsonResponse(session()), post: () => sseResponse(['[DONE]']) })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      expect(document.querySelector('.game-stage-bg')).toBeNull()
      expect(document.querySelector('.game-stage-sprites')).toBeNull()
    })

    it('drops a sprite that fails to load without showing an error', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () => jsonResponse(session({ assets })),
        post: () => sseResponse([{ delta: '[SPRITE:chloe:sad] She looks up.' }, '[DONE]']),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      const sprite = await screen.findByAltText(t('game.sprite.alt', { character: 'chloe', emotion: 'sad' }))
      fireEvent.error(sprite)

      await waitFor(() => expect(document.querySelector('.game-stage-sprites')).toBeNull())
    })

    it('the toggle hides the artwork and persists the preference', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () => jsonResponse(session({ assets })),
        post: () => sseResponse([{ delta: '[BG:patio] She looks up.' }, '[DONE]']),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')
      await screen.findByText('She looks up.')

      const toggle = screen.getByRole('button', { name: t('game.stage.hide') })
      expect(toggle).toHaveAttribute('aria-pressed', 'true')
      await user.click(toggle)

      expect(document.querySelector('.game-stage-bg')).toBeNull()
      expect(screen.getByRole('button', { name: t('game.stage.show') })).toHaveAttribute('aria-pressed', 'false')
      expect(localStorage.getItem('ooc-local:stage')).toBe('0')
    })

    it('does not break when localStorage throws', async () => {
      const original = window.localStorage
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        get() {
          throw new Error('blocked')
        },
      })

      mockRoutedFetch({ get: () => jsonResponse(session({ assets })), post: () => sseResponse(['[DONE]']) })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      expect(screen.getByRole('button', { name: t('game.stage.hide') })).toBeInTheDocument()

      Object.defineProperty(window, 'localStorage', { configurable: true, value: original })
    })

    it('announces the scene change in the existing live region', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () => jsonResponse(session({ assets })),
        post: () => sseResponse([{ delta: '[BG:patio][SPRITE:chloe:sad] She looks up.' }, '[DONE]']),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      await screen.findByText(
        t('game.scene.announce', {
          background: 'patio',
          characters: t('game.scene.characterEmotion', { character: 'chloe', emotion: 'sad' }),
        }),
      )
    })
  })
})
