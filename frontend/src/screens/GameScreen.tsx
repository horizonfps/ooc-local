import { useEffect, useRef, useState } from 'react'
import { ErrorState } from '../components/ErrorState'
import { Hud } from '../components/Hud'
import { Loading } from '../components/Loading'
import { TurnText } from '../components/TurnText'
import { ApiError, fetchSession, type SessionDetail } from '../api'
import { describeError } from '../errors'
import { t } from '../i18n'
import { navigate } from '../useHashRoute'
import './game.css'

type GameState =
  | { phase: 'loading' }
  | { phase: 'error'; error: unknown }
  | { phase: 'notFound' }
  | { phase: 'ready'; session: SessionDetail }

export function GameScreen(props: { sessionId: string }) {
  const { sessionId } = props
  const headingRef = useRef<HTMLHeadingElement>(null)
  const historyRef = useRef<HTMLOListElement>(null)
  const [state, setState] = useState<GameState>({ phase: 'loading' })

  const load = () => {
    setState({ phase: 'loading' })
    fetchSession(sessionId)
      .then((session) => setState({ phase: 'ready', session }))
      .catch((error) => {
        if (error instanceof ApiError && error.status === 404) {
          setState({ phase: 'notFound' })
        } else {
          setState({ phase: 'error', error })
        }
      })
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  useEffect(() => {
    headingRef.current?.focus()
  }, [sessionId])

  useEffect(() => {
    if (state.phase !== 'ready') return
    const previousTitle = document.title
    document.title = t('game.documentTitle', { scenario: state.session.scenarioName })
    return () => {
      document.title = previousTitle
    }
  }, [state])

  useEffect(() => {
    if (state.phase !== 'ready') return
    const el = historyRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [state.phase, sessionId])

  const scenarioName = state.phase === 'ready' ? state.session.scenarioName : ''

  return (
    <main className="game">
      <div className="game-topbar">
        <button type="button" className="game-back" onClick={() => navigate('#/')}>
          {t('game.back')}
        </button>
        <h1 ref={headingRef} tabIndex={-1} title={scenarioName || undefined}>
          {scenarioName}
        </h1>
      </div>

      <Hud hud={state.phase === 'ready' ? state.session.hud : null} />

      {state.phase === 'loading' ? (
        <div className="game-history game-history--skeleton" aria-hidden="true">
          <div className="game-skeleton-block" />
          <div className="game-skeleton-block" />
        </div>
      ) : null}
      {state.phase === 'loading' ? <Loading label={t('game.loading')} visuallyHidden /> : null}

      {state.phase === 'notFound' ? (
        <>
          <ErrorState title={t('game.notFound.title')} body={t('game.notFound.body')} />
          <div className="game-notFound-back">
            <button type="button" onClick={() => navigate('#/')}>
              {t('common.back')}
            </button>
          </div>
        </>
      ) : null}

      {state.phase === 'error'
        ? (() => {
            const described = describeError(state.error)
            return <ErrorState title={described.title} body={described.body} cause={described.cause} onRetry={load} />
          })()
        : null}

      {state.phase === 'ready' ? (
        <ol className="game-history" ref={historyRef}>
          <li className="game-turn game-turn--prologue">
            <span className="game-turn-label">{t('game.prologue.label')}</span>
            <TurnText text={state.session.prologue} />
          </li>
          {state.session.turns.map((turn) => (
            <li
              key={turn.index}
              className={turn.role === 'player' ? 'game-turn game-turn--player' : 'game-turn game-turn--narrator'}
            >
              <span className="game-turn-label">
                {turn.role === 'player' ? t('game.turn.playerLabel') : t('game.turn.narratorLabel')}
              </span>
              {turn.role === 'player' ? <p className="game-turn-text">{turn.text}</p> : <TurnText text={turn.text} />}
            </li>
          ))}
        </ol>
      ) : null}

      {state.phase === 'ready' && state.session.turns.length === 0 ? (
        <p className="game-empty-hint">{t('game.empty.hint')}</p>
      ) : null}

      <div className="game-footer" />
    </main>
  )
}
