import { useEffect, useRef, useState } from 'react'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { Loading } from '../components/Loading'
import { describeError } from '../errors'
import { intlLocale, t } from '../i18n'
import { navigate } from '../useHashRoute'
import {
  createSession,
  fetchScenarios,
  fetchSessions,
  type ScenarioSummary,
  type SessionSummary,
} from '../api'
import './sessions.css'

const RELATIVE_UNITS: { unit: Intl.RelativeTimeFormatUnit; seconds: number }[] = [
  { unit: 'year', seconds: 31536000 },
  { unit: 'month', seconds: 2592000 },
  { unit: 'week', seconds: 604800 },
  { unit: 'day', seconds: 86400 },
  { unit: 'hour', seconds: 3600 },
  { unit: 'minute', seconds: 60 },
]

function formatRelativeTime(isoDate: string, locale: string): string {
  const then = new Date(isoDate).getTime()
  const diffSeconds = Math.round((then - Date.now()) / 1000)
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })

  for (const { unit, seconds } of RELATIVE_UNITS) {
    if (Math.abs(diffSeconds) >= seconds) {
      return formatter.format(Math.round(diffSeconds / seconds), unit)
    }
  }
  return formatter.format(diffSeconds, 'second')
}

function turnsLabel(turnCount: number): string {
  if (turnCount === 0) return t('sessions.item.turnsZero')
  if (turnCount === 1) return t('sessions.item.turnsOne')
  return t('sessions.item.turnsOther', { count: turnCount })
}

type SessionsState =
  | { status: 'loading' }
  | { status: 'error'; error: unknown }
  | { status: 'loaded'; sessions: SessionSummary[] }

type ScenariosState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'loaded'; scenarios: ScenarioSummary[] }

export function SessionsScreen() {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [sessionsState, setSessionsState] = useState<SessionsState>({ status: 'loading' })
  const [scenariosState, setScenariosState] = useState<ScenariosState>({ status: 'loading' })
  const [selectedScenarioId, setSelectedScenarioId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<unknown>(null)

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  const loadSessions = () => {
    setSessionsState({ status: 'loading' })
    fetchSessions()
      .then((sessions) => setSessionsState({ status: 'loaded', sessions }))
      .catch((error) => setSessionsState({ status: 'error', error }))
  }

  useEffect(() => {
    loadSessions()
  }, [])

  useEffect(() => {
    fetchScenarios()
      .then((scenarios) => {
        setScenariosState({ status: 'loaded', scenarios })
        if (scenarios.length > 0) setSelectedScenarioId(scenarios[0].id)
      })
      .catch(() => setScenariosState({ status: 'error' }))
  }, [])

  const sessionsError = sessionsState.status === 'error' ? describeError(sessionsState.error) : null
  const scenarios = scenariosState.status === 'loaded' ? scenariosState.scenarios : []
  const selectedScenario = scenarios.find((scenario) => scenario.id === selectedScenarioId)
  const scenariosFailed = scenariosState.status === 'error'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting || !selectedScenarioId) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const session = await createSession(selectedScenarioId)
      navigate(`#/session/${session.id}`)
    } catch (error) {
      setSubmitError(error)
      setSubmitting(false)
    }
  }

  return (
    <main className="sessions">
      <h1 ref={headingRef} tabIndex={-1}>
        {t('app.title')}
      </h1>

      <section className="sessions-new">
        <h2>{t('sessions.new.heading')}</h2>
        <form onSubmit={(e) => void handleSubmit(e)}>
          <label htmlFor="sessions-new-scenario">{t('sessions.new.scenarioLabel')}</label>
          <select
            id="sessions-new-scenario"
            value={selectedScenarioId}
            onChange={(e) => setSelectedScenarioId(e.target.value)}
            disabled={submitting || scenariosFailed || scenarios.length === 0}
          >
            {scenarios.map((scenario) => (
              <option key={scenario.id} value={scenario.id}>
                {scenario.name}
              </option>
            ))}
          </select>
          {selectedScenario?.tagline ? <p className="sessions-new-tagline">{selectedScenario.tagline}</p> : null}
          {scenariosFailed ? <p className="sessions-new-scenarios-error">{t('sessions.new.scenariosError')}</p> : null}
          <button type="submit" aria-busy={submitting} disabled={submitting || scenariosFailed || !selectedScenarioId}>
            {submitting ? t('sessions.new.submitting') : t('sessions.new.submit')}
          </button>
        </form>
        {submitError ? (
          <ErrorState title={t('error.unexpected.title')} body={t('sessions.new.error')} />
        ) : null}
      </section>

      <section className="sessions-list">
        <h2>{t('sessions.heading')}</h2>
        {sessionsState.status === 'loading' ? (
          <>
            <ul className="sessions-skeleton" aria-hidden="true">
              <li />
              <li />
              <li />
            </ul>
            <Loading label={t('sessions.loading')} visuallyHidden />
          </>
        ) : null}

        {sessionsError ? <ErrorState title={sessionsError.title} body={sessionsError.body} onRetry={loadSessions} /> : null}

        {sessionsState.status === 'loaded' && sessionsState.sessions.length === 0 ? (
          <EmptyState title={t('sessions.empty.title')} body={t('sessions.empty.body')} />
        ) : null}

        {sessionsState.status === 'loaded' && sessionsState.sessions.length > 0 ? (
          <ul>
            {sessionsState.sessions.map((session) => (
              <li key={session.id}>
                <button
                  type="button"
                  className="sessions-item"
                  title={session.updatedAt}
                  onClick={() => navigate(`#/session/${session.id}`)}
                >
                  <span className="sessions-item-name">{session.scenarioName}</span>
                  <span className="sessions-item-meta">
                    {t('sessions.item.meta', {
                      turns: turnsLabel(session.turnCount),
                      when: formatRelativeTime(session.updatedAt, intlLocale),
                    })}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </main>
  )
}
