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
    starts: {},
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

function startFixture(id: string, name: string, location: string) {
  return {
    id,
    name,
    prologue: 'It begins.',
    opening_scene: 'A hallway.',
    play_guide: null,
    suggestions: [],
    hud: { location, time: '08:00', weather: 'clear' },
    characters: null,
  }
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

  it('dropping a file outside the label is swallowed by the tab root, no fetch and no navigation', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(emptyIndex()))
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(
      <MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />,
    )
    await screen.findByText(t('builder.media.cell.emptyDefault'))

    const root = container.querySelector('.builder-media-tab') as HTMLElement
    const file = makeFile('stray.png', 'image/png', 1024)
    const dropEvent = new Event('drop', { bubbles: true, cancelable: true }) as unknown as DragEvent
    Object.defineProperty(dropEvent, 'dataTransfer', { value: { files: [file] } })
    const prevented = !root.dispatchEvent(dropEvent)

    expect(prevented).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('a 422 upload response shows the invalid key error', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school/media' && (!init || init.method === undefined)) {
        return jsonResponse(emptyIndex())
      }
      return jsonResponse({ detail: 'invalid key' }, 422)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)
    await screen.findByText(t('builder.media.cell.emptyDefault'))

    const input = screen.getByLabelText(t('builder.media.sprite.upload', { character: 'Luca', emotion: 'default' }))
    const user = userEvent.setup()
    await user.upload(input, makeFile('x.png', 'image/png', 1024))

    expect(await screen.findByText(t('builder.media.error.invalidKey'))).toBeInTheDocument()
  })

  it('two characters sharing the same sprite folder do not double count the same slot', async () => {
    const draft = baseDraft()
    draft.characters.mira = {
      name: 'Mira',
      role: 'Teacher',
      appearance: 'Neat suit.',
      personality: 'Strict.',
      voice: 'Formal.',
      mind: { feeling: 'Tired', goal: 'Grade papers', opinion_of_player: null, secret_plan: null },
      sprite: 'luca',
      anchor: false,
      emotions: ['default', 'happy'],
    }
    draft.characters.luca.sprite = 'luca'

    const fetchMock = vi.fn(async () =>
      jsonResponse({ cover: null, sprites: { luca: { default: '/api/scenarios/school/media/sprites/luca/default.png' } }, backgrounds: {} }),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={draft} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    expect(await screen.findByText(t('builder.media.summary', { filled: 1, total: 2 }))).toBeInTheDocument()
  })

  it('two starts with different locations seed two background slots', async () => {
    const draft = baseDraft()
    draft.starts.a = startFixture('a', 'Start A', 'Hallway')
    draft.starts.b = startFixture('b', 'Start B', 'Library')

    const fetchMock = vi.fn(async () => jsonResponse(emptyIndex()))
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={draft} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    expect(await screen.findByTestId('media-bg-cell-hallway')).toBeInTheDocument()
    expect(screen.getByTestId('media-bg-cell-library')).toBeInTheDocument()
  })

  it('uploading a background sends kind=background without character and fills the cell', async () => {
    const draft = baseDraft()
    draft.starts.a = startFixture('a', 'Start A', 'Hallway')

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school/media' && (!init || init.method === undefined)) {
        return jsonResponse(emptyIndex())
      }
      if (url === '/api/builder/scenarios/school/media' && init?.method === 'POST') {
        expect(init.body).toBeInstanceOf(FormData)
        const body = init.body as FormData
        expect(body.get('kind')).toBe('background')
        expect(body.get('key')).toBe('hallway')
        expect(body.get('character')).toBeNull()
        return jsonResponse({ path: 'backgrounds/hallway.png', url: '/api/scenarios/school/media/backgrounds/hallway.png' }, 201)
      }
      throw new Error(`unexpected fetch ${url} ${init?.method}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={draft} onChange={() => {}} errors={[]} goToTab={() => {}} />)
    await screen.findByTestId('media-bg-cell-hallway')

    const input = screen.getByLabelText(t('builder.media.bg.upload', { location: 'hallway' }))
    const user = userEvent.setup()
    await user.upload(input, makeFile('bg.png', 'image/png', 1024))

    const img = await screen.findByAltText(t('builder.media.bg.alt', { location: 'hallway' }))
    expect(img).toHaveAttribute('src', expect.stringContaining('/api/scenarios/school/media/backgrounds/hallway.png?t='))
  })

  it('a start with an accented location slugifies to ascii', async () => {
    const draft = baseDraft()
    draft.starts.a = startFixture('a', 'Start A', 'pátio da escola')

    const fetchMock = vi.fn(async () => jsonResponse(emptyIndex()))
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={draft} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    expect(await screen.findByTestId('media-bg-cell-patio-da-escola')).toBeInTheDocument()
  })

  it('two starts sharing the same location generate a single slot', async () => {
    const draft = baseDraft()
    draft.starts.a = startFixture('a', 'Start A', 'Hallway')
    draft.starts.b = startFixture('b', 'Start B', 'Hallway')

    const fetchMock = vi.fn(async () => jsonResponse(emptyIndex()))
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={draft} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    await screen.findByTestId('media-bg-cell-hallway')
    expect(await screen.findByText(t('builder.media.summary', { filled: 0, total: 3 }))).toBeInTheDocument()
    expect(screen.getAllByTestId('media-bg-cell-hallway')).toHaveLength(1)
  })

  it('adding a location already in the list shows slugTaken', async () => {
    const draft = baseDraft()
    draft.starts.a = startFixture('a', 'Start A', 'Hallway')

    const fetchMock = vi.fn(async () => jsonResponse(emptyIndex()))
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={draft} onChange={() => {}} errors={[]} goToTab={() => {}} />)
    await screen.findByTestId('media-bg-cell-hallway')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: t('builder.media.backgrounds.add') }))
    await user.type(screen.getByLabelText(t('builder.media.backgrounds.addLabel')), 'hallway')
    await user.click(screen.getByRole('button', { name: t('builder.media.backgrounds.add') }))

    expect(await screen.findByText(t('builder.field.slugTaken', { slug: 'hallway' }))).toBeInTheDocument()
    expect(screen.getAllByTestId('media-bg-cell-hallway')).toHaveLength(1)
  })

  it('a start-seeded empty slot has no remove-slot offer', async () => {
    const draft = baseDraft()
    draft.starts.a = startFixture('a', 'Start A', 'Hallway')

    const fetchMock = vi.fn(async () => jsonResponse(emptyIndex()))
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={draft} onChange={() => {}} errors={[]} goToTab={() => {}} />)
    await screen.findByTestId('media-bg-cell-hallway')

    expect(screen.queryByRole('button', { name: t('builder.media.backgrounds.removeSlot', { location: 'hallway' }) })).not.toBeInTheDocument()
  })

  it('an orphan sprite for a declared character shows in the orphans strip with declare and remove', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        cover: null,
        sprites: { luca: { default: '/api/scenarios/school/media/sprites/luca/default.png', mocking: '/api/scenarios/school/media/sprites/luca/mocking.png' } },
        backgrounds: {},
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const onChange = vi.fn()
    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={onChange} errors={[]} goToTab={() => {}} />)

    expect(await screen.findByText(t('builder.media.sprites.orphans.title'))).toBeInTheDocument()
    expect(screen.getByText('mocking.png')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: t('builder.media.sprites.orphans.declare', { emotion: 'mocking' }) }))

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        characters: expect.objectContaining({
          luca: expect.objectContaining({ emotions: ['default', 'happy', 'mocking'] }),
        }),
      }),
    )
  })

  it('an orphan sprite folder with no matching character shows with only remove', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        cover: null,
        sprites: {
          luca: { default: '/api/scenarios/school/media/sprites/luca/default.png' },
          ghost: { default: '/api/scenarios/school/media/sprites/ghost/default.png' },
        },
        backgrounds: {},
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    expect(await screen.findByText(t('builder.media.sprites.orphans.folderTitle'))).toBeInTheDocument()
    expect(screen.getByText('default.png')).toBeInTheDocument()
    expect(screen.queryByText(t('builder.media.sprites.orphans.declare', { emotion: 'default' }))).not.toBeInTheDocument()
  })

  it('a 500 background upload response shows the write error only for that cell', async () => {
    const draft = baseDraft()
    draft.starts.a = startFixture('a', 'Start A', 'Hallway')

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school/media' && (!init || init.method === undefined)) {
        return jsonResponse(emptyIndex())
      }
      if (url === '/api/builder/scenarios/school/media' && init?.method === 'POST') {
        return jsonResponse({ detail: 'disk write failed' }, 500)
      }
      throw new Error(`unexpected fetch ${url} ${init?.method}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<MediaTab scenarioId="school" draft={draft} onChange={() => {}} errors={[]} goToTab={() => {}} />)
    await screen.findByTestId('media-bg-cell-hallway')

    const input = screen.getByLabelText(t('builder.media.bg.upload', { location: 'hallway' }))
    const user = userEvent.setup()
    await user.upload(input, makeFile('bg.png', 'image/png', 1024))

    expect(await screen.findByText(t('builder.media.error.write'))).toBeInTheDocument()
  })
})
