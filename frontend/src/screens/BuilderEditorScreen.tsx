import { useEffect, useRef, useState } from 'react'
import { ApiError, fetchScenarioDocument, type ScenarioDocument } from '../api'
import { deepEqual, validateDraft } from '../builder/validate'
import { ErrorState } from '../components/ErrorState'
import { Loading } from '../components/Loading'
import { describeError } from '../errors'
import { t, type StringKey } from '../i18n'
import { navigate, type BuilderTab } from '../useHashRoute'
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
    case 'identity':
      return draft.meta
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
  if (tab === 'media') return <p>{label}</p>
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

export function BuilderEditorScreen(props: { scenarioId: string; tab: BuilderTab }) {
  const { scenarioId: id, tab: activeTab } = props
  const headingRef = useRef<HTMLHeadingElement>(null)
  const tabRefs = useRef<Partial<Record<BuilderTab, HTMLAnchorElement | null>>>({})
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [focusedTab, setFocusedTab] = useState<BuilderTab>(activeTab)

  useEffect(() => {
    setFocusedTab(activeTab)
  }, [activeTab])

  function load() {
    setState({ status: 'loading' })
    fetchScenarioDocument(id)
      .then((doc) => {
        const draft = draftOf(doc)
        setState({ status: 'ready', loaded: draft, draft, revision: doc.revision })
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

  const errorCause = state.status === 'error' ? describeError(state.error).cause : undefined

  return (
    <main className="builder-editor">
      <header className="builder-editor-topbar">
        <button type="button" className="builder-editor-back" onClick={() => navigate('#/builder')}>
          {t('builder.editor.back')}
        </button>
        <h1 ref={headingRef} tabIndex={-1} title={scenarioName || undefined}>
          {scenarioName}
        </h1>
        <p className="builder-editor-folder">{t('builder.editor.folder', { folder: id })}</p>
        <div className="builder-editor-actions" />
        <p role="status" aria-live="polite" className="builder-editor-dirty">
          {dirty ? t('builder.editor.dirty') : t('builder.editor.clean')}
        </p>
      </header>

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
              {state.status === 'loading' ? (
                <>
                  <div className="builder-skeleton-block" aria-hidden="true" />
                  <div className="builder-skeleton-block" aria-hidden="true" />
                  <Loading label={t('builder.editor.loading')} visuallyHidden />
                </>
              ) : (
                tabProps && <TabPlaceholder tab={activeTab} {...tabProps} />
              )}
            </section>
            <aside className="builder-editor-preview" />
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

        {state.status === 'error' ? (
          <ErrorState title={t('builder.editor.error.title')} body={t('builder.editor.error.body')} cause={errorCause} onRetry={load} />
        ) : null}
      </div>
    </main>
  )
}
