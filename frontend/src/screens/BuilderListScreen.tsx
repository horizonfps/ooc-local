import { useEffect, useRef, useState } from 'react'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { Loading } from '../components/Loading'
import { describeError } from '../errors'
import { t } from '../i18n'
import { navigate } from '../useHashRoute'
import { fetchBuilderScenarios, type BuilderScenarioItem } from '../api'
import '../components/states.css'
import './builder.css'

const COVER_EXTENSIONS = ['png', 'jpg', 'webp'] as const

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

function BuilderCard(props: { scenario: BuilderScenarioItem }) {
  const { scenario } = props

  if (scenario.status === 'invalid') {
    return (
      <li className="builder-card builder-card-invalid">
        <span className="builder-card-name">{scenario.name || scenario.id}</span>
        <ErrorState
          title={t('builder.list.item.broken')}
          body={t('builder.list.item.brokenBody', { reason: scenario.reason ?? '' })}
        />
        <div className="builder-card-actions" />
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
      <div className="builder-card-actions" />
    </li>
  )
}

export function BuilderListScreen() {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [state, setState] = useState<ListState>({ status: 'loading' })
  const [announcement, setAnnouncement] = useState('')

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
        setAnnouncement(t('builder.list.reloaded'))
      })
      .catch((error) => setState({ status: 'error', error }))
  }

  const error = state.status === 'error' ? describeError(state.error) : null

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

      {error ? <ErrorState title={error.title} body={error.body} cause={error.cause} onRetry={load} /> : null}

      {state.status === 'loaded' && state.scenarios.length === 0 ? (
        <EmptyState title={t('builder.list.empty.title')} body={t('builder.list.empty.body')} />
      ) : null}

      {state.status === 'loaded' && state.scenarios.length > 0 ? (
        <ul className="builder-card-grid">
          {state.scenarios.map((scenario) => (
            <BuilderCard key={scenario.id} scenario={scenario} />
          ))}
        </ul>
      ) : null}
    </main>
  )
}
