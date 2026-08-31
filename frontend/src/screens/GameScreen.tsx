import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { ErrorState } from '../components/ErrorState'
import { Hud } from '../components/Hud'
import { Loading } from '../components/Loading'
import { TurnText } from '../components/TurnText'
import { ApiError, fetchSession, streamTurn, type HudState, type SessionDetail, type TurnView } from '../api'
import { describeError } from '../errors'
import { t } from '../i18n'
import { navigate } from '../useHashRoute'
import './game.css'

type GameState =
  | { phase: 'loading' }
  | { phase: 'error'; error: unknown }
  | { phase: 'notFound' }
  | { phase: 'ready'; session: SessionDetail }

type PreStreamKind = 'chatDisabled' | 'offline' | 'unexpected'

type PendingTurn =
  | { index: number; message: string; text: string; status: 'streaming' }
  | { index: number; message: string; text: string; status: 'error'; kind: 'stream'; cause: string }
  | { index: number; message: string; text: string; status: 'error'; kind: PreStreamKind; title: string; body: string; cause: string }
  | { index: number; message: string; text: string; status: 'error'; kind: 'notFound' }

function isReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

function scrollToBottom(el: HTMLElement) {
  const behavior = isReducedMotion() ? 'auto' : 'smooth'
  if (typeof el.scrollTo === 'function') {
    el.scrollTo({ top: el.scrollHeight, behavior })
  } else {
    el.scrollTop = el.scrollHeight
  }
}

export function GameScreen(props: { sessionId: string }) {
  const { sessionId } = props
  const headingRef = useRef<HTMLHeadingElement>(null)
  const historyRef = useRef<HTMLOListElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sendingRef = useRef(false)
  const [state, setState] = useState<GameState>({ phase: 'loading' })

  const [draft, setDraft] = useState('')
  const [turnPhase, setTurnPhase] = useState<'idle' | 'streaming'>('idle')
  const [pending, setPending] = useState<PendingTurn | null>(null)
  const [extraTurns, setExtraTurns] = useState<TurnView[]>([])
  const [hud, setHud] = useState<HudState | null>(null)
  const [hudStale, setHudStale] = useState(false)
  const [lastMessage, setLastMessage] = useState('')
  const [atBottom, setAtBottom] = useState(true)
  const [doneAnnouncement, setDoneAnnouncement] = useState('')
  const [focusToken, setFocusToken] = useState(0)

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
    setDraft('')
    setTurnPhase('idle')
    setPending(null)
    setExtraTurns([])
    setHudStale(false)
    setLastMessage('')
    setDoneAnnouncement('')
  }, [sessionId])

  useEffect(() => {
    if (state.phase === 'ready') setHud(state.session.hud)
  }, [state])

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

  useEffect(() => {
    if (!atBottom) return
    const el = historyRef.current
    if (!el) return
    scrollToBottom(el)
  }, [atBottom, extraTurns.length, pending])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [draft])

  useEffect(() => {
    if (focusToken === 0) return
    textareaRef.current?.focus()
  }, [focusToken])

  const handleScroll = () => {
    const el = historyRef.current
    if (!el) return
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 32)
  }

  const jumpToLatest = () => {
    setAtBottom(true)
    const el = historyRef.current
    if (el) scrollToBottom(el)
  }

  const nextIndex = () => {
    if (state.phase !== 'ready') return 1
    const turns = [...state.session.turns, ...extraTurns]
    return turns.length > 0 ? turns[turns.length - 1].index + 1 : 1
  }

  const runTurn = async (message: string) => {
    if (sendingRef.current) return
    sendingRef.current = true
    setTurnPhase('streaming')
    const index = nextIndex()
    setLastMessage(message)
    setPending({ index, message, text: '', status: 'streaming' })

    let sawError = false
    let sawHud = false
    let succeeded = false
    try {
      await streamTurn(sessionId, message, {
        onDelta: (delta) => setPending((p) => (p ? { ...p, text: p.text + delta } : p)),
        onHud: (newHud) => {
          sawHud = true
          setHud(newHud)
          setHudStale(false)
        },
        onError: (err) => {
          sawError = true
          setHudStale(true)
          setPending((p) => (p ? { index: p.index, message: p.message, text: p.text, status: 'error', kind: 'stream', cause: String(err) } : p))
        },
      })

      if (!sawError) {
        succeeded = true
        if (!sawHud) setHudStale(true)
        setPending((p) => {
          if (!p) return p
          setExtraTurns((prev) => [
            ...prev,
            { index: p.index, role: 'player', text: p.message },
            { index: p.index, role: 'narrator', text: p.text },
          ])
          setDoneAnnouncement(t('game.turn.done', { index: p.index }))
          return null
        })
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setPending((p) => (p ? { index: p.index, message: p.message, text: p.text, status: 'error', kind: 'notFound' } : p))
      } else {
        const described = describeError(err)
        const kind: PreStreamKind = err instanceof TypeError ? 'offline' : err instanceof ApiError && err.status === 503 ? 'chatDisabled' : 'unexpected'
        setPending((p) =>
          p ? { index: p.index, message: p.message, text: p.text, status: 'error', kind, title: described.title, body: described.body, cause: described.cause } : p,
        )
      }
      setHudStale(true)
      setDraft(message)
    } finally {
      sendingRef.current = false
      setTurnPhase('idle')
      if (succeeded) {
        setFocusToken((n) => n + 1)
      }
    }
  }

  const submit = () => {
    const message = draft.trim()
    if (message === '' || turnPhase === 'streaming') return
    setDraft('')
    void runTurn(message)
  }

  const retry = () => {
    if (turnPhase === 'streaming') return
    void runTurn(lastMessage)
  }

  const handleFormSubmit = (e: FormEvent) => {
    e.preventDefault()
    submit()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const scenarioName = state.phase === 'ready' ? state.session.scenarioName : ''
  const turns = state.phase === 'ready' ? [...state.session.turns, ...extraTurns] : []

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

      <Hud hud={state.phase === 'ready' ? hud : null} busy={turnPhase === 'streaming'} stale={hudStale} />

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
        <ol className="game-history" ref={historyRef} onScroll={handleScroll}>
          <li className="game-turn game-turn--prologue">
            <span className="game-turn-label">{t('game.prologue.label')}</span>
            <TurnText text={state.session.prologue} />
          </li>
          {turns.map((turn) => (
            <li
              key={`${turn.index}-${turn.role}`}
              className={turn.role === 'player' ? 'game-turn game-turn--player' : 'game-turn game-turn--narrator'}
            >
              <span className="game-turn-label">
                {turn.role === 'player' ? t('game.turn.playerLabel') : t('game.turn.narratorLabel')}
              </span>
              {turn.role === 'player' ? <p className="game-turn-text">{turn.text}</p> : <TurnText text={turn.text} />}
            </li>
          ))}

          {pending ? (
            <li className="game-turn game-turn--player">
              <span className="game-turn-label">{t('game.turn.playerLabel')}</span>
              <p className="game-turn-text">{pending.message}</p>
            </li>
          ) : null}

          {pending ? (
            <li className="game-turn game-turn--narrator">
              <span className="game-turn-label">{t('game.turn.narratorLabel')}</span>

              {pending.status === 'streaming' && pending.text === '' ? (
                <p role="status" aria-live="polite">
                  {t('game.turn.thinking')}
                </p>
              ) : null}

              {pending.status === 'streaming' ? (
                <div aria-live="off">
                  <TurnText text={pending.text} streaming />
                </div>
              ) : null}

              {pending.status === 'error' && pending.kind === 'stream' ? (
                <>
                  {pending.text.trim() !== '' ? (
                    <div className="game-turn-partial">
                      <span className="game-turn-partial-label">{t('game.turn.partial')}</span>
                      <TurnText text={pending.text} />
                    </div>
                  ) : null}
                  <ErrorState title={t('game.turn.error')} body={t('game.turn.errorBody')} cause={pending.cause} onRetry={retry} />
                </>
              ) : null}

              {pending.status === 'error' && (pending.kind === 'chatDisabled' || pending.kind === 'offline' || pending.kind === 'unexpected') ? (
                <ErrorState title={pending.title} body={pending.body} cause={pending.cause} onRetry={retry} />
              ) : null}

              {pending.status === 'error' && pending.kind === 'notFound' ? (
                <>
                  <ErrorState title={t('game.notFound.title')} body={t('game.notFound.body')} />
                  <div className="game-notFound-back">
                    <button type="button" onClick={() => navigate('#/')}>
                      {t('common.back')}
                    </button>
                  </div>
                </>
              ) : null}
            </li>
          ) : null}
        </ol>
      ) : null}

      {state.phase === 'ready' && state.session.turns.length === 0 && extraTurns.length === 0 && !pending ? (
        <p className="game-empty-hint">{t('game.empty.hint')}</p>
      ) : null}

      <p className="visually-hidden" aria-live="polite" role="status">
        {doneAnnouncement}
      </p>

      {state.phase === 'ready' && !atBottom ? (
        <button type="button" className="game-scrollLatest" onClick={jumpToLatest}>
          {t('game.scrollToLatest')}
        </button>
      ) : null}

      {state.phase === 'ready' ? (
        <form className="game-footer" onSubmit={handleFormSubmit}>
          <label htmlFor="game-input" className="visually-hidden">
            {t('game.input.label')}
          </label>
          <textarea
            id="game-input"
            ref={textareaRef}
            className="game-input-textarea"
            rows={1}
            value={draft}
            placeholder={t('game.input.placeholder')}
            disabled={turnPhase === 'streaming'}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button type="submit" disabled={turnPhase === 'streaming' || draft.trim() === ''} aria-busy={turnPhase === 'streaming'}>
            {turnPhase === 'streaming' ? t('game.input.sending') : t('game.input.send')}
          </button>
          <p className="game-input-hint">{t('game.input.hint')}</p>
        </form>
      ) : (
        <div className="game-footer" />
      )}
    </main>
  )
}
