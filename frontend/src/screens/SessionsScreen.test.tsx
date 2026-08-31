import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionsScreen } from './SessionsScreen'
import { t } from '../i18n'

const SCENARIO = { id: 'school', name: 'The School', tagline: 'A haunted hallway', locale: 'en' }
const SCENARIO_NO_TAGLINE = { id: 'noir', name: 'Noir City', tagline: null, locale: 'en' }

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function mockFetch(handlers: { scenarios?: () => Response | Promise<Response>; sessions?: () => Response | Promise<Response>; post?: () => Response | Promise<Response> }) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url === '/api/scenarios') {
      return handlers.scenarios ? handlers.scenarios() : jsonResponse([SCENARIO])
    }
    if (url === '/api/sessions' && init?.method === 'POST') {
      return handlers.post ? handlers.post() : jsonResponse({ id: 'new-session' }, 201)
    }
    if (url === '/api/sessions') {
      return handlers.sessions ? handlers.sessions() : jsonResponse([])
    }
    throw new Error(`unexpected fetch ${url}`)
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

describe('SessionsScreen', () => {
  it('shows an empty state and a usable creation block when there are no sessions', async () => {
    mockFetch({ sessions: () => jsonResponse([]) })
    render(<SessionsScreen />)

    expect(await screen.findByText(t('sessions.empty.title'))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('sessions.new.submit') })).toBeEnabled()
  })

  it('renders sessions in the order returned by the API, with correct turn plurals', async () => {
    const sessions = [
      { id: 'a', scenarioId: 's1', scenarioName: 'Alpha', turnCount: 0, updatedAt: new Date().toISOString(), location: 'x' },
      { id: 'b', scenarioId: 's2', scenarioName: 'Beta', turnCount: 1, updatedAt: new Date().toISOString(), location: 'x' },
      { id: 'c', scenarioId: 's3', scenarioName: 'Gamma', turnCount: 7, updatedAt: new Date().toISOString(), location: 'x' },
    ]
    mockFetch({ sessions: () => jsonResponse(sessions) })
    render(<SessionsScreen />)

    const items = await screen.findAllByRole('button', { name: /Alpha|Beta|Gamma/ })
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('Alpha'),
      expect.stringContaining('Beta'),
      expect.stringContaining('Gamma'),
    ])
    expect(within(items[0]).getByText(new RegExp(t('sessions.item.turnsZero')))).toBeInTheDocument()
    expect(within(items[1]).getByText(new RegExp(t('sessions.item.turnsOne')))).toBeInTheDocument()
    expect(within(items[2]).getByText(/7/)).toBeInTheDocument()
  })

  it('shows a loading skeleton while the sessions request is pending, without layout jump', async () => {
    let resolveSessions: (value: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      resolveSessions = resolve
    })
    mockFetch({ sessions: () => pending })
    render(<SessionsScreen />)

    expect(screen.getByText(t('sessions.loading'))).toBeInTheDocument()
    resolveSessions(jsonResponse([]))
    await screen.findByText(t('sessions.empty.title'))
  })

  it('shows an ErrorState with working retry when GET /api/sessions returns 500', async () => {
    const user = userEvent.setup()
    let callCount = 0
    mockFetch({
      sessions: () => {
        callCount += 1
        return callCount === 1 ? jsonResponse({}, 500) : jsonResponse([])
      },
    })
    render(<SessionsScreen />)

    await screen.findByRole('button', { name: t('common.retry') })
    await user.click(screen.getByRole('button', { name: t('common.retry') }))
    await screen.findByText(t('sessions.empty.title'))
    expect(callCount).toBe(2)
  })

  it('shows the offline error family when fetch rejects', async () => {
    mockFetch({
      sessions: () => {
        throw new TypeError('Failed to fetch')
      },
    })
    render(<SessionsScreen />)

    expect(await screen.findByText(t('error.offline.title'))).toBeInTheDocument()
  })

  it('disables the scenario select and shows an error when scenarios fail to load, keeping the session list navigable', async () => {
    mockFetch({
      scenarios: () => jsonResponse({}, 500),
      sessions: () =>
        jsonResponse([{ id: 'a', scenarioId: 's1', scenarioName: 'Alpha', turnCount: 2, updatedAt: new Date().toISOString(), location: 'x' }]),
    })
    render(<SessionsScreen />)

    expect(await screen.findByText(t('sessions.new.scenariosError'))).toBeInTheDocument()
    expect(screen.getByLabelText(t('sessions.new.scenarioLabel'))).toBeDisabled()
    expect(await screen.findByRole('button', { name: /Alpha/ })).toBeEnabled()
  })

  it('renders a single scenario already selected and enabled', async () => {
    mockFetch({ scenarios: () => jsonResponse([SCENARIO]), sessions: () => jsonResponse([]) })
    render(<SessionsScreen />)

    const select = await screen.findByLabelText(t('sessions.new.scenarioLabel'))
    expect(select).toBeEnabled()
    expect((select as HTMLSelectElement).value).toBe(SCENARIO.id)
    expect(screen.getByText(SCENARIO.tagline)).toBeInTheDocument()
  })

  it('renders no secondary line when the scenario has no tagline', async () => {
    mockFetch({ scenarios: () => jsonResponse([SCENARIO_NO_TAGLINE]), sessions: () => jsonResponse([]) })
    render(<SessionsScreen />)

    await screen.findByLabelText(t('sessions.new.scenarioLabel'))
    expect(document.querySelector('.sessions-new-tagline')).toBeNull()
  })

  it('creates a session on submit and navigates to the session hash, sending only one POST on a double click', async () => {
    const user = userEvent.setup()
    let postCalls = 0
    const fetchMock = mockFetch({
      scenarios: () => jsonResponse([SCENARIO]),
      sessions: () => jsonResponse([]),
      post: () => {
        postCalls += 1
        return jsonResponse(
          { id: 'sess-1', scenarioId: SCENARIO.id, scenarioName: SCENARIO.name, prologue: 'once', playGuide: null, turns: [], hud: { turn: 0, location: '', time: '', weather: '' } },
          201,
        )
      },
    })
    render(<SessionsScreen />)

    const submit = await screen.findByRole('button', { name: t('sessions.new.submit') })
    await user.dblClick(submit)

    await waitFor(() => expect(location.hash).toBe('#/session/sess-1'))
    expect(postCalls).toBe(1)
    expect(fetchMock).toHaveBeenCalled()
  })

  it('shows an inline error on POST failure, re-enables controls and keeps the hash unchanged', async () => {
    const user = userEvent.setup()
    mockFetch({
      scenarios: () => jsonResponse([SCENARIO]),
      sessions: () => jsonResponse([]),
      post: () => jsonResponse({}, 500),
    })
    render(<SessionsScreen />)

    const submit = await screen.findByRole('button', { name: t('sessions.new.submit') })
    await user.click(submit)

    expect(await screen.findByText(t('sessions.new.error'))).toBeInTheDocument()
    expect(location.hash).toBe('')
    expect(submit).toBeEnabled()
    const select = screen.getByLabelText(t('sessions.new.scenarioLabel')) as HTMLSelectElement
    expect(select.value).toBe(SCENARIO.id)
    expect(select).toBeEnabled()
  })

  it('navigates to the session hash when a list item is clicked', async () => {
    const user = userEvent.setup()
    mockFetch({
      sessions: () =>
        jsonResponse([{ id: 'sess-9', scenarioId: 's1', scenarioName: 'Alpha', turnCount: 3, updatedAt: new Date().toISOString(), location: 'x' }]),
    })
    render(<SessionsScreen />)

    const item = await screen.findByRole('button', { name: /Alpha/ })
    await user.click(item)
    expect(location.hash).toBe('#/session/sess-9')
  })

  it('shows coherent relative time for now and three days ago', async () => {
    const now = new Date().toISOString()
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString()
    mockFetch({
      sessions: () =>
        jsonResponse([
          { id: 'a', scenarioId: 's1', scenarioName: 'Now', turnCount: 1, updatedAt: now, location: 'x' },
          { id: 'b', scenarioId: 's2', scenarioName: 'ThreeDays', turnCount: 1, updatedAt: threeDaysAgo, location: 'x' },
        ]),
    })
    render(<SessionsScreen />)

    const nowItem = await screen.findByRole('button', { name: /Now/ })
    const oldItem = await screen.findByRole('button', { name: /ThreeDays/ })
    expect(nowItem).toHaveAttribute('title', now)
    expect(oldItem).toHaveAttribute('title', threeDaysAgo)
  })
})
