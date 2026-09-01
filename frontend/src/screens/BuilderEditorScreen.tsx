import { useEffect, useRef, useState } from 'react'
import { ApiError, fetchScenarioDocument, saveScenarioDocument, type ScenarioDocument } from '../api'
import { deepEqual, validateDraft } from '../builder/validate'
import { BuilderPreview } from '../components/builder/BuilderPreview'
import { CharactersTab } from '../components/builder/CharactersTab'
import { IdentityTab } from '../components/builder/IdentityTab'
import { MediaTab } from '../components/builder/MediaTab'
import { StartsTab } from '../components/builder/StartsTab'
import { WorldTab } from '../components/builder/WorldTab'
import { ErrorState } from '../components/ErrorState'
import { Loading } from '../components/Loading'
import { describeError } from '../errors'
import { t, type StringKey } from '../i18n'
import { navigate, type BuilderTab } from '../useHashRoute'
import { useUnsavedGuard } from '../useUnsavedGuard'
import './builderEditor.css'

export type { BuilderTab } from '../useHashRoute'

export type BuilderDraft = Omit<ScenarioDocument, 'revision'>

export type ValidationError = { tab: BuilderTab; field: string; label: string; message: string }

export type TabProps = {
  scenarioId: string
  draft: BuilderDraft
  onChange: (next: BuilderDraft) => void
  errors: ValidationError[]
  goToTab: (tab: BuilderTab) => void
}

const TAB_ORDER: readonly BuilderTab[] = ['identity', 'world', 'starts', 'characters', 'media']

const TAB_LABEL_KEY: Record<BuilderTab, StringKey> = {
  identity: 'builder.editor.tab.identity',
  world: 'builder.editor.tab.world',
  starts: 'builder.editor.tab.starts',
  characters: 'builder.editor.tab.characters',
  media: 'builder.editor.tab.media',
}

function draftOf(doc: ScenarioDocument): BuilderDraft {
  return { meta: doc.meta, world: doc.world, starts: doc.starts, characters: doc.characters }
}

function slice(tab: BuilderTab, draft: BuilderDraft): unknown {
  switch (tab) {
    case 'identity': {
      const { world_mode: _worldMode, default_start: _defaultStart, ...identityMeta } = draft.meta
      return identityMeta
    }
    case 'world':
      return { world: draft.world, world_mode: draft.meta.world_mode }
    case 'starts':
      return { starts: draft.starts, default_start: draft.meta.default_start }
    case 'characters':
      return draft.characters
    case 'media':
      return null
  }
}

const DEMO_MARK = ' •'

function demoEdit(tab: BuilderTab, draft: BuilderDraft): BuilderDraft {
  switch (tab) {
    case 'identity': {
      const tagline = draft.meta.tagline ?? ''
      const nextTagline = tagline.endsWith(DEMO_MARK) ? tagline.slice(0, -DEMO_MARK.length) : tagline + DEMO_MARK
      return { ...draft, meta: { ...draft.meta, tagline: nextTagline === '' ? null : nextTagline } }
    }
    case 'world':
      return { ...draft, world: draft.world.endsWith(DEMO_MARK) ? draft.world.slice(0, -DEMO_MARK.length) : draft.world + DEMO_MARK }
    case 'starts': {
      const ids = Object.keys(draft.starts)
      if (ids.length === 0) return draft
      const id = ids[0]
      const start = draft.starts[id]
      const nextName = start.name.endsWith(DEMO_MARK) ? start.name.slice(0, -DEMO_MARK.length) : start.name + DEMO_MARK
      return { ...draft, starts: { ...draft.starts, [id]: { ...start, name: nextName } } }
    }
    case 'characters': {
      const ids = Object.keys(draft.characters)
      if (ids.length === 0) return draft
      const id = ids[0]
      const character = draft.characters[id]
      const nextName = character.name.endsWith(DEMO_MARK) ? character.name.slice(0, -DEMO_MARK.length) : character.name + DEMO_MARK
      return { ...draft, characters: { ...draft.characters, [id]: { ...character, name: nextName } } }
    }
    case 'media':
      return draft
  }
}

function TabPlaceholder(props: TabProps & { tab: BuilderTab }) {
  const { tab, draft, onChange } = props
  const label = t(TAB_LABEL_KEY[tab])
  if (!import.meta.env.DEV) return <p>{label}</p>
  return (
    <div>
      <p>{label}</p>
      <button type="button" data-testid={`builder-tab-demo-edit-${tab}`} onClick={() => onChange(demoEdit(tab, draft))}>
        {label}
      </button>
    </div>
  )
}

type LoadState =
  | { status: 'loading' }
  | { status: 'notFound' }
  | { status: 'invalid'; reason: string }
  | { status: 'error'; error: unknown }
  | { status: 'ready'; loaded: BuilderDraft; draft: BuilderDraft; revision: string }

type SaveStatus = 'idle' | 'saving'
type SaveErrorKind = 'disabled' | 'generic' | null

export function BuilderEditorScreen(props: { scenarioId: string; tab: BuilderTab }) {
  const { scenarioId: id, tab: activeTab } = props
  const headingRef = useRef<HTMLHeadingElement>(null)
  const tabRefs = useRef<Partial<Record<BuilderTab, HTMLAnchorElement | null>>>({})
  const previewToggleRef = useRef<HTMLButtonElement>(null)
  const previewCloseRef = useRef<HTMLButtonElement>(null)
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [focusedTab, setFocusedTab] = useState<BuilderTab>(activeTab)
  const [previewOpen, setPreviewOpen] = useState(false)

  const [announcement, setAnnouncement] = useState('')
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [saveErrorKind, setSaveErrorKind] = useState<SaveErrorKind>(null)
  const [saveError, setSaveError] = useState<unknown>(null)
  const [validationAttempted, setValidationAttempted] = useState(false)
  const [conflictOpen, setConflictOpen] = useState(false)
  const [reloadConfirmOpen, setReloadConfirmOpen] = useState(false)

  const conflictDialogRef = useRef<HTMLDialogElement>(null)
  const conflictCancelRef = useRef<HTMLButtonElement>(null)
  const reloadDialogRef = useRef<HTMLDialogElement>(null)
  const reloadCancelRef = useRef<HTMLButtonElement>(null)
  const validationPanelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setFocusedTab(activeTab)
  }, [activeTab])

  useEffect(() => {
    if (previewOpen) previewCloseRef.current?.focus()
  }, [previewOpen])

  function closePreview() {
    setPreviewOpen(false)
    previewToggleRef.current?.focus()
  }

  function load(opts?: { announceOnLoad?: boolean }) {
    setState({ status: 'loading' })
    fetchScenarioDocument(id)
      .then((doc) => {
        const draft = draftOf(doc)
        setState({ status: 'ready', loaded: draft, draft, revision: doc.revision })
        setSaveErrorKind(null)
        setValidationAttempted(false)
        if (opts?.announceOnLoad) setAnnouncement(t('builder.editor.reloaded'))
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setState({ status: 'notFound' })
        } else if (err instanceof ApiError && err.status === 422) {
          setState({ status: 'invalid', reason: err.detail ?? '' })
        } else {
          setState({ status: 'error', error: err })
        }
      })
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  useEffect(() => {
    headingRef.current?.focus()
  }, [id])

  const scenarioName = state.status === 'ready' ? state.draft.meta.name : ''

  useEffect(() => {
    if (!scenarioName) return
    const previousTitle = document.title
    document.title = t('builder.editor.documentTitle', { scenario: scenarioName })
    return () => {
      document.title = previousTitle
    }
  }, [scenarioName])

  const draft = state.status === 'ready' ? state.draft : null
  const loaded = state.status === 'ready' ? state.loaded : null
  const dirty = draft && loaded ? !deepEqual(draft, loaded) : false
  const errors = draft ? validateDraft(draft) : []

  function handleChange(next: BuilderDraft) {
    setState((prev) => (prev.status === 'ready' ? { ...prev, draft: next } : prev))
  }

  function goToTab(tab: BuilderTab) {
    navigate(`#/builder/${id}/${tab}`)
  }

  function documentOf(): ScenarioDocument | null {
    if (state.status !== 'ready') return null
    const starts = Object.fromEntries(
      Object.entries(state.draft.starts).map(([id, start]) => [
        id,
        { ...start, suggestions: start.suggestions.filter((s) => s.trim() !== '') },
      ]),
    )
    return { revision: state.revision, ...state.draft, starts }
  }

  function applySaveSuccess(sent: BuilderDraft, raw: BuilderDraft, revision: string) {
    setState((prev) => {
      if (prev.status !== 'ready') return prev
      const untouchedDuringSave = deepEqual(prev.draft, raw)
      return { ...prev, draft: untouchedDuringSave ? sent : prev.draft, loaded: sent, revision }
    })
    setSaveStatus('idle')
    setSaveErrorKind(null)
    setValidationAttempted(false)
    setSavedAt(Date.now())
    setAnnouncement(t('builder.editor.saved', { folder: id }))
  }

  function doSave(force: boolean) {
    const doc = documentOf()
    if (!doc || state.status !== 'ready') return
    const raw = state.draft
    const { revision: _sentRevision, ...sent } = doc
    setSaveStatus('saving')
    setSaveErrorKind(null)
    saveScenarioDocument(id, doc, force)
      .then(({ revision }) => applySaveSuccess(sent, raw, revision))
      .catch((err) => {
        setSaveStatus('idle')
        if (err instanceof ApiError && err.status === 409) {
          setConflictOpen(true)
        } else if (err instanceof ApiError && err.status === 503) {
          setSaveErrorKind('disabled')
        } else {
          setSaveErrorKind('generic')
          setSaveError(err)
        }
      })
  }

  function handleSaveClick() {
    if (state.status !== 'ready' || saveStatus === 'saving') return
    if (errors.length > 0) {
      setValidationAttempted(true)
      return
    }
    doSave(false)
  }

  async function handleGuardSave(): Promise<void> {
    const doc = documentOf()
    if (!doc || state.status !== 'ready') throw new Error('editor not ready')
    if (errors.length > 0) {
      setValidationAttempted(true)
      throw new Error('validation failed')
    }
    const raw = state.draft
    const { revision: _sentRevision, ...sent } = doc
    setSaveStatus('saving')
    setSaveErrorKind(null)
    try {
      const { revision } = await saveScenarioDocument(id, doc)
      applySaveSuccess(sent, raw, revision)
    } catch (err) {
      setSaveStatus('idle')
      if (err instanceof ApiError && err.status === 409) {
        setConflictOpen(true)
      } else if (err instanceof ApiError && err.status === 503) {
        setSaveErrorKind('disabled')
      } else {
        setSaveErrorKind('generic')
        setSaveError(err)
      }
      throw err
    }
  }

  function handleGuardDiscard() {
    setState((prev) => (prev.status === 'ready' ? { ...prev, draft: prev.loaded } : prev))
  }

  useUnsavedGuard(dirty, { scenarioId: id, onSave: handleGuardSave, onDiscard: handleGuardDiscard })

  const handleSaveClickRef = useRef(handleSaveClick)
  handleSaveClickRef.current = handleSaveClick

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const isSaveShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's'
      if (!isSaveShortcut) return
      event.preventDefault()
      handleSaveClickRef.current()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  useEffect(() => {
    if (validationAttempted && errors.length > 0) {
      validationPanelRef.current?.focus()
    }
  }, [validationAttempted, errors.length])

  useEffect(() => {
    if (conflictOpen) {
      conflictDialogRef.current?.showModal()
      conflictCancelRef.current?.focus()
    } else {
      conflictDialogRef.current?.close()
    }
  }, [conflictOpen])

  useEffect(() => {
    if (reloadConfirmOpen) {
      reloadDialogRef.current?.showModal()
      reloadCancelRef.current?.focus()
    } else {
      reloadDialogRef.current?.close()
    }
  }, [reloadConfirmOpen])

  function handleReloadClick() {
    if (dirty) {
      setReloadConfirmOpen(true)
      return
    }
    load({ announceOnLoad: true })
  }

  function handleReloadConfirm() {
    setReloadConfirmOpen(false)
    load({ announceOnLoad: true })
  }

  function handleConflictReload() {
    setConflictOpen(false)
    load()
  }

  function handleConflictOverwrite() {
    setConflictOpen(false)
    doSave(true)
  }

  function jumpToValidationError(tab: BuilderTab, field: string) {
    goToTab(tab)
    document.getElementById(`builder-field-${field}`)?.focus()
  }

  function isTabDirty(tab: BuilderTab): boolean {
    if (!draft || !loaded || tab === 'media') return false
    return !deepEqual(slice(tab, draft), slice(tab, loaded))
  }

  function isTabInvalid(tab: BuilderTab): boolean {
    return errors.some((e) => e.tab === tab)
  }

  function handleTabKeyDown(event: React.KeyboardEvent<HTMLAnchorElement>, tab: BuilderTab) {
    const index = TAB_ORDER.indexOf(tab)
    function moveTo(nextTab: BuilderTab) {
      setFocusedTab(nextTab)
      tabRefs.current[nextTab]?.focus()
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      moveTo(TAB_ORDER[(index + 1) % TAB_ORDER.length])
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      moveTo(TAB_ORDER[(index - 1 + TAB_ORDER.length) % TAB_ORDER.length])
    } else if (event.key === 'Home') {
      event.preventDefault()
      moveTo(TAB_ORDER[0])
    } else if (event.key === 'End') {
      event.preventDefault()
      moveTo(TAB_ORDER[TAB_ORDER.length - 1])
    } else if (event.key === ' ') {
      event.preventDefault()
      goToTab(tab)
    }
  }

  const showTabs = state.status === 'loading' || state.status === 'ready'
  const tabProps: TabProps | null = draft
    ? { scenarioId: id, draft, onChange: handleChange, errors, goToTab }
    : null

  const described = state.status === 'error' ? describeError(state.error) : null

  return (
    <main className="builder-editor">
      <header className="builder-editor-topbar">
        <button type="button" className="builder-editor-back" onClick={() => navigate('#/builder')}>
          {t('builder.editor.back')}
        </button>
        <h1 ref={headingRef} tabIndex={-1} title={scenarioName || undefined}>
          {scenarioName}
        </h1>
        {state.status === 'ready' ? (
          <p className="builder-editor-folder">{t('builder.editor.folder', { folder: id })}</p>
        ) : null}
        <div className="builder-editor-actions">
          {state.status === 'ready' ? (
            <>
              <button
                type="button"
                className="builder-editor-reload"
                onClick={handleReloadClick}
              >
                {t('builder.editor.reload')}
              </button>
              <span className="builder-editor-saveShortcut">{t('builder.editor.saveShortcut')}</span>
              <button
                type="button"
                className="builder-editor-save"
                onClick={handleSaveClick}
                disabled={!dirty || saveStatus === 'saving'}
                aria-busy={saveStatus === 'saving' || undefined}
              >
                {saveStatus === 'saving' ? t('builder.editor.saving') : t('builder.editor.save')}
              </button>
              <button
                type="button"
                ref={previewToggleRef}
                className="builder-editor-previewToggle"
                aria-expanded={previewOpen}
                aria-controls="builder-editor-preview"
                onClick={() => setPreviewOpen((open) => !open)}
              >
                {previewOpen ? t('builder.editor.previewToggle.hide') : t('builder.editor.previewToggle.show')}
              </button>
            </>
          ) : null}
        </div>
        {state.status === 'ready' ? (
          <p role="status" aria-live="polite" className="builder-editor-dirty">
            {dirty ? t('builder.editor.dirty') : t('builder.editor.clean')}
          </p>
        ) : null}
      </header>

      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>

      <dialog
        ref={conflictDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-editor-conflict-title"
        onClose={() => setConflictOpen(false)}
        onCancel={(event) => {
          event.preventDefault()
          setConflictOpen(false)
        }}
      >
        <h2 id="builder-editor-conflict-title">{t('builder.editor.save.error.conflict.title')}</h2>
        <p>{t('builder.editor.save.error.conflict.body', { folder: id })}</p>
        <div className="builder-editor-dialog-actions">
          <button type="button" ref={conflictCancelRef} onClick={() => setConflictOpen(false)}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={handleConflictReload}>
            {t('builder.editor.conflict.reload')}
          </button>
          <button type="button" onClick={handleConflictOverwrite}>
            {t('builder.editor.conflict.overwrite')}
          </button>
        </div>
      </dialog>

      <dialog
        ref={reloadDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-editor-reloadConfirm-title"
        onClose={() => setReloadConfirmOpen(false)}
        onCancel={(event) => {
          event.preventDefault()
          setReloadConfirmOpen(false)
        }}
      >
        <h2 id="builder-editor-reloadConfirm-title">{t('builder.editor.reload.confirmTitle')}</h2>
        <p>{t('builder.editor.reload.confirmBody')}</p>
        <div className="builder-editor-dialog-actions">
          <button type="button" ref={reloadCancelRef} onClick={() => setReloadConfirmOpen(false)}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={handleReloadConfirm}>
            {t('builder.editor.reload.confirmSubmit')}
          </button>
        </div>
      </dialog>

      {showTabs ? (
        <nav
          role="tablist"
          aria-label={t('builder.editor.tabs.label')}
          aria-disabled={state.status === 'loading' || undefined}
          className={`builder-editor-tabs${state.status === 'loading' ? ' is-disabled' : ''}`}
        >
          {TAB_ORDER.map((tab) => {
            const selected = tab === activeTab
            const tabDirty = isTabDirty(tab)
            const tabInvalid = isTabInvalid(tab)
            return (
              <a
                key={tab}
                ref={(el) => {
                  tabRefs.current[tab] = el
                }}
                role="tab"
                id={`builder-editor-tab-${tab}`}
                href={`#/builder/${id}/${tab}`}
                aria-selected={selected}
                aria-controls="builder-editor-panel"
                tabIndex={tab === focusedTab ? 0 : -1}
                className={`builder-editor-tab${tabDirty ? ' is-dirty' : ''}${tabInvalid ? ' is-invalid' : ''}`}
                onKeyDown={(event) => handleTabKeyDown(event, tab)}
              >
                {t(TAB_LABEL_KEY[tab])}
                {tabDirty ? <span className="visually-hidden"> {t('builder.editor.tab.dirty')}</span> : null}
                {tabInvalid ? <span className="visually-hidden"> {t('builder.editor.tab.invalid')}</span> : null}
              </a>
            )
          })}
        </nav>
      ) : null}

      <div className="builder-editor-body">
        {showTabs ? (
          <>
            <section
              role="tabpanel"
              id="builder-editor-panel"
              aria-labelledby={`builder-editor-tab-${activeTab}`}
              tabIndex={0}
              className="builder-editor-panel"
            >
              {state.status === 'ready' && saveErrorKind === 'disabled' ? (
                <ErrorState
                  title={t('builder.editor.save.error.disabled.title')}
                  body={t('builder.editor.save.error.disabled.body')}
                />
              ) : null}

              {state.status === 'ready' && saveErrorKind === 'generic' ? (
                <ErrorState
                  title={t('builder.editor.save.error.title')}
                  body={t('builder.editor.save.error.body')}
                  cause={describeError(saveError).cause}
                  onRetry={() => doSave(false)}
                />
              ) : null}

              {state.status === 'ready' && validationAttempted && errors.length > 0 ? (
                <div ref={validationPanelRef} role="alert" tabIndex={-1} className="builder-editor-validation">
                  <p className="builder-editor-validation-title">{t('builder.editor.validation.summaryTitle')}</p>
                  <p>
                    {errors.length === 1
                      ? t('builder.editor.save.error.validationOne')
                      : t('builder.editor.save.error.validationOther', { count: errors.length })}
                  </p>
                  <ul>
                    {errors.map((error) => (
                      <li key={`${error.tab}:${error.field}`}>
                        <button type="button" onClick={() => jumpToValidationError(error.tab, error.field)}>
                          {t('builder.editor.validation.jump', { field: error.label })}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {state.status === 'loading' ? (
                <>
                  <div className="builder-skeleton-block" aria-hidden="true" />
                  <div className="builder-skeleton-block" aria-hidden="true" />
                  <Loading label={t('builder.editor.loading')} visuallyHidden />
                </>
              ) : (
                tabProps &&
                (activeTab === 'identity' ? (
                  <IdentityTab {...tabProps} />
                ) : activeTab === 'world' ? (
                  <WorldTab {...tabProps} />
                ) : activeTab === 'starts' ? (
                  <StartsTab {...tabProps} />
                ) : activeTab === 'characters' ? (
                  <CharactersTab {...tabProps} />
                ) : activeTab === 'media' ? (
                  <MediaTab {...tabProps} />
                ) : (
                  <TabPlaceholder tab={activeTab} {...tabProps} />
                ))
              )}
            </section>
            <aside
              id="builder-editor-preview"
              aria-label={t('builder.preview.regionLabel')}
              className={`builder-editor-preview${previewOpen ? ' is-open' : ''}`}
            >
              <button type="button" ref={previewCloseRef} className="builder-editor-previewClose" onClick={closePreview}>
                {t('builder.editor.previewClose')}
              </button>
              {state.status === 'ready' ? (
                <BuilderPreview
                  scenarioId={id}
                  draft={state.draft}
                  loadedStartIds={Object.keys(state.loaded.starts)}
                  dirty={dirty}
                  savedAt={savedAt}
                  onSave={handleGuardSave}
                />
              ) : null}
            </aside>
          </>
        ) : null}

        {state.status === 'notFound' ? (
          <ErrorState
            title={t('builder.editor.notFound.title')}
            body={t('builder.editor.notFound.body')}
            onRetry={undefined}
          />
        ) : null}

        {state.status === 'notFound' ? (
          <div className="builder-editor-notFound-back">
            <button type="button" onClick={() => navigate('#/builder')}>
              {t('common.back')}
            </button>
          </div>
        ) : null}

        {state.status === 'invalid' ? (
          <ErrorState
            title={t('builder.editor.invalid.title')}
            body={t('builder.editor.invalid.body', { reason: state.reason })}
            cause={state.reason}
            onRetry={load}
          />
        ) : null}

        {described ? (
          <ErrorState title={described.title} body={described.body} cause={described.cause} onRetry={load} />
        ) : null}
      </div>
    </main>
  )
}
