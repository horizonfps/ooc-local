import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MediaTab } from './MediaTab'
import type { BuilderDraft } from '../../screens/BuilderEditorScreen'
import type { MediaIndex } from '../../api'
import { t } from '../../i18n'

function baseDraft(): BuilderDraft {
  return {
    meta: {
      name: 'The School',
      tagline: null,
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
        prologue: 'It begins.',
        opening_scene: 'A hallway.',
        play_guide: null,
        suggestions: [],
        hud: { location: 'Hallway', time: '08:00', weather: 'clear' },
        characters: ['luca'],
      },
    },
    characters: {
      luca: {
        name: 'Luca',
        role: 'Janitor',
        appearance: 'Tall, gray coveralls.',
        personality: 'Quiet, watchful.',
        voice: 'Short sentences.',
        mind: { feeling: 'Bored', goal: 'Finish the round', opinion_of_player: null, secret_plan: null },
        sprite: null,
        anchor: false,
        emotions: ['default', 'happy'],
      },
    },
  }
}

function emptyIndex(): MediaIndex {
  return { cover: null, sprites: {}, backgrounds: {} }
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function makeFile(name: string, type: string, sizeBytes: number): File {
  const bytes = new Uint8Array(sizeBytes)
  return new File([bytes], name, { type })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('MediaTab', () => {
  it('shows one filled cell and the rest empty with the right summary', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ cover: null, sprites: { luca: { default: '/api/scenarios/school/media/sprites/luca/default.png' } }, backgrounds: {} }),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    expect(await screen.findByText(t('builder.media.summary', { filled: 1, total: 2 }))).toBeInTheDocument()
    expect(screen.getByAltText(t('builder.media.sprite.alt', { character: 'Luca', emotion: 'default' }))).toBeInTheDocument()
    expect(screen.getByText(t('builder.media.cell.empty'))).toBeInTheDocument()
  })

  it('uploading a sprite sends FormData with kind=sprite, key and character, and the cell fills in', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school/media' && (!init || init.method === undefined)) {
        return jsonResponse(emptyIndex())
      }
      if (url === '/api/builder/scenarios/school/media' && init?.method === 'POST') {
        expect(init.body).toBeInstanceOf(FormData)
        const body = init.body as FormData
        expect(body.get('kind')).toBe('sprite')
        expect(body.get('key')).toBe('default')
        expect(body.get('character')).toBe('luca')
        return jsonResponse({ path: 'sprites/luca/default.png', url: '/api/scenarios/school/media/sprites/luca/default.png' }, 201)
      }
      throw new Error(`unexpected fetch ${url} ${init?.method}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)
    await screen.findByText(t('builder.media.summary', { filled: 0, total: 2 }))

    const input = screen.getByLabelText(t('builder.media.sprite.upload', { character: 'Luca', emotion: 'default' }))
    const user = userEvent.setup()
    await user.upload(input, makeFile('x.png', 'image/png', 1024))

    const img = await screen.findByAltText(t('builder.media.sprite.alt', { character: 'Luca', emotion: 'default' }))
    expect(img).toHaveAttribute('src', expect.stringContaining('/api/scenarios/school/media/sprites/luca/default.png?t='))
    expect(await screen.findByText(t('builder.media.uploaded', { name: 'default.png' }))).toBeInTheDocument()
  })

  it('removing with confirmation sends DELETE and the cell goes back to empty', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school/media' && (!init || init.method === undefined)) {
        return jsonResponse({ cover: null, sprites: { luca: { default: '/api/scenarios/school/media/sprites/luca/default.png' } }, backgrounds: {} })
      }
      if (url.startsWith('/api/builder/scenarios/school/media?') && init?.method === 'DELETE') {
        return jsonResponse(null, 204)
      }
      throw new Error(`unexpected fetch ${url} ${init?.method}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    const removeButton = await screen.findByLabelText(t('builder.media.sprite.remove', { character: 'Luca', emotion: 'default' }))
    const user = userEvent.setup()
    await user.click(removeButton)

    await user.click(screen.getByRole('button', { name: t('common.remove') }))

    expect(await screen.findByText(t('builder.media.removed', { name: 'default.png' }))).toBeInTheDocument()
    expect(screen.queryByAltText(t('builder.media.sprite.alt', { character: 'Luca', emotion: 'default' }))).not.toBeInTheDocument()
  })

  it('the empty default cell shows the emptyDefault message', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(emptyIndex()))
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    expect(await screen.findByText(t('builder.media.cell.emptyDefault'))).toBeInTheDocument()
  })

  it('dropping a file on the cell uploads it the same way as the input', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school/media' && (!init || init.method === undefined)) {
        return jsonResponse(emptyIndex())
      }
      if (url === '/api/builder/scenarios/school/media' && init?.method === 'POST') {
        return jsonResponse({ path: 'sprites/luca/default.png', url: '/api/scenarios/school/media/sprites/luca/default.png' }, 201)
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)
    await screen.findByText(t('builder.media.cell.emptyDefault'))

    const cell = screen.getByTestId('media-cell-luca-default')
    const file = makeFile('drop.png', 'image/png', 1024)
    const dataTransfer = { files: [file] }

    const label = cell.querySelector('label') as HTMLElement
    const dropEvent = new Event('drop', { bubbles: true, cancelable: true }) as unknown as DragEvent
    Object.defineProperty(dropEvent, 'dataTransfer', { value: dataTransfer })
    label.dispatchEvent(dropEvent)

    const img = await screen.findByAltText(t('builder.media.sprite.alt', { character: 'Luca', emotion: 'default' }))
    expect(img).toBeInTheDocument()
  })

  it('replacing an image announces replaced and the URL gains a ?t=', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school/media' && (!init || init.method === undefined)) {
        return jsonResponse({ cover: null, sprites: { luca: { default: '/api/scenarios/school/media/sprites/luca/default.png' } }, backgrounds: {} })
      }
      if (url === '/api/builder/scenarios/school/media' && init?.method === 'POST') {
        return jsonResponse({ path: 'sprites/luca/default.png', url: '/api/scenarios/school/media/sprites/luca/default.png' }, 201)
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)
    await screen.findByAltText(t('builder.media.sprite.alt', { character: 'Luca', emotion: 'default' }))

    const input = screen.getByLabelText(t('builder.media.sprite.upload', { character: 'Luca', emotion: 'default' }))
    const user = userEvent.setup()
    await user.upload(input, makeFile('new.png', 'image/png', 1024))

    expect(await screen.findByText(t('builder.media.replaced', { name: 'default.png' }))).toBeInTheDocument()
    const img = await screen.findByAltText(t('builder.media.sprite.alt', { character: 'Luca', emotion: 'default' }))
    expect(img).toHaveAttribute('src', expect.stringContaining('?t='))
  })

  it('a 413 upload response shows the size error with retry, only for that cell', async () => {
    let calls = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school/media' && (!init || init.method === undefined)) {
        return jsonResponse(emptyIndex())
      }
      if (url === '/api/builder/scenarios/school/media' && init?.method === 'POST') {
        calls += 1
        return jsonResponse({ detail: 'file too large' }, 413)
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)
    await screen.findByText(t('builder.media.cell.emptyDefault'))

    const input = screen.getByLabelText(t('builder.media.sprite.upload', { character: 'Luca', emotion: 'default' }))
    const user = userEvent.setup()
    await user.upload(input, makeFile('x.png', 'image/png', 1024))

    expect(await screen.findByText(t('builder.media.error.size', { max: 8 }))).toBeInTheDocument()
    expect(calls).toBe(1)

    await user.click(screen.getByRole('button', { name: t('common.retry') }))
    expect(calls).toBe(2)

    expect(screen.getByText(t('builder.media.cell.empty'))).toBeInTheDocument()
  })

  it('a 503 upload response shows the disabled error', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school/media' && (!init || init.method === undefined)) {
        return jsonResponse(emptyIndex())
      }
      return jsonResponse({ detail: 'builder disabled by flag' }, 503)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)
    await screen.findByText(t('builder.media.cell.emptyDefault'))

    const input = screen.getByLabelText(t('builder.media.sprite.upload', { character: 'Luca', emotion: 'default' }))
    const user = userEvent.setup()
    await user.upload(input, makeFile('x.png', 'image/png', 1024))

    expect(await screen.findByText(t('builder.media.error.disabled'))).toBeInTheDocument()
  })

  it('a failed index fetch shows an ErrorState with retry, without crashing the tab', async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError('network down')
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    expect(await screen.findByRole('button', { name: t('common.retry') })).toBeInTheDocument()
  })
})
