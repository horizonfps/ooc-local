import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BuilderListScreen } from './BuilderListScreen'
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
