import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BuilderPreview } from './BuilderPreview'
import { t } from '../../i18n'
import type { BuilderDraft } from '../../screens/BuilderEditorScreen'
import type { SessionDetail } from '../../api'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
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

function draft(overrides: Partial<BuilderDraft> = {}): BuilderDraft {
  return {
    meta: { name: 'The School', tagline: null, description: null, locale: 'en', tags: [], default_start: 'default', world_mode: 'guided', allow_dynamic_stats: false },
    world: '',
    starts: {
      default: {
        id: 'default',
        name: 'Default start',
        prologue: '',
        opening_scene: '',
        conflict: null,
        mission: null,
        play_guide: null,
        suggestions: [],
        hud: { location: 'Hallway', time: '08:00', weather: 'clear' },
        characters: null,
      },
      alt: {
        id: 'alt',
        name: 'Alt start',
        prologue: '',
        opening_scene: '',
        conflict: null,
        mission: null,
        play_guide: null,
        suggestions: [],
        hud: { location: 'Yard', time: '20:00', weather: 'clear' },
        characters: null,
      },
    },
    characters: {},
    stats: [],
    lorebook: {},
    commands: [],
    ...overrides,
  }
}

function session(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    id: 'sess-1',
    scenarioId: 'school',
    scenarioName: 'The School',
    prologue: 'It begins.',
    playGuide: null,
    turns: [],
    hud: { turn: 0, location: 'Hallway', time: '08:00', weather: 'clear' },
    assets: { sprites: {}, backgrounds: {} },
    cast: [],
    stats: [],
    minds: {},
    commands: [],
    suggestions: [],
    ...overrides,
  }
}

type FetchHandlers = {
  create?: (body: { scenarioId: string; startId?: string; ephemeral?: boolean }) => Response | Promise<Response>
  get?: (id: string) => Response | Promise<Response>
  del?: (id: string, init: RequestInit) => Response | Promise<Response>
  turn?: () => Response | Promise<Response>
}

function mockFetch(handlers: FetchHandlers) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (method === 'POST' && url === '/api/sessions') {
      const body = JSON.parse(String(init?.body))
      return (handlers.create ?? (() => jsonResponse(session())))(body)
    }
    if (method === 'DELETE' && url.startsWith('/api/sessions/')) {
      const id = url.slice('/api/sessions/'.length)
      return (handlers.del ?? (() => jsonResponse(null, 204)))(id, init ?? {})
    }
    if (method === 'POST' && url.endsWith('/turn')) {
      return (handlers.turn ?? (() => sseResponse(['[DONE]'])))()
    }
    if (method === 'GET' && url.startsWith('/api/sessions/')) {
      const id = url.slice('/api/sessions/'.length)
      return (handlers.get ?? (() => jsonResponse(session({ id }))))(id)
    }
    throw new Error(`unexpected fetch ${method} ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  location.hash = ''
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  location.hash = ''
})

describe('BuilderPreview', () => {
  it('starts the preview with ephemeral true and the selected start, showing the prologue', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({
      create: () => jsonResponse(session({ id: 'sess-1', prologue: 'It begins.' })),
    })
    render(
      <BuilderPreview scenarioId="school" draft={draft()} loadedStartIds={['default', 'alt']} dirty={false} savedAt={null} onSave={vi.fn()} />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.preview.start') }))
    await screen.findByText('It begins.')

    const createCall = fetchMock.mock.calls.find(([input, init]) => String(input) === '/api/sessions' && (init as RequestInit)?.method === 'POST')
    expect(createCall).toBeDefined()
    const createInit = (createCall as [RequestInfo | URL, RequestInit])[1]
    const body = JSON.parse(String(createInit.body))
    expect(body).toMatchObject({ scenarioId: 'school', startId: 'default', ephemeral: true })
  })

  it('plays a turn through the panel and updates the hud', async () => {
    const user = userEvent.setup()
    mockFetch({
      create: () => jsonResponse(session()),
      turn: () => sseResponse([{ delta: 'It creaks.' }, { hud: { turn: 1, location: 'Yard', time: 'Day', weather: 'clear' } }, '[DONE]']),
    })
    render(
      <BuilderPreview scenarioId="school" draft={draft()} loadedStartIds={['default', 'alt']} dirty={false} savedAt={null} onSave={vi.fn()} />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.preview.start') }))
    await screen.findByText('It begins.')

    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'I open the door.{Enter}')

    await screen.findByText('It creaks.')
    await screen.findByText('Yard')
  })

  it('restarts with confirmation when turns were played, deleting the old session before creating a new one', async () => {
    const user = userEvent.setup()
    let createCount = 0
    const fetchMock = mockFetch({
      create: () => {
        createCount += 1
        return jsonResponse(session({ id: `sess-${createCount}` }))
      },
      turn: () => sseResponse(['[DONE]']),
    })
    render(
      <BuilderPreview scenarioId="school" draft={draft()} loadedStartIds={['default', 'alt']} dirty={false} savedAt={null} onSave={vi.fn()} />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.preview.start') }))
    await screen.findByText('It begins.')

    const textarea = screen.getByRole('textbox', { name: t('game.input.label') })
    await user.type(textarea, 'One.{Enter}')
    await waitFor(() => expect(textarea).not.toBeDisabled())
    await user.type(textarea, 'Two.{Enter}')
    await waitFor(() => expect(textarea).not.toBeDisabled())

    await user.click(screen.getByRole('button', { name: t('builder.preview.restart') }))
    const dialog = screen.getByRole('heading', { name: t('builder.preview.restart.title') }).closest('dialog') as HTMLDialogElement
    expect(dialog).toBeTruthy()
    await user.click(within(dialog).getByRole('button', { name: t('builder.preview.restart.submit') }))

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.find(([input, init]) => String(input) === '/api/sessions/sess-1' && (init as RequestInit)?.method === 'DELETE')
      expect(deleteCall).toBeDefined()
    })
    await waitFor(() => expect(createCount).toBe(2))
  })

  it('shows the stale warning while dirty, and save-and-restart calls onSave before restarting', async () => {
    const user = userEvent.setup()
    let resolveSave: () => void = () => {}
    const onSave = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveSave = resolve
        }),
    )
    let createCount = 0
    const fetchMock = mockFetch({
      create: () => {
        createCount += 1
        return jsonResponse(session({ id: `sess-${createCount}` }))
      },
    })
    render(<BuilderPreview scenarioId="school" draft={draft()} loadedStartIds={['default', 'alt']} dirty={true} savedAt={null} onSave={onSave} />)

    await user.click(screen.getByRole('button', { name: t('builder.preview.start') }))
    await screen.findByText('It begins.')

    expect(screen.getByText(t('builder.preview.stale'))).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: t('builder.preview.saveAndRestart') }))
    expect(onSave).toHaveBeenCalled()
    expect(createCount).toBe(1)

    resolveSave()
    await waitFor(() => expect(createCount).toBe(2))
    void fetchMock
  })

  it('switches the outdated warning to restart after a save while the preview is running', async () => {
    const user = userEvent.setup()
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(1000)
    mockFetch({ create: () => jsonResponse(session()) })
    const { rerender } = render(
      <BuilderPreview scenarioId="school" draft={draft()} loadedStartIds={['default', 'alt']} dirty={false} savedAt={null} onSave={vi.fn()} />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.preview.start') }))
    await screen.findByText('It begins.')
    nowSpy.mockReturnValue(2000)

    rerender(
      <BuilderPreview scenarioId="school" draft={draft()} loadedStartIds={['default', 'alt']} dirty={false} savedAt={1500} onSave={vi.fn()} />,
    )

    expect(screen.getByText(t('builder.preview.outdated'))).toBeInTheDocument()
  })

  it('disables an unsaved start in the select and shows the hint', () => {
    mockFetch({})
    render(
      <BuilderPreview
        scenarioId="school"
        draft={draft({ meta: { ...draft().meta, default_start: 'alt' } })}
        loadedStartIds={['default']}
        dirty={false}
        savedAt={null}
        onSave={vi.fn()}
      />,
    )

    const option = screen.getByRole('option', { name: /Alt start/ }) as HTMLOptionElement
    expect(option.disabled).toBe(true)
    expect(screen.getByText(t('builder.preview.startUnsaved'))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('builder.preview.start') })).toBeDisabled()
  })

  it('deletes the ephemeral session with keepalive on unmount', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({ create: () => jsonResponse(session({ id: 'sess-1' })) })
    const { unmount } = render(
      <BuilderPreview scenarioId="school" draft={draft()} loadedStartIds={['default', 'alt']} dirty={false} savedAt={null} onSave={vi.fn()} />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.preview.start') }))
    await screen.findByText('It begins.')

    unmount()

    const deleteCall = fetchMock.mock.calls.find(([input, init]) => String(input) === '/api/sessions/sess-1' && (init as RequestInit)?.method === 'DELETE')
    expect(deleteCall).toBeDefined()
    const deleteInit = (deleteCall as [RequestInfo | URL, RequestInit])[1]
    expect(deleteInit.keepalive).toBe(true)
  })

  it('deletes the session created mid-start when unmounted before the create call resolves', async () => {
    const user = userEvent.setup()
    let resolveCreate: (response: Response) => void = () => {}
    const fetchMock = mockFetch({
      create: () =>
        new Promise<Response>((resolve) => {
          resolveCreate = resolve
        }),
    })
    const { unmount } = render(
      <BuilderPreview scenarioId="school" draft={draft()} loadedStartIds={['default', 'alt']} dirty={false} savedAt={null} onSave={vi.fn()} />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.preview.start') }))
    unmount()
    resolveCreate(jsonResponse(session({ id: 'sess-1' })))

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.find(([input, init]) => String(input) === '/api/sessions/sess-1' && (init as RequestInit)?.method === 'DELETE')
      expect(deleteCall).toBeDefined()
    })
  })

  it('shows a start error with retry when creating the session fails', async () => {
    const user = userEvent.setup()
    mockFetch({ create: () => jsonResponse({ detail: 'boom' }, 500) })
    render(
      <BuilderPreview scenarioId="school" draft={draft()} loadedStartIds={['default', 'alt']} dirty={false} savedAt={null} onSave={vi.fn()} />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.preview.start') }))
    await screen.findByText(t('builder.preview.start.error'))
    expect(screen.getByRole('button', { name: t('common.retry') })).toBeInTheDocument()
  })

  it('shows the invalid reason and hides the start button when the document is invalid', () => {
    mockFetch({})
    render(
      <BuilderPreview
        scenarioId="school"
        draft={draft()}
        loadedStartIds={['default', 'alt']}
        dirty={false}
        savedAt={null}
        invalidReason="scenario.yaml: broken"
        onSave={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: t('builder.preview.start') })).not.toBeInTheDocument()
    expect(screen.getByText(t('builder.preview.invalid.body', { reason: 'scenario.yaml: broken' }))).toBeInTheDocument()
  })
})
