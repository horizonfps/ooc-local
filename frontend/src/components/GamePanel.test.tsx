import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GamePanel } from './GamePanel'
import { t } from '../i18n'
import type { SessionDetail, StatView } from '../api'

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
    cast: [],
    stats: [],
    minds: {},
    commands: [],
    suggestions: [],
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
      expect(document.querySelector('.game-stage-toggle')).toBeNull()
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

  describe('cast', () => {
    it('updates the chips and announces the new cast once when onHud carries a different cast', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () => jsonResponse(session({ cast: [{ id: 'aiko', name: 'Aiko' }] })),
        post: () =>
          sseResponse([
            { delta: 'They arrive.' },
            {
              hud: {
                turn: 1,
                location: 'Yard',
                time: 'Day',
                weather: 'clear',
                cast: [
                  { id: 'aiko', name: 'Aiko' },
                  { id: 'cydonia', name: 'Cydonia' },
                ],
              },
            },
            '[DONE]',
          ]),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      expect(screen.getByText('Aiko')).toBeInTheDocument()

      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      await screen.findByText('Cydonia')
      await screen.findByText(t('game.cast.announce', { characters: 'Aiko, Cydonia' }))
    })

    it('loading a session does not announce the cast in the live region', async () => {
      mockRoutedFetch({
        get: () => jsonResponse(session({ cast: [{ id: 'aiko', name: 'Aiko' }] })),
        post: () => sseResponse(['[DONE]']),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      expect(screen.getByText('Aiko')).toBeInTheDocument()
      expect(screen.queryByText(t('game.cast.announce', { characters: 'Aiko' }))).toBeNull()
    })

    it('keeps the previous chips when onHud carries cast null', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () => jsonResponse(session({ cast: [{ id: 'aiko', name: 'Aiko' }] })),
        post: () =>
          sseResponse([
            { delta: 'They stay.' },
            { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear', cast: null } },
            '[DONE]',
          ]),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      await screen.findByText('Yard')
      expect(screen.getByText('Aiko')).toBeInTheDocument()
    })

    it('keeps the previous chips when onHud omits cast', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () => jsonResponse(session({ cast: [{ id: 'aiko', name: 'Aiko' }] })),
        post: () =>
          sseResponse([
            { delta: 'They stay.' },
            { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear' } },
            '[DONE]',
          ]),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      await screen.findByText('Yard')
      expect(screen.getByText('Aiko')).toBeInTheDocument()
    })

    it('keeps the previous chips visible with aria-busy during the stream', async () => {
      const user = userEvent.setup()
      let releaseStream: (() => void) | undefined
      const streamGate = new Promise<void>((resolve) => {
        releaseStream = resolve
      })
      mockRoutedFetch({
        get: () => jsonResponse(session({ cast: [{ id: 'aiko', name: 'Aiko' }] })),
        post: async () => {
          await streamGate
          return sseResponse([{ delta: 'They stay.' }, '[DONE]'])
        },
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      const group = screen.getByRole('group', { name: t('game.cast.regionLabel') })
      expect(group).toHaveAttribute('aria-busy', 'true')
      expect(screen.getByText('Aiko')).toBeInTheDocument()

      releaseStream?.()
      await screen.findByText('They stay.')
    })
  })

  describe('stats and minds', () => {
    function statView(overrides: Partial<StatView> = {}): StatView {
      return { id: 'reputacao', name: 'Reputação', icon: '⭐', color: null, value: 55, min: 0, max: 100, level: null, ...overrides }
    }

    it('an SSE hud event with stats updates the bars and announces the change once', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () => jsonResponse(session({ stats: [statView({ value: 55 })] })),
        post: () =>
          sseResponse([
            { delta: 'Time passes.' },
            {
              hud: {
                turn: 1,
                location: 'Yard',
                time: 'Day',
                weather: 'clear',
                stats: [statView({ value: 60 })],
              },
            },
            '[DONE]',
          ]),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      expect(screen.getByText(t('hud.stat.value', { value: 55, max: 100 }))).toBeInTheDocument()

      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      await screen.findByText(t('hud.stat.value', { value: 60, max: 100 }))
      const announcement = t('hud.stats.announce', { changes: t('hud.stats.change', { name: 'Reputação', value: 60 }) })
      await screen.findByText(announcement)
      expect(screen.getAllByText(announcement)).toHaveLength(1)
    })

    it('an SSE hud event with minds fills the INFO rows', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () => jsonResponse(session({ cast: [{ id: 'chloe', name: 'Chloe' }] })),
        post: () =>
          sseResponse([
            { delta: 'She watches.' },
            {
              hud: {
                turn: 1,
                location: 'Yard',
                time: 'Day',
                weather: 'clear',
                minds: { chloe: { attitude: 'desconfiada', emoji: '🤨', event: 'viu você chegar' } },
              },
            },
            '[DONE]',
          ]),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      await screen.findByText('desconfiada')
      expect(screen.getByText(t('game.info.event', { event: 'viu você chegar' }))).toBeInTheDocument()
    })

    it('loading a session does not announce stats', async () => {
      mockRoutedFetch({
        get: () => jsonResponse(session({ stats: [statView({ value: 55 })] })),
        post: () => sseResponse(['[DONE]']),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const announcement = t('hud.stats.announce', { changes: t('hud.stats.change', { name: 'Reputação', value: 55 }) })
      expect(screen.queryByText(announcement)).toBeNull()
    })

    it('a hud event without stats keeps the previous bars, and without minds keeps the previous INFO rows', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () =>
          jsonResponse(
            session({
              cast: [{ id: 'chloe', name: 'Chloe' }],
              stats: [statView({ value: 55 })],
              minds: { chloe: { attitude: 'desconfiada', emoji: '🤨', event: 'viu você chegar' } },
            }),
          ),
        post: () =>
          sseResponse([
            { delta: 'Nothing changes.' },
            { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear' } },
            '[DONE]',
          ]),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      await screen.findByText('Yard')
      expect(screen.getByText(t('hud.stat.value', { value: 55, max: 100 }))).toBeInTheDocument()
      expect(screen.getByText('desconfiada')).toBeInTheDocument()
    })

    it('only the changed stat appears in the announcement', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () =>
          jsonResponse(
            session({
              stats: [statView({ id: 'reputacao', name: 'Reputação', value: 55 }), statView({ id: 'energia', name: 'Energia', value: 80 })],
            }),
          ),
        post: () =>
          sseResponse([
            { delta: 'Time passes.' },
            {
              hud: {
                turn: 1,
                location: 'Yard',
                time: 'Day',
                weather: 'clear',
                stats: [statView({ id: 'reputacao', name: 'Reputação', value: 60 }), statView({ id: 'energia', name: 'Energia', value: 80 })],
              },
            },
            '[DONE]',
          ]),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      const announcement = t('hud.stats.announce', { changes: t('hud.stats.change', { name: 'Reputação', value: 60 }) })
      await screen.findByText(announcement)
      expect(screen.queryByText(t('hud.stats.change', { name: 'Energia', value: 80 }), { exact: false })).toBeNull()
    })

    it('during the stream both blocks keep the previous values with aria-busy', async () => {
      const user = userEvent.setup()
      let releaseStream: (() => void) | undefined
      const streamGate = new Promise<void>((resolve) => {
        releaseStream = resolve
      })
      mockRoutedFetch({
        get: () =>
          jsonResponse(
            session({
              cast: [{ id: 'chloe', name: 'Chloe' }],
              stats: [statView({ value: 55 })],
              minds: { chloe: { attitude: 'desconfiada', emoji: '🤨', event: 'viu você chegar' } },
            }),
          ),
        post: async () => {
          await streamGate
          return sseResponse([{ delta: 'They stay.' }, '[DONE]'])
        },
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      const statsGroup = screen.getByRole('group', { name: t('hud.stats.regionLabel') })
      expect(statsGroup).toHaveAttribute('aria-busy', 'true')
      expect(screen.getByText(t('hud.stat.value', { value: 55, max: 100 }))).toBeInTheDocument()

      const infoGroup = screen.getByRole('group', { name: t('game.info.regionLabel') })
      expect(infoGroup).toHaveAttribute('aria-busy', 'true')
      expect(screen.getByText('desconfiada')).toBeInTheDocument()

      releaseStream?.()
      await screen.findByText('They stay.')
    })

    it('a scenario without stats renders no bars block', async () => {
      mockRoutedFetch({ get: () => jsonResponse(session()), post: () => sseResponse(['[DONE]']) })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      expect(document.querySelector('.statBars')).toBeNull()
    })

    it('a failed turn shows hud.stale exactly once, with both blocks dimmed and still in the DOM', async () => {
      const user = userEvent.setup()
      mockRoutedFetch({
        get: () =>
          jsonResponse(
            session({
              cast: [{ id: 'chloe', name: 'Chloe' }],
              stats: [statView({ value: 55 })],
              minds: { chloe: { attitude: 'desconfiada', emoji: '🤨', event: 'viu você chegar' } },
            }),
          ),
        post: () => jsonResponse({}, 500),
      })
      render(<GamePanel sessionId="sess-1" />)

      await screen.findByText('Once upon a time.')
      const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
      await user.type(textarea, 'go{Enter}')

      const staleTexts = await screen.findAllByText(t('hud.stale'))
      expect(staleTexts).toHaveLength(1)
      expect(document.querySelector('.statBars--stale')).not.toBeNull()
      expect(document.querySelector('.info--stale')).not.toBeNull()
      expect(screen.getByText(t('hud.stat.value', { value: 55, max: 100 }))).toBeInTheDocument()
      expect(screen.getByText('desconfiada')).toBeInTheDocument()
    })
  })
})
