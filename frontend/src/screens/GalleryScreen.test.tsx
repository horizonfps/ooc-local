import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GalleryScreen } from './GalleryScreen'
import { t } from '../i18n'
import type { Gallery } from '../api'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function mockFetch(handler: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(async () => handler())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const BASE_GALLERY: Gallery = {
  scenarioId: 'school',
  scenarioName: 'The School',
  totals: { achievements: 2, achievementsUnlocked: 1, endings: 1, endingsUnlocked: 0 },
  starts: [
    {
      id: 'start-a',
      name: 'Start A',
      achievements: [
        {
          id: 'unlocked-achievement',
          name: 'Broke the window',
          rarity: 'rare',
          hint: null,
          unlocked: true,
          unlockedAt: new Date().toISOString(),
          sessionId: 's1',
          turn: 5,
        },
        {
          id: 'derrotei-sukuna',
          name: 'Defeated Sukuna',
          rarity: 'legendary',
          hint: 'Fight the strongest foe.',
          unlocked: false,
          unlockedAt: null,
          sessionId: null,
          turn: null,
        },
      ],
      endings: [
        {
          id: 'caderno-queimado',
          name: 'The Burnt Notebook',
          rarity: 'epic',
          hint: null,
          unlocked: false,
          unlockedAt: null,
          sessionId: null,
          turn: null,
        },
      ],
    },
  ],
}

beforeEach(() => {
  location.hash = ''
})

afterEach(() => {
  vi.unstubAllGlobals()
  location.hash = ''
})

describe('GalleryScreen', () => {
  it('shows two lists per start, unlocked with name and turn, locked with ??? and hint', async () => {
    mockFetch(() => jsonResponse(BASE_GALLERY))
    render(<GalleryScreen scenarioId="school" />)

    expect(await screen.findByText('Start A')).toBeInTheDocument()
    expect(screen.getByText(t('gallery.achievements.heading'))).toBeInTheDocument()
    expect(screen.getByText(t('gallery.endings.heading'))).toBeInTheDocument()

    expect(screen.getByText('Broke the window')).toBeInTheDocument()
    expect(screen.getByText(/Turn 5/)).toBeInTheDocument()

    expect(screen.getAllByText(t('gallery.locked.name')).length).toBeGreaterThan(0)
    expect(screen.getByText('Fight the strongest foe.')).toBeInTheDocument()
  })

  it('shows a progress line with the four distinct totals', async () => {
    const gallery: Gallery = { ...BASE_GALLERY, totals: { achievements: 7, achievementsUnlocked: 3, endings: 11, endingsUnlocked: 9 } }
    mockFetch(() => jsonResponse(gallery))
    render(<GalleryScreen scenarioId="school" />)

    await screen.findByText('Start A')
    const progress = document.querySelector('.gallery-progress')
    expect(progress).not.toBeNull()
    const text = progress!.textContent ?? ''
    expect(text).toMatch(/\b3\b/)
    expect(text).toMatch(/\b7\b/)
    expect(text).toMatch(/\b9\b/)
    expect(text).toMatch(/\b11\b/)
  })

  it('shows the rarity label for rare, epic and legendary entries, not just common', async () => {
    mockFetch(() => jsonResponse(BASE_GALLERY))
    render(<GalleryScreen scenarioId="school" />)

    await screen.findByText('Start A')
    const rareItem = document.querySelector('#gallery-entry-start-a-achievements-0') as HTMLElement
    expect(within(rareItem).getByText(t('game.rarity.rare'))).toBeInTheDocument()

    const legendaryItem = document.querySelector('#gallery-entry-start-a-achievements-1') as HTMLElement
    expect(within(legendaryItem).getByText(t('game.rarity.legendary'))).toBeInTheDocument()

    const epicItem = document.querySelector('#gallery-entry-start-a-endings-0') as HTMLElement
    expect(within(epicItem).getByText(t('game.rarity.epic'))).toBeInTheDocument()
  })

  it('shows the no-hint line for a locked entry without a hint', async () => {
    mockFetch(() => jsonResponse(BASE_GALLERY))
    render(<GalleryScreen scenarioId="school" />)

    expect(await screen.findByText(t('gallery.locked.noHint'))).toBeInTheDocument()
  })

  it('brings the screen-reader text for a locked entry inside a visually-hidden element', async () => {
    mockFetch(() => jsonResponse(BASE_GALLERY))
    render(<GalleryScreen scenarioId="school" />)

    const texts = await screen.findAllByText(t('gallery.locked.sr'))
    expect(texts.length).toBeGreaterThan(0)
    for (const node of texts) {
      expect(node).toHaveClass('visually-hidden')
    }
  })

  it('falls back to common class and label for an unknown rarity', async () => {
    const gallery: Gallery = {
      ...BASE_GALLERY,
      starts: [
        {
          id: 'start-a',
          name: 'Start A',
          achievements: [
            { id: 'weird', name: 'Weird', rarity: 'mythic', hint: null, unlocked: true, unlockedAt: new Date().toISOString(), sessionId: 's1', turn: 1 },
          ],
          endings: [],
        },
      ],
    }
    mockFetch(() => jsonResponse(gallery))
    render(<GalleryScreen scenarioId="school" />)

    const name = await screen.findByText('Weird')
    expect(name).toHaveClass('game-rarity--common')
    expect(screen.getByText(t('game.rarity.common'))).toBeInTheDocument()
  })

  it('shows the empty state for a scenario with no achievements', async () => {
    const gallery: Gallery = { ...BASE_GALLERY, starts: [{ id: 'start-a', name: 'Start A', achievements: [], endings: [] }] }
    mockFetch(() => jsonResponse(gallery))
    render(<GalleryScreen scenarioId="school" />)

    expect(await screen.findByText(t('gallery.empty.title'))).toBeInTheDocument()
  })

  it('shows two sections in response order for two starts', async () => {
    const gallery: Gallery = {
      ...BASE_GALLERY,
      starts: [
        { id: 'start-a', name: 'Start A', achievements: [], endings: [] },
        { id: 'start-b', name: 'Start B', achievements: [BASE_GALLERY.starts[0].achievements[0]], endings: [] },
      ],
    }
    mockFetch(() => jsonResponse(gallery))
    render(<GalleryScreen scenarioId="school" />)

    const headings = await screen.findAllByRole('heading', { level: 2 })
    expect(headings.map((h) => h.textContent)).toEqual(['Start A', 'Start B'])
  })

  it('never leaks the name or id of a locked entry into the rendered HTML', async () => {
    mockFetch(() => jsonResponse(BASE_GALLERY))
    const { container } = render(<GalleryScreen scenarioId="school" />)

    await screen.findByText('Start A')
    expect(container.innerHTML).not.toContain('Defeated Sukuna')
    expect(container.innerHTML).not.toContain('derrotei-sukuna')
    expect(container.innerHTML).not.toContain('caderno-queimado')
  })

  it('uses positional element ids for entries, not the entry id', async () => {
    mockFetch(() => jsonResponse(BASE_GALLERY))
    const { container } = render(<GalleryScreen scenarioId="school" />)

    await screen.findByText('Start A')
    expect(container.querySelector('#gallery-entry-start-a-achievements-0')).toBeInTheDocument()
    expect(container.querySelector('#gallery-entry-start-a-achievements-1')).toBeInTheDocument()
    expect(container.querySelector('#gallery-entry-start-a-endings-0')).toBeInTheDocument()
  })

  it('shows an ErrorState with working retry on a network error', async () => {
    const user = userEvent.setup()
    let callCount = 0
    mockFetch(() => {
      callCount += 1
      return callCount === 1 ? jsonResponse({}, 500) : jsonResponse(BASE_GALLERY)
    })
    render(<GalleryScreen scenarioId="school" />)

    await screen.findByRole('button', { name: t('common.retry') })
    await user.click(screen.getByRole('button', { name: t('common.retry') }))
    await screen.findByText('Start A')
    expect(callCount).toBe(2)
  })

  it('shows a not-found message on 404', async () => {
    mockFetch(() => jsonResponse({}, 404))
    render(<GalleryScreen scenarioId="missing" />)

    expect(await screen.findByText(t('gallery.notFound.title'))).toBeInTheDocument()
  })

  it('shows a working back button on the 404 state', async () => {
    const user = userEvent.setup()
    location.hash = '#/gallery/missing'
    mockFetch(() => jsonResponse({}, 404))
    render(<GalleryScreen scenarioId="missing" />)

    await screen.findByText(t('gallery.notFound.title'))
    const back = screen.getByRole('button', { name: t('common.back') })
    await user.click(back)
    expect(location.hash).toBe('#/')
  })

  it('does not crash and omits the date for an unlocked entry with an unparseable unlockedAt', async () => {
    const gallery: Gallery = {
      ...BASE_GALLERY,
      starts: [
        {
          id: 'start-a',
          name: 'Start A',
          achievements: [
            { id: 'broken-date', name: 'Broken Date', rarity: 'rare', hint: null, unlocked: true, unlockedAt: 'not-a-date', sessionId: 's1', turn: 3 },
          ],
          endings: [],
        },
      ],
    }
    mockFetch(() => jsonResponse(gallery))
    render(<GalleryScreen scenarioId="school" />)

    expect(await screen.findByText('Broken Date')).toBeInTheDocument()
    expect(document.querySelector('.gallery-entry-when')).toBeNull()
  })

  it('omits the turn when the entry has no turn recorded', async () => {
    const gallery: Gallery = {
      ...BASE_GALLERY,
      starts: [
        {
          id: 'start-a',
          name: 'Start A',
          achievements: [
            { id: 'no-turn', name: 'No Turn', rarity: 'rare', hint: null, unlocked: true, unlockedAt: new Date().toISOString(), sessionId: 's1', turn: null },
          ],
          endings: [],
        },
      ],
    }
    mockFetch(() => jsonResponse(gallery))
    render(<GalleryScreen scenarioId="school" />)

    await screen.findByText('No Turn')
    const when = document.querySelector('.gallery-entry-when')
    expect(when).not.toBeNull()
    expect(when!.textContent).not.toMatch(/Turn 0/)
    expect(when!.textContent).not.toContain('Turn')
  })

  it('renders the achievements list before the endings list within a start', async () => {
    mockFetch(() => jsonResponse(BASE_GALLERY))
    render(<GalleryScreen scenarioId="school" />)

    await screen.findByText('Start A')
    const headings = document.querySelectorAll('.gallery-section h3')
    expect(Array.from(headings).map((h) => h.textContent)).toEqual([t('gallery.achievements.heading'), t('gallery.endings.heading')])
  })

  it('shows a loading skeleton with a Loading node while fetching', async () => {
    let resolveGallery: (value: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      resolveGallery = resolve
    })
    mockFetch(() => pending)
    render(<GalleryScreen scenarioId="school" />)

    expect(screen.getByRole('status')).toBeInTheDocument()
    resolveGallery(jsonResponse(BASE_GALLERY))
    await screen.findByText('Start A')
  })

  it('refetches and refocuses the heading when scenarioId changes', async () => {
    mockFetch(() => jsonResponse(BASE_GALLERY))
    const { rerender } = render(<GalleryScreen scenarioId="school" />)
    await screen.findByText('Start A')

    const other: Gallery = { ...BASE_GALLERY, scenarioName: 'Other', starts: [{ id: 'start-b', name: 'Start B', achievements: [], endings: [] }] }
    mockFetch(() => jsonResponse(other))
    rerender(<GalleryScreen scenarioId="other" />)

    const heading = await screen.findByRole('heading', { level: 1, name: 'Other' })
    expect(heading).toHaveFocus()
  })
})
