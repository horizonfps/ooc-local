import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BuilderEditorScreen } from './BuilderEditorScreen'
import { t } from '../i18n'

const DOCUMENT = {
  revision: 'rev-1',
  meta: {
    name: 'The School',
    tagline: 'A haunted hallway',
    description: null,
    locale: 'en',
    tags: [],
    default_start: 'default',
    world_mode: 'guided',
  },
  world: '## Universe\n\nA dusty old school.',
  starts: {
    default: {
      id: 'default',
      name: 'Default start',
      prologue: 'It begins.',
      opening_scene: 'A hallway at night.',
      play_guide: null,
      suggestions: [],
      hud: { location: 'Hallway', time: '08:00', weather: 'clear' },
      characters: ['ally'],
    },
  },
  characters: {
    ally: {
      name: 'Ally',
      role: 'friend',
      appearance: '',
      personality: '',
      voice: '',
      mind: { feeling: '', goal: '', opinion_of_player: null, secret_plan: null },
      sprite: null,
      anchor: false,
      emotions: ['default'],
    },
  },
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function mockFetch(handler: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url === '/api/builder/scenarios/school') return handler()
    throw new Error(`unexpected fetch ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mockFetchWithSave(getHandler: () => Response | Promise<Response>, putHandler: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url !== '/api/builder/scenarios/school') throw new Error(`unexpected fetch ${url}`)
    if (init?.method === 'PUT') return putHandler()
    return getHandler()
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

describe('BuilderEditorScreen', () => {
  it('loads and renders the tablist with the tab from the hash selected', async () => {
    mockFetch(() => jsonResponse(DOCUMENT))
    render(<BuilderEditorScreen scenarioId="school" tab="world" />)

    expect(await screen.findByRole('heading', { name: 'The School' })).toBeInTheDocument()
    const tablist = screen.getByRole('tablist', { name: t('builder.editor.tabs.label') })
    const tabs = within(tablist).getAllByRole('tab')
    expect(tabs).toHaveLength(5)
    const worldTab = within(tablist).getByRole('tab', { name: t('builder.editor.tab.world') })
    expect(worldTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(t('builder.editor.clean'))).toBeInTheDocument()
  })

  it('marks dirty on onChange from a tab placeholder and clears it when undone', async () => {
    const user = userEvent.setup()
    mockFetch(() => jsonResponse(DOCUMENT))
    render(<BuilderEditorScreen scenarioId="school" tab="characters" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-characters')
    await user.click(editButton)
    expect(screen.getByText(t('builder.editor.dirty'))).toBeInTheDocument()

    await user.click(editButton)
    expect(screen.getByText(t('builder.editor.clean'))).toBeInTheDocument()
  })

  it('links each tab to its own hash and moves roving focus with the arrow keys', async () => {
    const user = userEvent.setup()
    mockFetch(() => jsonResponse(DOCUMENT))
    render(<BuilderEditorScreen scenarioId="school" tab="identity" />)

    const identityTab = await screen.findByRole('tab', { name: t('builder.editor.tab.identity') })
    const worldTab = screen.getByRole('tab', { name: t('builder.editor.tab.world') })
    expect(worldTab).toHaveAttribute('href', '#/builder/school/world')

    identityTab.focus()
    await user.keyboard('{ArrowRight}')
    expect(document.activeElement).toBe(worldTab)

    await user.keyboard('{Home}')
    expect(document.activeElement).toBe(identityTab)
  })

  it('renders the identity tab with the name field from the draft and marks dirty on edit', async () => {
    const user = userEvent.setup()
    mockFetch(() => jsonResponse(DOCUMENT))
    render(<BuilderEditorScreen scenarioId="school" tab="identity" />)

    const nameField = await screen.findByLabelText(t('builder.identity.name'))
    expect(nameField).toHaveValue('The School')
    expect(screen.getByText(t('builder.editor.clean'))).toBeInTheDocument()

    await user.type(nameField, ' Reborn')
    expect(screen.getByText(t('builder.editor.dirty'))).toBeInTheDocument()
  })

  it('keeps the draft when the tab prop changes', async () => {
    const user = userEvent.setup()
    mockFetch(() => jsonResponse(DOCUMENT))
    const { rerender } = render(<BuilderEditorScreen scenarioId="school" tab="characters" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-characters')
    await user.click(editButton)
    expect(screen.getByText(t('builder.editor.dirty'))).toBeInTheDocument()

    rerender(<BuilderEditorScreen scenarioId="school" tab="starts" />)
    expect(await screen.findByText(t('builder.editor.dirty'))).toBeInTheDocument()
  })

  it('shows the not found state for a 404', async () => {
    mockFetch(() => jsonResponse({ detail: 'scenario not found' }, 404))
    render(<BuilderEditorScreen scenarioId="school" tab="identity" />)

    expect(await screen.findByText(t('builder.editor.notFound.title'))).toBeInTheDocument()
    expect(screen.getByText(t('builder.editor.notFound.body'))).toBeInTheDocument()
    expect(screen.queryByRole('tablist')).toBeNull()
  })

  it('shows the invalid state for a 422 with the reason interpolated, and no editable fields', async () => {
    mockFetch(() => jsonResponse({ detail: 'scenario.yaml: bad yaml' }, 422))
    render(<BuilderEditorScreen scenarioId="school" tab="identity" />)

    expect(await screen.findByText(t('builder.editor.invalid.title'))).toBeInTheDocument()
    expect(screen.getByText(t('builder.editor.invalid.body', { reason: 'scenario.yaml: bad yaml' }))).toBeInTheDocument()
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('shows the generic error state with retry for a 500', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch(() => jsonResponse({ detail: 'boom' }, 500))
    render(<BuilderEditorScreen scenarioId="school" tab="identity" />)

    expect(await screen.findByText(t('error.unexpected.title'))).toBeInTheDocument()
    const retryButton = screen.getByRole('button', { name: t('common.retry') })

    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school') return jsonResponse(DOCUMENT)
      throw new Error(`unexpected fetch ${url}`)
    })
    await user.click(retryButton)

    expect(await screen.findByRole('heading', { name: 'The School' })).toBeInTheDocument()
  })

  it('saves an edit with a PUT carrying the revision and returns to clean with the new revision', async () => {
    const user = userEvent.setup()
    let putBody: unknown = null
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url !== '/api/builder/scenarios/school') throw new Error(`unexpected fetch ${url}`)
      if (init?.method === 'PUT') {
        putBody = JSON.parse(String(init.body))
        return jsonResponse({ revision: 'rev-2' })
      }
      return jsonResponse(DOCUMENT)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<BuilderEditorScreen scenarioId="school" tab="characters" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-characters')
    await user.click(editButton)
    expect(screen.getByText(t('builder.editor.dirty'))).toBeInTheDocument()

    const saveButton = screen.getByRole('button', { name: t('builder.editor.save') })
    await user.click(saveButton)

    expect(await screen.findByText(t('builder.editor.clean'))).toBeInTheDocument()
    expect(putBody).toMatchObject({ revision: 'rev-1', force: false })
    expect(screen.getByRole('button', { name: t('builder.editor.save') })).toBeDisabled()
  })

  it('saves with Ctrl+S from anywhere in the editor', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetchWithSave(
      () => jsonResponse(DOCUMENT),
      () => jsonResponse({ revision: 'rev-2' }),
    )
    render(<BuilderEditorScreen scenarioId="school" tab="characters" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-characters')
    await user.click(editButton)
    expect(screen.getByText(t('builder.editor.dirty'))).toBeInTheDocument()

    await user.keyboard('{Control>}s{/Control}')

    expect(await screen.findByText(t('builder.editor.clean'))).toBeInTheDocument()
    const putCalls = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'PUT')
    expect(putCalls).toHaveLength(1)
  })

  it('opens the conflict dialog on 409 and resends with force:true on overwrite', async () => {
    const user = userEvent.setup()
    let putCount = 0
    let lastForce: unknown = null
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url !== '/api/builder/scenarios/school') throw new Error(`unexpected fetch ${url}`)
      if (init?.method === 'PUT') {
        putCount += 1
        lastForce = JSON.parse(String(init.body)).force
        if (putCount === 1) return jsonResponse({ detail: 'revision conflict' }, 409)
        return jsonResponse({ revision: 'rev-2' })
      }
      return jsonResponse(DOCUMENT)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<BuilderEditorScreen scenarioId="school" tab="characters" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-characters')
    await user.click(editButton)
    await user.click(screen.getByRole('button', { name: t('builder.editor.save') }))

    const dialog = await screen.findByRole('dialog', { name: t('builder.editor.save.error.conflict.title') })
    await user.click(within(dialog).getByRole('button', { name: t('builder.editor.conflict.overwrite') }))

    expect(await screen.findByText(t('builder.editor.clean'))).toBeInTheDocument()
    expect(lastForce).toBe(true)
    expect(putCount).toBe(2)
  })

  it('shows the disabled-by-flag message on a 503 without retry', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetchWithSave(
      () => jsonResponse(DOCUMENT),
      () => jsonResponse({ detail: 'builder disabled by flag' }, 503),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<BuilderEditorScreen scenarioId="school" tab="characters" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-characters')
    await user.click(editButton)
    await user.click(screen.getByRole('button', { name: t('builder.editor.save') }))

    expect(await screen.findByText(t('builder.editor.save.error.disabled.title'))).toBeInTheDocument()
    expect(screen.getByText(t('builder.editor.save.error.disabled.body'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t('common.retry') })).toBeNull()
  })

  it('keeps the draft on a 500 and shows the save error', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetchWithSave(
      () => jsonResponse(DOCUMENT),
      () => jsonResponse({ detail: 'boom' }, 500),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<BuilderEditorScreen scenarioId="school" tab="characters" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-characters')
    await user.click(editButton)
    await user.click(screen.getByRole('button', { name: t('builder.editor.save') }))

    expect(await screen.findByText(t('builder.editor.save.error.title'))).toBeInTheDocument()
    expect(screen.getByText(t('builder.editor.dirty'))).toBeInTheDocument()
  })

  it('blocks the save on structural validation and the jump link goes to the Starts tab', async () => {
    const user = userEvent.setup()
    const invalidDocument = { ...DOCUMENT, starts: {} }
    mockFetch(() => jsonResponse(invalidDocument))
    render(<BuilderEditorScreen scenarioId="school" tab="characters" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-characters')
    await user.click(editButton)
    await user.click(screen.getByRole('button', { name: t('builder.editor.save') }))

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(t('builder.editor.validation.summaryTitle'))).toBeInTheDocument()
    const jumpLink = within(alert).getAllByRole('button')[0]
    await user.click(jumpLink)

    expect(location.hash).toBe('#/builder/school/starts')
  })

  it('asks for confirmation before reloading a dirty draft, and reloads on confirm', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch(() => jsonResponse(DOCUMENT))
    render(<BuilderEditorScreen scenarioId="school" tab="characters" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-characters')
    await user.click(editButton)
    await user.click(screen.getByRole('button', { name: t('builder.editor.reload') }))

    const dialog = await screen.findByRole('dialog', { name: t('builder.editor.reload.confirmTitle') })
    await user.click(within(dialog).getByRole('button', { name: t('common.cancel') }))
    expect(screen.getByText(t('builder.editor.dirty'))).toBeInTheDocument()
    expect(fetchMock.mock.calls).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: t('builder.editor.reload') }))
    const dialogAgain = await screen.findByRole('dialog', { name: t('builder.editor.reload.confirmTitle') })
    await user.click(within(dialogAgain).getByRole('button', { name: t('builder.editor.reload.confirmSubmit') }))

    expect(await screen.findByText(t('builder.editor.clean'))).toBeInTheDocument()
    expect(fetchMock.mock.calls).toHaveLength(2)
  })
})
