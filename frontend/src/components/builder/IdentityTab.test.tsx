import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { IdentityTab } from './IdentityTab'
import { validateDraft } from '../../builder/validate'
import type { BuilderDraft } from '../../screens/BuilderEditorScreen'
import { t } from '../../i18n'

function baseDraft(): BuilderDraft {
  return {
    meta: {
      name: 'The School',
      tagline: 'A haunted hallway',
      description: null,
      locale: 'en',
      tags: ['horror'],
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
        characters: [],
      },
    },
    characters: {},
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

function Harness(props: { initial: BuilderDraft }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return (
    <IdentityTab
      scenarioId="school"
      draft={draft}
      onChange={setDraft}
      errors={errors}
      goToTab={() => {}}
    />
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('IdentityTab', () => {
  it('typing the name calls onChange with the updated draft', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const draft = baseDraft()
    render(<IdentityTab scenarioId="school" draft={draft} onChange={onChange} errors={[]} goToTab={() => {}} />)

    const input = screen.getByLabelText(t('builder.identity.name'))
    await user.type(input, '!')

    expect(onChange).toHaveBeenCalled()
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0] as BuilderDraft
    expect(lastCall.meta.name).toBe('The School!')
  })

  it('Enter and comma create a chip, and the remove button deletes it', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    const tagsInput = screen.getByLabelText(t('builder.identity.tags'))
    await user.type(tagsInput, 'fantasy{Enter}')
    expect(screen.getByText('fantasy')).toBeInTheDocument()

    await user.type(tagsInput, 'noir,')
    expect(screen.getByText('noir')).toBeInTheDocument()

    const removeButton = screen.getByRole('button', { name: t('builder.identity.tags.remove', { tag: 'fantasy' }) })
    await user.click(removeButton)
    expect(screen.queryByText('fantasy')).not.toBeInTheDocument()
  })

  it('uploading a cover sends FormData with kind=cover and swaps the thumbnail', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/builder/scenarios/school/media' && init?.method === 'POST') {
        expect(init.body).toBeInstanceOf(FormData)
        const body = init.body as FormData
        expect(body.get('kind')).toBe('cover')
        return jsonResponse({ path: 'cover.png', url: '/api/scenarios/school/media/cover.png' }, 201)
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<IdentityTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    const file = makeFile('capa.png', 'image/png', 1024)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const user = userEvent.setup()
    await user.upload(fileInput, file)

    const img = await screen.findByAltText(t('builder.identity.cover.alt', { scenario: 'The School' }))
    expect(img).toHaveAttribute('src', expect.stringContaining('/api/scenarios/school/media/cover.png?t='))
  })

  it('a duplicate tag is announced and not inserted', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    const tagsInput = screen.getByLabelText(t('builder.identity.tags'))
    await user.type(tagsInput, 'horror{Enter}')

    expect(screen.getByText(t('builder.identity.tags.duplicate', { tag: 'horror' }))).toBeInTheDocument()
    expect(screen.getAllByText('horror')).toHaveLength(1)
  })

  it('the tagline counter appears at 100 chars and validation blocks at 121', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft()} />)

    const taglineInput = screen.getByLabelText(t('builder.identity.tagline'))
    await user.clear(taglineInput)
    await user.type(taglineInput, 'a'.repeat(100))
    expect(screen.getByText(t('builder.field.counter', { count: 100, max: 120 }))).toBeInTheDocument()

    await user.type(taglineInput, 'a'.repeat(21))
    await user.tab()

    expect(taglineInput).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText(t('builder.field.tooLong', { max: 120 }))).toBeInTheDocument()
  })

  it('a 9 MB file is rejected without a fetch call', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<IdentityTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    const file = makeFile('capa.png', 'image/png', 9 * 1024 * 1024)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const user = userEvent.setup()
    await user.upload(fileInput, file)

    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByText(t('builder.media.error.size', { max: 8 }))).toBeInTheDocument()
  })

  it('a 413 upload response shows the size error with retry', async () => {
    let calls = 0
    const fetchMock = vi.fn(async () => {
      calls += 1
      return jsonResponse({ detail: 'file too large' }, 413)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<IdentityTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    const file = makeFile('capa.png', 'image/png', 1024)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const user = userEvent.setup()
    await user.upload(fileInput, file)

    expect(await screen.findByText(t('builder.media.error.size', { max: 8 }))).toBeInTheDocument()
    expect(calls).toBe(1)

    await user.click(screen.getByRole('button', { name: t('common.retry') }))
    expect(calls).toBe(2)
  })

  it('a 503 upload response shows the disabled error', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ detail: 'builder disabled by flag' }, 503))
    vi.stubGlobal('fetch', fetchMock)

    render(<IdentityTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    const file = makeFile('capa.png', 'image/png', 1024)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const user = userEvent.setup()
    await user.upload(fileInput, file)

    expect(await screen.findByText(t('builder.media.error.disabled'))).toBeInTheDocument()
  })

  it('a failed deleteMedia (500) shows removeFailed and keeps the thumbnail', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.startsWith('/api/builder/scenarios/school/media') && init?.method === 'DELETE') {
        return jsonResponse({ detail: 'delete failed' }, 500)
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<IdentityTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    const img = await screen.findByAltText(t('builder.identity.cover.alt', { scenario: 'The School' }))
    expect(img).toHaveAttribute('src', '/api/scenarios/school/media/cover.png')
    fireEvent.load(img)

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: t('builder.identity.cover.remove') }))

    expect(await screen.findByText(t('builder.media.error.removeFailed'))).toBeInTheDocument()
    expect(screen.getByAltText(t('builder.identity.cover.alt', { scenario: 'The School' }))).toHaveAttribute(
      'src',
      '/api/scenarios/school/media/cover.png',
    )
  })

  it('shows the placeholder and hides remove once every cover extension fails to load', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<IdentityTab scenarioId="school" draft={baseDraft()} onChange={() => {}} errors={[]} goToTab={() => {}} />)

    let img = await screen.findByAltText(t('builder.identity.cover.alt', { scenario: 'The School' }))
    fireEvent.error(img)
    img = await screen.findByAltText(t('builder.identity.cover.alt', { scenario: 'The School' }))
    fireEvent.error(img)
    img = await screen.findByAltText(t('builder.identity.cover.alt', { scenario: 'The School' }))
    fireEvent.error(img)

    expect(screen.queryByAltText(t('builder.identity.cover.alt', { scenario: 'The School' }))).not.toBeInTheDocument()
    expect(screen.getByText(t('builder.identity.cover.empty'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t('builder.identity.cover.remove') })).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
