import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { LorebookTab } from './LorebookTab'
import { validateDraft } from '../../builder/validate'
import type { BuilderDraft } from '../../screens/BuilderEditorScreen'
import type { LoreEntryDoc } from '../../api'
import { t } from '../../i18n'

function loreEntry(overrides: Partial<LoreEntryDoc> = {}): LoreEntryDoc {
  return {
    title: 'O caderno',
    keywords: ['caderno'],
    body: 'Um caderno preto.',
    scope: 'keyword',
    priority: 0,
    enabled: true,
    ...overrides,
  }
}

function baseDraft(overrides: Partial<BuilderDraft> = {}): BuilderDraft {
  return {
    meta: {
      name: 'The School',
      tagline: null,
      description: null,
      locale: 'en',
      tags: [],
      default_start: 'default',
      world_mode: 'guided',
      allow_dynamic_stats: false,
    },
    world: '## Universe\n\nA dusty old school.',
    starts: {
      default: {
        id: 'default',
        name: 'Default start',
        prologue: 'It begins.',
        opening_scene: 'A hallway.',
        conflict: null,
        mission: null,
        play_guide: null,
        suggestions: [],
        hud: { location: 'Hallway', time: '08:00', weather: 'clear' },
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

function Harness(props: { initial: BuilderDraft; goToTab?: (tab: string) => void; onChangeSpy?: (next: BuilderDraft) => void }) {
  const [draft, setDraft] = useState(props.initial)
  const errors = validateDraft(draft)
  return (
    <>
      <LorebookTab
        scenarioId="school"
        draft={draft}
        onChange={(next) => {
          props.onChangeSpy?.(next)
          setDraft(next)
        }}
        errors={errors}
        goToTab={(props.goToTab as never) ?? (() => {})}
      />
      <pre data-testid="lorebook-debug">{JSON.stringify(draft.lorebook)}</pre>
      <pre data-testid="world-debug">{draft.world}</pre>
    </>
  )
}

describe('LorebookTab', () => {
  it('writes title, body, scope and enabled', () => {
    render(<Harness initial={baseDraft({ lorebook: { caderno: loreEntry() } })} />)

    fireEvent.change(document.getElementById('builder-field-lorebook.caderno.title') as HTMLInputElement, {
      target: { value: 'O caderno secreto' },
    })
    fireEvent.change(screen.getByLabelText(t('builder.lorebook.body')), { target: { value: 'Novo corpo.' } })
    fireEvent.click(screen.getByRole('radio', { name: t('builder.lorebook.scope.always') }))
    fireEvent.click(screen.getByRole('checkbox', { name: t('builder.lorebook.enabled') }))

    const debug = JSON.parse(screen.getByTestId('lorebook-debug').textContent ?? '{}')
    expect(debug.caderno.title).toBe('O caderno secreto')
    expect(debug.caderno.body).toBe('Novo corpo.')
    expect(debug.caderno.scope).toBe('always')
    expect(debug.caderno.enabled).toBe(false)
  })

  it('adds a keyword on Enter and on comma', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft({ lorebook: { caderno: loreEntry({ keywords: [] }) } })} />)

    const input = screen.getByLabelText(t('builder.lorebook.keywords.add'))
    await user.type(input, 'caderno{Enter}')
    await user.type(input, 'diário,')

    const debug = JSON.parse(screen.getByTestId('lorebook-debug').textContent ?? '{}')
    expect(debug.caderno.keywords).toEqual(['caderno', 'diário'])
    expect(screen.getByText('caderno')).toBeInTheDocument()
    expect(screen.getByText('diário')).toBeInTheDocument()
  })

  it('removes a keyword through the chip button', () => {
    render(<Harness initial={baseDraft({ lorebook: { caderno: loreEntry({ keywords: ['caderno', 'diário'] }) } })} />)

    fireEvent.click(screen.getByRole('button', { name: t('builder.lorebook.keywords.remove', { keyword: 'caderno' }) }))

    const debug = JSON.parse(screen.getByTestId('lorebook-debug').textContent ?? '{}')
    expect(debug.caderno.keywords).toEqual(['diário'])
  })

  it('creates an entry through the dialog and selects it', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft({ lorebook: {} })} />)

    await user.click(screen.getByRole('button', { name: t('builder.lorebook.create') }))
    fireEvent.change(screen.getByLabelText(t('builder.lorebook.create.idLabel')), { target: { value: 'sala-do-gremio' } })
    fireEvent.change(screen.getByLabelText(t('builder.lorebook.title')), { target: { value: 'Sala do grêmio' } })
    await user.click(screen.getByRole('button', { name: t('builder.lorebook.create.submit') }))

    const debug = JSON.parse(screen.getByTestId('lorebook-debug').textContent ?? '{}')
    expect(debug['sala-do-gremio']).toEqual({
      title: 'Sala do grêmio',
      keywords: [],
      body: '',
      scope: 'keyword',
      priority: 0,
      enabled: true,
    })
    await waitFor(() => {
      expect(document.getElementById('builder-field-lorebook.sala-do-gremio.title')).toBe(document.activeElement)
    })
  })

  it('deletes an entry through the dialog', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft({ lorebook: { caderno: loreEntry() } })} />)

    await user.click(screen.getByRole('button', { name: t('builder.lorebook.delete.title', { title: 'O caderno' }) }))
    const dialog = screen.getByRole('heading', { name: t('builder.lorebook.delete.title', { title: 'O caderno' }) }).closest('dialog')
    expect(dialog).not.toBeNull()
    await user.click(within(dialog as HTMLElement).getByRole('button', { name: t('builder.lorebook.delete') }))

    const debug = JSON.parse(screen.getByTestId('lorebook-debug').textContent ?? '{}')
    expect(debug.caderno).toBeUndefined()
    expect(screen.getByText(t('builder.lorebook.empty.title'))).toBeInTheDocument()
  })

  it('breaks the free world blocks into entries', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={baseDraft({
          world: '## Universe\n\nU\n\n## O caderno\n\nUm caderno preto.\n\n## Sala do grêmio\n\nCheira a café.',
          lorebook: {},
        })}
      />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split') }))
    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split.submit') }))

    const debug = JSON.parse(screen.getByTestId('lorebook-debug').textContent ?? '{}')
    expect(debug['o-caderno']).toEqual({
      title: 'O caderno',
      keywords: ['O caderno'],
      body: 'Um caderno preto.',
      scope: 'keyword',
      priority: 0,
      enabled: true,
    })
    expect(debug['sala-do-gremio']).toEqual({
      title: 'Sala do grêmio',
      keywords: ['Sala do grêmio'],
      body: 'Cheira a café.',
      scope: 'keyword',
      priority: 0,
      enabled: true,
    })
    expect(screen.getByTestId('world-debug').textContent).toBe('## Universe\n\nU')
  })

  it('announces the split and selects the first created entry', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={baseDraft({
          world: '## Universe\n\nU\n\n## O caderno\n\nUm caderno preto.\n\n## Sala do grêmio\n\nCheira a café.',
          lorebook: {},
        })}
      />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split') }))
    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split.submit') }))

    expect(screen.getByText(t('builder.lorebook.split.done', { count: 2 }))).toBeInTheDocument()
    await waitFor(() => {
      expect(document.getElementById('builder-field-lorebook.o-caderno.title')).toBe(document.activeElement)
    })
  })

  it('disambiguates an id that already exists', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={baseDraft({
          world: '## Universe\n\nU\n\n## O caderno\n\nUm caderno novo.',
          lorebook: { 'o-caderno': loreEntry() },
        })}
      />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split') }))
    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split.submit') }))

    const debug = JSON.parse(screen.getByTestId('lorebook-debug').textContent ?? '{}')
    expect(debug['o-caderno-2']).toBeDefined()
    expect(debug['o-caderno']).toEqual(loreEntry())
  })

  it('leaves an untitled block in the world', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={baseDraft({
          world: '## Universe\n\nU\n\n## O caderno\n\nUm caderno preto.\n\n##\n\nSem título.',
          lorebook: {},
        })}
      />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split') }))
    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split.submit') }))

    expect(screen.getByTestId('world-debug').textContent).toContain('Sem título.')
    expect(screen.getByText(t('builder.lorebook.split.skipped', { count: 1 }), { exact: false })).toBeInTheDocument()
  })

  it('does not break without confirmation', async () => {
    const user = userEvent.setup()
    const world = '## Universe\n\nU\n\n## O caderno\n\nUm caderno preto.'
    render(<Harness initial={baseDraft({ world, lorebook: {} })} />)

    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split') }))
    const dialog = screen.getByRole('heading', { name: t('builder.lorebook.split.title') }).closest('dialog')
    expect(dialog).not.toBeNull()
    await user.click(within(dialog as HTMLElement).getByRole('button', { name: t('common.cancel') }))

    expect(screen.getByTestId('lorebook-debug').textContent).toBe('{}')
    expect(screen.getByTestId('world-debug').textContent).toBe(world)
  })

  it('hides the split button when the world is custom', async () => {
    const user = userEvent.setup()
    const goToTab = vi.fn()
    render(
      <Harness
        initial={baseDraft({ meta: { ...baseDraft().meta, world_mode: 'custom' }, world: 'Freeform text.', lorebook: {} })}
        goToTab={goToTab}
      />,
    )

    expect(screen.queryByRole('button', { name: t('builder.lorebook.split') })).toBeNull()
    expect(screen.getByText(t('builder.lorebook.split.unavailable'))).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split.goToWorld') }))
    expect(goToTab).toHaveBeenCalledWith('world')
  })

  it('hides the split button when there is no free block', () => {
    render(<Harness initial={baseDraft({ world: '## Universe\n\nU', lorebook: {} })} />)

    expect(screen.getByText(t('builder.lorebook.split.empty'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t('builder.lorebook.split') })).toBeNull()
  })

  it('breaks the world in a single onChange', async () => {
    const user = userEvent.setup()
    const onChangeSpy = vi.fn()
    render(
      <Harness
        initial={baseDraft({
          world: '## Universe\n\nU\n\n## O caderno\n\nUm caderno preto.',
          lorebook: {},
        })}
        onChangeSpy={onChangeSpy}
      />,
    )

    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split') }))
    onChangeSpy.mockClear()
    await user.click(screen.getByRole('button', { name: t('builder.lorebook.split.submit') }))

    expect(onChangeSpy).toHaveBeenCalledTimes(1)
    const next = onChangeSpy.mock.calls[0][0] as BuilderDraft
    expect(next.lorebook['o-caderno']).toBeDefined()
    expect(next.world).toBe('## Universe\n\nU')
  })

  it('refuses a repeated keyword regardless of accent or case', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft({ lorebook: { caderno: loreEntry({ keywords: ['Diário'] }) } })} />)

    const input = screen.getByLabelText(t('builder.lorebook.keywords.add'))
    await user.type(input, 'diario{Enter}')

    const debug = JSON.parse(screen.getByTestId('lorebook-debug').textContent ?? '{}')
    expect(debug.caderno.keywords).toEqual(['Diário'])
    expect(screen.getByText(t('builder.identity.tags.duplicate', { tag: 'diario' }))).toBeInTheDocument()
  })

  it('shows the disabled badge and the every-turn badge', () => {
    render(
      <Harness
        initial={baseDraft({
          lorebook: { caderno: loreEntry({ enabled: false, scope: 'always' }) },
        })}
      />,
    )

    expect(screen.getByText(t('builder.lorebook.disabledBadge'))).toBeInTheDocument()
    expect(screen.getByText(t('builder.lorebook.alwaysBadge'))).toBeInTheDocument()
  })

  it('refuses a duplicate id in the create dialog', async () => {
    const user = userEvent.setup()
    render(<Harness initial={baseDraft({ lorebook: { caderno: loreEntry() } })} />)

    await user.click(screen.getByRole('button', { name: t('builder.lorebook.create') }))
    fireEvent.change(screen.getByLabelText(t('builder.lorebook.create.idLabel')), { target: { value: 'caderno' } })
    await user.click(screen.getByRole('button', { name: t('builder.lorebook.create.submit') }))

    expect(screen.getByText(t('builder.field.slugTaken', { slug: 'caderno' }))).toBeInTheDocument()
    const debug = JSON.parse(screen.getByTestId('lorebook-debug').textContent ?? '{}')
    expect(debug.caderno).toEqual(loreEntry())
  })

  it('shows an error for a keyword-scoped entry with no keyword', () => {
    render(<Harness initial={baseDraft({ lorebook: { caderno: loreEntry({ keywords: [] }) } })} />)

    const alert = screen.getByText(t('builder.validate.loreKeywordRequired'))
    expect(alert).toHaveAttribute('role', 'alert')
    const list = document.querySelector('.builder-tags-list') as HTMLElement
    expect(list.getAttribute('aria-describedby')).toContain(alert.id)
  })

  it('marks an unselected entry with an error in the list', async () => {
    const user = userEvent.setup()
    render(
      <Harness
        initial={baseDraft({
          lorebook: {
            caderno: loreEntry({ keywords: [] }),
            gremio: loreEntry({ title: 'Sala do grêmio', keywords: ['grêmio'] }),
          },
        })}
      />,
    )

    await user.click(screen.getByText('Sala do grêmio'))

    const cadernoItem = screen.getByText('O caderno').closest('li')
    expect(cadernoItem).toHaveClass('is-invalid')
    expect(within(cadernoItem as HTMLElement).getByText(t('builder.starts.itemInvalid'))).toBeInTheDocument()
  })
})
