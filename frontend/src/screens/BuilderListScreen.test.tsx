import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BuilderListScreen, slugify } from './BuilderListScreen'
import { t } from '../i18n'

const SCENARIO_A = {
  id: 'school',
  name: 'The School',
  tagline: 'A haunted hallway',
  locale: 'en',
  startCount: 1,
  characterCount: 0,
  hasCover: false,
  updatedAt: new Date().toISOString(),
  status: 'ok' as const,
}

const SCENARIO_B = {
  id: 'noir',
  name: 'Noir City',
  tagline: null,
  locale: 'pt-br',
  startCount: 2,
  characterCount: 1,
  hasCover: false,
  updatedAt: new Date().toISOString(),
  status: 'ok' as const,
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
    if (url === '/api/builder/scenarios') return handler()
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

describe('BuilderListScreen', () => {
  it('renders scenarios with name, tagline and meta with correct plurals', async () => {
    mockFetch(() => jsonResponse([SCENARIO_A, SCENARIO_B]))
    render(<BuilderListScreen />)

    expect(await screen.findByText('The School')).toBeInTheDocument()
    expect(screen.getByText('A haunted hallway')).toBeInTheDocument()
    expect(screen.getByText('Noir City')).toBeInTheDocument()

    expect(screen.getByText(t('builder.list.item.meta', { starts: t('builder.list.item.startsOne'), characters: t('builder.list.item.charactersZero') }))).toBeInTheDocument()
    expect(
      screen.getByText(
        t('builder.list.item.meta', {
          starts: t('builder.list.item.startsOther', { count: 2 }),
          characters: t('builder.list.item.charactersOne'),
        }),
      ),
    ).toBeInTheDocument()
  })

  it('navigates to the editor hash when a valid card is clicked', async () => {
    const user = userEvent.setup()
    mockFetch(() => jsonResponse([SCENARIO_A]))
    render(<BuilderListScreen />)

    const link = await screen.findByRole('link', { name: t('builder.list.item.edit', { scenario: SCENARIO_A.name }) })
    await user.click(link)
    expect(location.hash).toBe(`#/builder/${SCENARIO_A.id}/identity`)
  })

  it('shows the reason for an invalid scenario and has no edit link', async () => {
    const invalid = { id: 'broken', name: 'broken', tagline: null, locale: 'en', startCount: 0, characterCount: 0, hasCover: false, updatedAt: new Date().toISOString(), status: 'invalid' as const, reason: 'bad yaml' }
    mockFetch(() => jsonResponse([invalid]))
    render(<BuilderListScreen />)

    expect(await screen.findByText(t('builder.list.item.broken'))).toBeInTheDocument()
    expect(screen.getByText(t('builder.list.item.brokenBody', { reason: 'bad yaml' }))).toBeInTheDocument()
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('falls back through cover extensions and lands on the placeholder', async () => {
    const withCover = { ...SCENARIO_A, hasCover: true }
    mockFetch(() => jsonResponse([withCover]))
    render(<BuilderListScreen />)

    const img = await screen.findByRole('img', { name: t('builder.list.item.coverAlt', { scenario: withCover.name }) })
    expect(img).toHaveAttribute('src', `/api/scenarios/${withCover.id}/media/cover.png`)

    act(() => {
      img.dispatchEvent(new Event('error'))
    })
    const imgJpg = await screen.findByRole('img', { name: t('builder.list.item.coverAlt', { scenario: withCover.name }) })
    expect(imgJpg).toHaveAttribute('src', `/api/scenarios/${withCover.id}/media/cover.jpg`)

    act(() => {
      imgJpg.dispatchEvent(new Event('error'))
    })
    const imgWebp = await screen.findByRole('img', { name: t('builder.list.item.coverAlt', { scenario: withCover.name }) })
    expect(imgWebp).toHaveAttribute('src', `/api/scenarios/${withCover.id}/media/cover.webp`)

    act(() => {
      imgWebp.dispatchEvent(new Event('error'))
    })
    expect(screen.queryByRole('img')).toBeNull()
    expect(document.querySelector('.builder-card-cover-placeholder')).toBeInTheDocument()
  })

  it('shows an empty state when there are no scenarios', async () => {
    mockFetch(() => jsonResponse([]))
    render(<BuilderListScreen />)

    expect(await screen.findByText(t('builder.list.empty.title'))).toBeInTheDocument()
  })

  it('shows an ErrorState with working retry when the GET returns 500', async () => {
    const user = userEvent.setup()
    let callCount = 0
    mockFetch(() => {
      callCount += 1
      return callCount === 1 ? jsonResponse({}, 500) : jsonResponse([])
    })
    render(<BuilderListScreen />)

    await screen.findByRole('button', { name: t('common.retry') })
    await user.click(screen.getByRole('button', { name: t('common.retry') }))
    await screen.findByText(t('builder.list.empty.title'))
    expect(callCount).toBe(2)
  })

  it('shows the offline error family when fetch rejects', async () => {
    mockFetch(() => {
      throw new TypeError('Failed to fetch')
    })
    render(<BuilderListScreen />)

    expect(await screen.findByText(t('builder.list.error.title'))).toBeInTheDocument()
  })

  it('reloads the list and announces it on reload', async () => {
    const user = userEvent.setup()
    mockFetch(() => jsonResponse([SCENARIO_A]))
    render(<BuilderListScreen />)

    await screen.findByText('The School')
    await user.click(screen.getByRole('button', { name: t('builder.list.reload') }))

    expect(await screen.findByText(t('builder.list.reloaded'))).toBeInTheDocument()
  })
})

describe('slugify', () => {
  it('lowercases, strips diacritics and hyphenates', () => {
    expect(slugify('Ação na Escola!')).toBe('acao-na-escola')
  })
})

type RouteHandler = (input: RequestInfo | URL, init?: RequestInit) => Response | Promise<Response>

function mockRoutedFetch(routes: Record<string, RouteHandler>) {
  const calls: { url: string; init?: RequestInit }[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, init })
    const key = `${init?.method ?? 'GET'} ${url}`
    for (const [pattern, handler] of Object.entries(routes)) {
      if (pattern === key || pattern === url) return handler(input, init)
    }
    throw new Error(`unexpected fetch ${key}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, calls }
}

describe('BuilderListScreen — create', () => {
  it('typing the name fills the folder by slug until the folder is edited by hand', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({ 'GET /api/builder/scenarios': () => jsonResponse([]) })
    render(<BuilderListScreen />)

    const nameInput = await screen.findByLabelText(t('builder.create.nameLabel'))
    const folderInput = screen.getByLabelText(t('builder.create.folderLabel'))

    await user.type(nameInput, 'Ação na Escola')
    expect(folderInput).toHaveValue('acao-na-escola')

    await user.clear(folderInput)
    await user.type(folderInput, 'minha-pasta')
    await user.type(nameInput, '!')
    expect(folderInput).toHaveValue('minha-pasta')
  })

  it('shows the duplicate message without POSTing when the folder is already in the list', async () => {
    const user = userEvent.setup()
    const { calls } = mockRoutedFetch({ 'GET /api/builder/scenarios': () => jsonResponse([SCENARIO_A]) })
    render(<BuilderListScreen />)

    await screen.findByText('The School')
    const nameInput = screen.getByLabelText(t('builder.create.nameLabel'))
    const folderInput = screen.getByLabelText(t('builder.create.folderLabel'))
    await user.type(nameInput, 'Second School')
    await user.clear(folderInput)
    await user.type(folderInput, 'school')

    await user.click(screen.getByRole('button', { name: t('builder.create.submit') }))

    expect(await screen.findByText(t('builder.create.error.duplicate', { folder: 'school' }))).toBeInTheDocument()
    expect(calls.filter((c) => c.init?.method === 'POST')).toHaveLength(0)
  })

  it('navigates to the identity screen for the new scenario on success', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({
      'GET /api/builder/scenarios': () => jsonResponse([]),
      'POST /api/builder/scenarios': () =>
        jsonResponse({ ...SCENARIO_A, id: 'novo', name: 'Novo' }, 201),
    })
    render(<BuilderListScreen />)

    await screen.findByRole('heading', { name: t('builder.create.heading') })
    await user.type(screen.getByLabelText(t('builder.create.nameLabel')), 'Novo')
    await user.click(screen.getByRole('button', { name: t('builder.create.submit') }))

    expect(location.hash).toBe('#/builder/novo/identity')
  })

  it('a double-click on submit fires a single POST', async () => {
    const user = userEvent.setup()
    let postCount = 0
    const { calls } = mockRoutedFetch({
      'GET /api/builder/scenarios': () => jsonResponse([]),
      'POST /api/builder/scenarios': () => {
        postCount += 1
        return jsonResponse({ ...SCENARIO_A, id: 'novo', name: 'Novo' }, 201)
      },
    })
    render(<BuilderListScreen />)

    await screen.findByRole('heading', { name: t('builder.create.heading') })
    await user.type(screen.getByLabelText(t('builder.create.nameLabel')), 'Novo')
    await user.dblClick(screen.getByRole('button', { name: t('builder.create.submit') }))

    await vi.waitFor(() => expect(calls.filter((c) => c.init?.method === 'POST')).toHaveLength(postCount))
    expect(postCount).toBe(1)
  })

  it('shows the empty state action and moves focus to the name field', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({ 'GET /api/builder/scenarios': () => jsonResponse([]) })
    render(<BuilderListScreen />)

    const action = await screen.findByRole('button', { name: t('builder.list.empty.action') })
    await user.click(action)

    expect(screen.getByLabelText(t('builder.create.nameLabel'))).toHaveFocus()
  })

  it('maps a 409 from the server to the duplicate message in the folder field, without navigating', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({
      'GET /api/builder/scenarios': () => jsonResponse([]),
      'POST /api/builder/scenarios': () => jsonResponse({ detail: 'folder exists' }, 409),
    })
    render(<BuilderListScreen />)

    await screen.findByRole('heading', { name: t('builder.create.heading') })
    await user.type(screen.getByLabelText(t('builder.create.nameLabel')), 'Novo')
    await user.click(screen.getByRole('button', { name: t('builder.create.submit') }))

    expect(await screen.findByText(t('builder.create.error.duplicate', { folder: 'novo' }))).toBeInTheDocument()
    expect(location.hash).toBe('')
  })
})

describe('BuilderListScreen — duplicate', () => {
  it('pre-fills {folder}-copy deduplicated against the loaded list and inserts the new card on success', async () => {
    const user = userEvent.setup()
    const withCopy = { ...SCENARIO_B, id: 'school-copy', name: 'School Copy' }
    mockRoutedFetch({
      'GET /api/builder/scenarios': () => jsonResponse([SCENARIO_A, withCopy]),
      'POST /api/builder/scenarios/school/duplicate': () =>
        jsonResponse({ ...SCENARIO_A, id: 'school-copy-2', name: 'School Copy 2' }, 201),
    })
    render(<BuilderListScreen />)

    await screen.findByText('The School')
    await user.click(screen.getByRole('button', { name: t('builder.duplicate.title', { scenario: 'The School' }) }))

    const dialog = screen.getByRole('dialog', { name: t('builder.duplicate.title', { scenario: 'The School' }) })
    const folderInput = within(dialog).getByLabelText(t('builder.duplicate.folderLabel'))
    expect(folderInput).toHaveValue('school-copy-2')

    await user.click(within(dialog).getByRole('button', { name: t('builder.duplicate.submit') }))

    expect(await screen.findByText('School Copy 2')).toBeInTheDocument()
  })

  it('shows builder.duplicate.error inside the dialog without closing it on server failure', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({
      'GET /api/builder/scenarios': () => jsonResponse([SCENARIO_A]),
      'POST /api/builder/scenarios/school/duplicate': () => jsonResponse({ detail: 'boom' }, 500),
    })
    render(<BuilderListScreen />)

    await screen.findByText('The School')
    await user.click(screen.getByRole('button', { name: t('builder.duplicate.title', { scenario: 'The School' }) }))
    const dialog = screen.getByRole('dialog', { name: t('builder.duplicate.title', { scenario: 'The School' }) })
    await user.click(within(dialog).getByRole('button', { name: t('builder.duplicate.submit') }))

    expect(await within(dialog).findByText(t('builder.duplicate.error'))).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: t('builder.duplicate.title', { scenario: 'The School' }) })).toBeInTheDocument()
  })

  it('reuses builder.create.error.invalidFolder for an invalid duplicate folder', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({ 'GET /api/builder/scenarios': () => jsonResponse([SCENARIO_A]) })
    render(<BuilderListScreen />)

    await screen.findByText('The School')
    await user.click(screen.getByRole('button', { name: t('builder.duplicate.title', { scenario: 'The School' }) }))
    const dialog = screen.getByRole('dialog', { name: t('builder.duplicate.title', { scenario: 'The School' }) })
    const folderInput = within(dialog).getByLabelText(t('builder.duplicate.folderLabel'))
    await user.clear(folderInput)
    await user.type(folderInput, 'Bad Folder!')
    await user.click(within(dialog).getByRole('button', { name: t('builder.duplicate.submit') }))

    expect(await within(dialog).findByText(t('builder.create.error.invalidFolder'))).toBeInTheDocument()
  })
})

describe('BuilderListScreen — delete', () => {
  it('only enables the destructive button once the folder name matches exactly, and moves focus to the h1 on success', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({
      'GET /api/builder/scenarios': () => jsonResponse([SCENARIO_A]),
      'DELETE /api/builder/scenarios/school': () => ({ ok: true, status: 204, json: async () => ({}) }) as Response,
    })
    render(<BuilderListScreen />)

    await screen.findByText('The School')
    await user.click(screen.getByRole('button', { name: t('builder.delete.title', { scenario: 'The School' }) }))
    const dialog = screen.getByRole('dialog', { name: t('builder.delete.title', { scenario: 'The School' }) })
    const confirmInput = within(dialog).getByLabelText(t('builder.delete.confirmLabel', { folder: 'school' }))
    const submitButton = within(dialog).getByRole('button', { name: t('builder.delete.submit') })
    expect(submitButton).toBeDisabled()

    await user.type(confirmInput, 'school')
    expect(submitButton).toBeEnabled()
    await user.click(submitButton)

    await vi.waitFor(() => expect(screen.queryByText('The School')).toBeNull())
    expect(screen.getByRole('heading', { name: t('builder.list.heading') })).toHaveFocus()
  })

  it('shows builder.delete.error inside the dialog and keeps the card on a 500', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({
      'GET /api/builder/scenarios': () => jsonResponse([SCENARIO_A]),
      'DELETE /api/builder/scenarios/school': () => jsonResponse({ detail: 'boom' }, 500),
    })
    render(<BuilderListScreen />)

    await screen.findByText('The School')
    await user.click(screen.getByRole('button', { name: t('builder.delete.title', { scenario: 'The School' }) }))
    const dialog = screen.getByRole('dialog', { name: t('builder.delete.title', { scenario: 'The School' }) })
    await user.type(within(dialog).getByLabelText(t('builder.delete.confirmLabel', { folder: 'school' })), 'school')
    await user.click(within(dialog).getByRole('button', { name: t('builder.delete.submit') }))

    expect(await within(dialog).findByText(t('builder.delete.error'))).toBeInTheDocument()
    expect(screen.getByText('The School')).toBeInTheDocument()
  })

  it('Escape closes the dialogs and returns focus to the trigger', async () => {
    const user = userEvent.setup()
    mockRoutedFetch({ 'GET /api/builder/scenarios': () => jsonResponse([SCENARIO_A]) })
    render(<BuilderListScreen />)

    await screen.findByText('The School')
    const trigger = screen.getByRole('button', { name: t('builder.delete.title', { scenario: 'The School' }) })
    await user.click(trigger)
    const dialog = screen.getByRole('dialog', { name: t('builder.delete.title', { scenario: 'The School' }) })
    await user.keyboard('{Escape}')

    expect(dialog).not.toHaveAttribute('open')
    expect(trigger).toHaveFocus()
  })
})
