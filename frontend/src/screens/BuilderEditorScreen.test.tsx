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
  world: 'A dusty old school.',
  starts: {
    default: {
      id: 'default',
      name: 'Default start',
      prologue: '',
      opening_scene: '',
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
    render(<BuilderEditorScreen scenarioId="school" tab="identity" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-identity')
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

  it('keeps the draft when the tab prop changes', async () => {
    const user = userEvent.setup()
    mockFetch(() => jsonResponse(DOCUMENT))
    const { rerender } = render(<BuilderEditorScreen scenarioId="school" tab="identity" />)

    const editButton = await screen.findByTestId('builder-tab-demo-edit-identity')
    await user.click(editButton)
    expect(screen.getByText(t('builder.editor.dirty'))).toBeInTheDocument()

    rerender(<BuilderEditorScreen scenarioId="school" tab="world" />)
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
})
