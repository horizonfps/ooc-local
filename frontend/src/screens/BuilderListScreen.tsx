import { useEffect, useRef, useState } from 'react'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { Loading } from '../components/Loading'
import { describeError } from '../errors'
import { locale as appLocale, t, type Locale } from '../i18n'
import { navigate } from '../useHashRoute'
import {
  ApiError,
  createBuilderScenario,
  deleteBuilderScenario,
  duplicateBuilderScenario,
  fetchBuilderScenarios,
  type BuilderScenarioItem,
} from '../api'
import '../components/states.css'
import './builder.css'

const COVER_EXTENSIONS = ['png', 'jpg', 'webp'] as const
const FOLDER_RE = /^[a-z0-9-]+$/

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-{2,}/g, '-')
    .slice(0, 64)
    .replace(/^-+|-+$/g, '')
}

function dedupeFolder(base: string, existingIds: readonly string[]): string {
  const existing = new Set(existingIds)
  if (!existing.has(base)) return base
  let n = 2
  while (existing.has(`${base}-${n}`)) n += 1
  return `${base}-${n}`
}

type ListState =
  | { status: 'loading' }
  | { status: 'error'; error: unknown }
  | { status: 'loaded'; scenarios: BuilderScenarioItem[] }

function startsLabel(startCount: number): string {
  if (startCount === 1) return t('builder.list.item.startsOne')
  return t('builder.list.item.startsOther', { count: startCount })
}

function charactersLabel(characterCount: number): string {
  if (characterCount === 0) return t('builder.list.item.charactersZero')
  if (characterCount === 1) return t('builder.list.item.charactersOne')
  return t('builder.list.item.charactersOther', { count: characterCount })
}

function localeLabel(locale: string): string {
  return locale === 'pt-br' ? t('builder.create.locale.ptBr') : t('builder.create.locale.en')
}

function BuilderCover(props: { scenarioId: string; scenarioName: string }) {
  const [extIndex, setExtIndex] = useState(0)

  if (extIndex >= COVER_EXTENSIONS.length) {
    return (
      <div className="builder-card-cover builder-card-cover-placeholder" aria-hidden="true">
        {props.scenarioName.charAt(0).toUpperCase()}
      </div>
    )
  }

  const ext = COVER_EXTENSIONS[extIndex]
  return (
    <img
      className="builder-card-cover"
      src={`/api/scenarios/${props.scenarioId}/media/cover.${ext}`}
      alt={t('builder.list.item.coverAlt', { scenario: props.scenarioName })}
      onError={() => setExtIndex((i) => i + 1)}
    />
  )
}

type DialogKind = 'duplicate' | 'delete' | null

function BuilderCard(props: {
  scenario: BuilderScenarioItem
  existingIds: readonly string[]
  onDuplicated: (item: BuilderScenarioItem) => void
  onDeleted: (id: string) => void
  announce: (message: string) => void
  headingRef: React.RefObject<HTMLHeadingElement | null>
}) {
  const { scenario, existingIds, onDuplicated, onDeleted, announce, headingRef } = props
  const displayName = scenario.name || scenario.id

  const [dialogOpen, setDialogOpen] = useState<DialogKind>(null)
  const duplicateDialogRef = useRef<HTMLDialogElement>(null)
  const deleteDialogRef = useRef<HTMLDialogElement>(null)
  const duplicateTriggerRef = useRef<HTMLButtonElement>(null)
  const deleteTriggerRef = useRef<HTMLButtonElement>(null)
  const duplicateFolderRef = useRef<HTMLInputElement>(null)
  const deleteCancelRef = useRef<HTMLButtonElement>(null)

  const [newFolder, setNewFolder] = useState('')
  const [dupError, setDupError] = useState<string | null>(null)
  const [dupSubmitting, setDupSubmitting] = useState(false)

  const [confirmText, setConfirmText] = useState('')
  const [delError, setDelError] = useState<string | null>(null)
  const [delSubmitting, setDelSubmitting] = useState(false)
  const dupSubmittingRef = useRef(false)
  const delSubmittingRef = useRef(false)

  useEffect(() => {
    if (dialogOpen === 'duplicate') {
      duplicateDialogRef.current?.showModal()
      duplicateFolderRef.current?.focus()
      duplicateFolderRef.current?.select()
    } else if (dialogOpen === 'delete') {
      deleteDialogRef.current?.showModal()
      deleteCancelRef.current?.focus()
    }
  }, [dialogOpen])

  function closeDialog() {
    const trigger = dialogOpen === 'duplicate' ? duplicateTriggerRef.current : deleteTriggerRef.current
    duplicateDialogRef.current?.close()
    deleteDialogRef.current?.close()
    setDialogOpen(null)
    trigger?.focus()
  }

  function handleDialogClosed() {
    const trigger = dialogOpen === 'duplicate' ? duplicateTriggerRef.current : deleteTriggerRef.current
    setDialogOpen(null)
    trigger?.focus()
  }

  function handleDialogKeyDown(event: React.KeyboardEvent<HTMLDialogElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      closeDialog()
    }
  }

  function openDuplicate() {
    setNewFolder(dedupeFolder(`${scenario.id}-copy`, existingIds))
    setDupError(null)
    dupSubmittingRef.current = false
    setDupSubmitting(false)
    setDialogOpen('duplicate')
  }

  function openDelete() {
    setConfirmText('')
    setDelError(null)
    delSubmittingRef.current = false
    setDelSubmitting(false)
    setDialogOpen('delete')
  }

  async function handleDuplicateSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (dupSubmittingRef.current) return
    const folder = newFolder.trim()
    if (!folder || !FOLDER_RE.test(folder)) {
      setDupError(t('builder.create.error.invalidFolder'))
      return
    }
    dupSubmittingRef.current = true
    setDupSubmitting(true)
    setDupError(null)
    try {
      const created = await duplicateBuilderScenario(scenario.id, folder)
      setDialogOpen(null)
      duplicateDialogRef.current?.close()
      onDuplicated(created)
      announce(t('builder.duplicate.success', { scenario: displayName, folder }))
      duplicateTriggerRef.current?.focus()
    } catch (err) {
      dupSubmittingRef.current = false
      setDupSubmitting(false)
      if (err instanceof ApiError && (err.status === 409 || err.status === 422)) {
        setDupError(
          err.status === 409 ? t('builder.create.error.duplicate', { folder }) : t('builder.create.error.invalidFolder'),
        )
        return
      }
      setDupError(t('builder.duplicate.error'))
      return
    }
    dupSubmittingRef.current = false
    setDupSubmitting(false)
  }

  async function handleDeleteSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (delSubmittingRef.current || confirmText !== scenario.id) return
    delSubmittingRef.current = true
    setDelSubmitting(true)
    setDelError(null)
    try {
      await deleteBuilderScenario(scenario.id)
      setDialogOpen(null)
      deleteDialogRef.current?.close()
      onDeleted(scenario.id)
      announce(t('builder.delete.success', { scenario: displayName }))
      headingRef.current?.focus()
    } catch {
      delSubmittingRef.current = false
      setDelSubmitting(false)
      setDelError(t('builder.delete.error'))
      return
    }
    delSubmittingRef.current = false
    setDelSubmitting(false)
  }

  const actions = (
    <div className="builder-card-actions">
      <button
        type="button"
        ref={duplicateTriggerRef}
        aria-label={t('builder.duplicate.title', { scenario: displayName })}
        onClick={openDuplicate}
      >
        {t('builder.duplicate.action')}
      </button>
      <button
        type="button"
        ref={deleteTriggerRef}
        aria-label={t('builder.delete.title', { scenario: displayName })}
        onClick={openDelete}
      >
        {t('builder.delete.action')}
      </button>

      <dialog
        ref={duplicateDialogRef}
        className="builder-dialog"
        aria-labelledby={`builder-duplicate-title-${scenario.id}`}
        onKeyDown={handleDialogKeyDown}
        onClose={handleDialogClosed}
      >
        <h2 id={`builder-duplicate-title-${scenario.id}`}>{t('builder.duplicate.title', { scenario: displayName })}</h2>
        <p>{t('builder.duplicate.body')}</p>
        <form onSubmit={handleDuplicateSubmit}>
          <label htmlFor={`builder-duplicate-folder-${scenario.id}`}>{t('builder.duplicate.folderLabel')}</label>
          <input
            id={`builder-duplicate-folder-${scenario.id}`}
            ref={duplicateFolderRef}
            value={newFolder}
            onChange={(e) => setNewFolder(e.target.value)}
            aria-invalid={dupError ? 'true' : undefined}
          />
          {dupError ? (
            <p role="alert" className="builder-dialog-error">
              {dupError}
            </p>
          ) : null}
          <div className="builder-dialog-actions">
            <button type="button" onClick={closeDialog}>
              {t('common.cancel')}
            </button>
            <button type="submit" disabled={dupSubmitting} aria-busy={dupSubmitting || undefined}>
              {dupSubmitting ? t('builder.duplicate.submitting') : t('builder.duplicate.submit')}
            </button>
          </div>
        </form>
      </dialog>

      <dialog
        ref={deleteDialogRef}
        className="builder-dialog"
        aria-labelledby={`builder-delete-title-${scenario.id}`}
        onKeyDown={handleDialogKeyDown}
        onClose={handleDialogClosed}
      >
        <h2 id={`builder-delete-title-${scenario.id}`}>{t('builder.delete.title', { scenario: displayName })}</h2>
        <p>{t('builder.delete.body', { folder: scenario.id })}</p>
        <form onSubmit={handleDeleteSubmit}>
          <label htmlFor={`builder-delete-confirm-${scenario.id}`}>
            {t('builder.delete.confirmLabel', { folder: scenario.id })}
          </label>
          <input
            id={`builder-delete-confirm-${scenario.id}`}
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
          />
          {delError ? (
            <p role="alert" className="builder-dialog-error">
              {delError}
            </p>
          ) : null}
          <div className="builder-dialog-actions">
            <button type="button" ref={deleteCancelRef} onClick={closeDialog}>
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              className="builder-dialog-delete-submit"
              disabled={confirmText !== scenario.id || delSubmitting}
              aria-busy={delSubmitting || undefined}
            >
              {delSubmitting ? t('builder.delete.submitting') : t('builder.delete.submit')}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  )

  if (scenario.status === 'invalid') {
    return (
      <li className="builder-card builder-card-invalid">
        <span className="builder-card-name">{displayName}</span>
        <ErrorState
          title={t('builder.list.item.broken')}
          body={t('builder.list.item.brokenBody', {
            reason: scenario.reason ?? t('builder.list.item.reasonUnknown'),
          })}
        />
        {actions}
      </li>
    )
  }

  return (
    <li className="builder-card">
      <a className="builder-card-link" href={`#/builder/${scenario.id}/identity`} aria-label={t('builder.list.item.edit', { scenario: scenario.name })}>
        {scenario.hasCover ? (
          <BuilderCover scenarioId={scenario.id} scenarioName={scenario.name} />
        ) : (
          <div className="builder-card-cover builder-card-cover-placeholder" aria-hidden="true">
            {scenario.name.charAt(0).toUpperCase()}
          </div>
        )}
        <strong className="builder-card-name">{scenario.name}</strong>
        {scenario.tagline !== null ? <p className="builder-card-tagline">{scenario.tagline}</p> : null}
        <p className="builder-card-meta">
          {t('builder.list.item.meta', {
            starts: startsLabel(scenario.startCount),
            characters: charactersLabel(scenario.characterCount),
          })}
        </p>
        <span className="builder-card-locale">{localeLabel(scenario.locale)}</span>
      </a>
      {actions}
    </li>
  )
}

type CreateFieldError = { field: 'name' | 'folder'; message: string }

function CreateScenarioForm(props: { existingIds: readonly string[]; announce: (message: string) => void }) {
  const { existingIds, announce } = props
  const nameInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState('')
  const [folder, setFolder] = useState('')
  const [folderTouched, setFolderTouched] = useState(false)
  const [createLocale, setCreateLocale] = useState(appLocale)
  const [fieldError, setFieldError] = useState<CreateFieldError | null>(null)
  const [generalError, setGeneralError] = useState<unknown>(null)
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

  function handleNameChange(value: string) {
    setName(value)
    if (!folderTouched) setFolder(slugify(value))
  }

  function handleFolderChange(value: string) {
    setFolder(value)
    setFolderTouched(true)
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (submittingRef.current) return

    setGeneralError(null)
    const trimmedName = name.trim()
    if (!trimmedName) {
      setFieldError({ field: 'name', message: t('builder.create.error.nameRequired') })
      nameInputRef.current?.focus()
      return
    }
    if (!folder || !FOLDER_RE.test(folder)) {
      setFieldError({ field: 'folder', message: t('builder.create.error.invalidFolder') })
      folderInputRef.current?.focus()
      return
    }
    if (existingIds.includes(folder)) {
      setFieldError({ field: 'folder', message: t('builder.create.error.duplicate', { folder }) })
      folderInputRef.current?.focus()
      return
    }

    setFieldError(null)
    submittingRef.current = true
    setSubmitting(true)
    try {
      const created = await createBuilderScenario({ folder, name: trimmedName, locale: createLocale })
      announce(t('builder.create.success', { name: created.name }))
      navigate(`#/builder/${created.id}/identity`)
    } catch (err) {
      submittingRef.current = false
      setSubmitting(false)
      if (err instanceof ApiError && err.status === 409) {
        setFieldError({ field: 'folder', message: t('builder.create.error.duplicate', { folder }) })
        folderInputRef.current?.focus()
        return
      }
      setGeneralError(err)
      return
    }
  }

  const errorId = fieldError ? 'builder-create-error' : undefined

  return (
    <section className="builder-create" aria-labelledby="builder-create-heading">
      <h2 id="builder-create-heading">{t('builder.create.heading')}</h2>
      <form onSubmit={handleSubmit}>
        <div className="builder-create-field">
          <label htmlFor="builder-create-name">{t('builder.create.nameLabel')}</label>
          <input
            id="builder-create-name"
            ref={nameInputRef}
            value={name}
            maxLength={80}
            placeholder={t('builder.create.namePlaceholder')}
            onChange={(e) => handleNameChange(e.target.value)}
            aria-invalid={fieldError?.field === 'name' ? 'true' : undefined}
            aria-describedby={fieldError?.field === 'name' ? errorId : undefined}
          />
        </div>
        <div className="builder-create-field">
          <label htmlFor="builder-create-folder">{t('builder.create.folderLabel')}</label>
          <input
            id="builder-create-folder"
            ref={folderInputRef}
            value={folder}
            onChange={(e) => handleFolderChange(e.target.value)}
            aria-invalid={fieldError?.field === 'folder' ? 'true' : undefined}
            aria-describedby={fieldError?.field === 'folder' ? errorId : undefined}
          />
          <p className="builder-create-hint">{t('builder.create.folderHint')}</p>
        </div>
        <div className="builder-create-field">
          <label htmlFor="builder-create-locale">{t('builder.create.localeLabel')}</label>
          <select
            id="builder-create-locale"
            value={createLocale}
            onChange={(e) => setCreateLocale(e.target.value as Locale)}
          >
            <option value="en">{t('builder.create.locale.en')}</option>
            <option value="pt-br">{t('builder.create.locale.ptBr')}</option>
          </select>
        </div>
        {fieldError ? (
          <p role="alert" id={errorId} className="builder-create-error">
            {fieldError.message}
          </p>
        ) : null}
        <button type="submit" disabled={submitting} aria-busy={submitting || undefined}>
          {submitting ? t('builder.create.submitting') : t('builder.create.submit')}
        </button>
      </form>
      {generalError ? (
        <ErrorState title={t('error.unexpected.title')} body={t('builder.create.error.failed')} cause={describeError(generalError).cause} />
      ) : null}
    </section>
  )
}

export function BuilderListScreen() {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [state, setState] = useState<ListState>({ status: 'loading' })
  const [announcement, setAnnouncement] = useState('')
  const [loadCount, setLoadCount] = useState(0)

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  useEffect(() => {
    const previousTitle = document.title
    document.title = t('builder.documentTitle')
    return () => {
      document.title = previousTitle
    }
  }, [])

  const load = () => {
    setState({ status: 'loading' })
    fetchBuilderScenarios()
      .then((scenarios) => setState({ status: 'loaded', scenarios }))
      .catch((error) => setState({ status: 'error', error }))
  }

  useEffect(() => {
    load()
  }, [])

  const handleReload = () => {
    setAnnouncement('')
    fetchBuilderScenarios()
      .then((scenarios) => {
        setState({ status: 'loaded', scenarios })
        setLoadCount((n) => n + 1)
        setAnnouncement(t('builder.list.reloaded'))
      })
      .catch((error) => setState({ status: 'error', error }))
  }

  function handleDuplicated(item: BuilderScenarioItem) {
    setState((prev) => (prev.status === 'loaded' ? { status: 'loaded', scenarios: [...prev.scenarios, item] } : prev))
  }

  function handleDeleted(id: string) {
    setState((prev) =>
      prev.status === 'loaded' ? { status: 'loaded', scenarios: prev.scenarios.filter((s) => s.id !== id) } : prev,
    )
  }

  const errorCause = state.status === 'error' ? describeError(state.error).cause : null
  const existingIds = state.status === 'loaded' ? state.scenarios.map((s) => s.id) : []

  return (
    <main className="builder-list">
      <div className="builder-list-topbar">
        <button type="button" className="builder-list-back" onClick={() => navigate('#/')}>
          {t('builder.list.back')}
        </button>
        <h1 ref={headingRef} tabIndex={-1}>
          {t('builder.list.heading')}
        </h1>
        <button type="button" className="builder-list-reload" onClick={handleReload}>
          {t('builder.list.reload')}
        </button>
      </div>

      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>

      <CreateScenarioForm existingIds={existingIds} announce={setAnnouncement} />

      {state.status === 'loading' ? (
        <>
          <ul className="builder-list-skeleton" aria-hidden="true">
            <li />
            <li />
            <li />
          </ul>
          <Loading label={t('builder.list.loading')} visuallyHidden />
        </>
      ) : null}

      {state.status === 'error' ? (
        <ErrorState
          title={t('builder.list.error.title')}
          body={t('builder.list.error.body')}
          cause={errorCause ?? undefined}
          onRetry={load}
        />
      ) : null}

      {state.status === 'loaded' && state.scenarios.length === 0 ? (
        <EmptyState
          title={t('builder.list.empty.title')}
          body={t('builder.list.empty.body')}
          action={
            <button type="button" onClick={() => document.getElementById('builder-create-name')?.focus()}>
              {t('builder.list.empty.action')}
            </button>
          }
        />
      ) : null}

      {state.status === 'loaded' && state.scenarios.length > 0 ? (
        <ul className="builder-card-grid">
          {state.scenarios.map((scenario) => (
            <BuilderCard
              key={`${scenario.id}:${loadCount}`}
              scenario={scenario}
              existingIds={existingIds}
              onDuplicated={handleDuplicated}
              onDeleted={handleDeleted}
              announce={setAnnouncement}
              headingRef={headingRef}
            />
          ))}
        </ul>
      ) : null}
    </main>
  )
}
