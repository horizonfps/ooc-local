import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { CastRow } from './CastRow'
import { ErrorState } from './ErrorState'
import { Hud } from './Hud'
import { Loading } from './Loading'
import { TurnText, findUnclosedBracket } from './TurnText'
import { fetchSession, streamTurn, type CastMember, type HudState, type SessionAssets, type SessionDetail, type TurnView } from '../api'
import { classifyError, describeError, type ErrorKind } from '../errors'
import { t } from '../i18n'
import { navigate } from '../useHashRoute'
import { EMPTY_SCENE, reduceScene, resolveBackground, resolveSprite } from '../scene'
import './stage.css'

const STAGE_STORAGE_KEY = 'ooc-local:stage'

function readStagePreference(): boolean {
  try {
    const raw = localStorage.getItem(STAGE_STORAGE_KEY)
    return raw === null ? true : raw === '1'
  } catch {
    return true
  }
}

function writeStagePreference(value: boolean) {
  try {
    localStorage.setItem(STAGE_STORAGE_KEY, value ? '1' : '0')
  } catch {
    // localStorage unavailable: preference just doesn't persist
  }
}

type GameState =
  | { phase: 'loading' }
  | { phase: 'error'; error: unknown }
  | { phase: 'notFound' }
  | { phase: 'ready'; session: SessionDetail }

type PendingTurn =
  | { index: number; message: string; text: string; status: 'streaming' }
  | { index: number; message: string; text: string; status: 'error'; kind: 'stream'; cause: string }
  | { index: number; message: string; text: string; status: 'error'; kind: ErrorKind; title: string; body: string; cause: string }

function isReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

function scrollToBottom(el: HTMLElement, behavior: ScrollBehavior) {
  if (typeof el.scrollTo === 'function') {
    el.scrollTo({ top: el.scrollHeight, behavior })
  } else {
    el.scrollTop = el.scrollHeight
  }
}

export type GamePanelProps = {
  sessionId: string
  onNotFound?: () => void
  onSessionLoaded?: (session: SessionDetail) => void
  onTurnsChanged?: (count: number) => void
  regionLabel?: string
  autoFocusInput?: boolean
}

export function GamePanel(props: GamePanelProps) {
  const { sessionId, onNotFound, onSessionLoaded, onTurnsChanged, regionLabel, autoFocusInput = true } = props
  const inputId = useId()
  const historyRef = useRef<HTMLOListElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sendingRef = useRef(false)
  const scrollFrameRef = useRef<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const onNotFoundRef = useRef(onNotFound)
  onNotFoundRef.current = onNotFound
  const onSessionLoadedRef = useRef(onSessionLoaded)
  onSessionLoadedRef.current = onSessionLoaded
  const onTurnsChangedRef = useRef(onTurnsChanged)
  onTurnsChangedRef.current = onTurnsChanged
  const [state, setState] = useState<GameState>({ phase: 'loading' })

  const [draft, setDraft] = useState('')
  const [turnPhase, setTurnPhase] = useState<'idle' | 'streaming'>('idle')
  const [pending, setPending] = useState<PendingTurn | null>(null)
  const [extraTurns, setExtraTurns] = useState<TurnView[]>([])
  const [hud, setHud] = useState<HudState | null>(null)
  const [hudStale, setHudStale] = useState(false)
  const [cast, setCast] = useState<CastMember[] | null>(null)
  const [lastMessage, setLastMessage] = useState('')
  const [atBottom, setAtBottom] = useState(true)
  const [doneAnnouncement, setDoneAnnouncement] = useState('')
  const [sceneAnnouncement, setSceneAnnouncement] = useState('')
  const [castAnnouncement, setCastAnnouncement] = useState('')
  const [focusToken, setFocusToken] = useState(0)
  const [stageEnabled, setStageEnabled] = useState(readStagePreference)
  const [backgroundUrl, setBackgroundUrl] = useState<string | null>(null)
  const [brokenSpriteUrls, setBrokenSpriteUrls] = useState<Set<string>>(new Set())
  const prevAnnounceRef = useRef<{ background: string | null; charactersKey: string } | null>(null)
  const prevCastKeyRef = useRef<string | null>(null)

  const load = () => {
    setState({ phase: 'loading' })
    fetchSession(sessionId)
      .then((session) => setState({ phase: 'ready', session }))
      .catch((error) => {
        if (classifyError(error).kind === 'notFound') {
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
    abortRef.current?.abort()
    abortRef.current = null
    setDraft('')
    setTurnPhase('idle')
    setPending(null)
    setExtraTurns([])
    setHudStale(false)
    setCast(null)
    setLastMessage('')
    setDoneAnnouncement('')
    setSceneAnnouncement('')
    setCastAnnouncement('')
    setBackgroundUrl(null)
    setBrokenSpriteUrls(new Set())
    prevAnnounceRef.current = null
    prevCastKeyRef.current = null
  }, [sessionId])

  useEffect(
    () => () => {
      abortRef.current?.abort()
      abortRef.current = null
    },
    [],
  )

  useEffect(() => {
    if (state.phase === 'ready') {
      setHud(state.session.hud)
      setCast(state.session.cast)
    }
  }, [state])

  useEffect(() => {
    if (state.phase === 'notFound') onNotFoundRef.current?.()
  }, [state.phase])

  useEffect(() => {
    if (state.phase === 'ready') onSessionLoadedRef.current?.(state.session)
  }, [state])

  useEffect(() => {
    if (state.phase !== 'ready') return
    const count = Math.floor((state.session.turns.length + extraTurns.length) / 2)
    onTurnsChangedRef.current?.(count)
  }, [state, extraTurns.length])

  useEffect(() => {
    if (state.phase !== 'ready') return
    const el = historyRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [state.phase, sessionId])

  useEffect(() => {
    if (state.phase !== 'ready' || !autoFocusInput) return
    textareaRef.current?.focus()
  }, [state.phase, sessionId, autoFocusInput])

  useEffect(() => {
    if (!atBottom) return
    const el = historyRef.current
    if (!el) return
    if (scrollFrameRef.current !== null) cancelAnimationFrame(scrollFrameRef.current)
    scrollFrameRef.current = requestAnimationFrame(() => {
      scrollFrameRef.current = null
      scrollToBottom(el, 'auto')
    })
    return () => {
      if (scrollFrameRef.current !== null) {
        cancelAnimationFrame(scrollFrameRef.current)
        scrollFrameRef.current = null
      }
    }
  }, [atBottom, extraTurns.length, pending?.text.length ?? 0])

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
    if (el) scrollToBottom(el, isReducedMotion() ? 'auto' : 'smooth')
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
    setSceneAnnouncement('')
    setCastAnnouncement('')

    const controller = new AbortController()
    abortRef.current = controller

    let sawError = false
    let sawHud = false
    let succeeded = false
    let narratorText = ''
    try {
      await streamTurn(
        sessionId,
        message,
        {
          onDelta: (delta) => {
            narratorText += delta
            setPending((p) => (p ? { ...p, text: p.text + delta } : p))
          },
          onHud: (newHud) => {
            sawHud = true
            setHud(newHud)
            setHudStale(false)
            if (newHud.cast != null) setCast(newHud.cast)
          },
          onError: (err) => {
            sawError = true
            setHudStale(true)
            setPending((p) => (p ? { index: p.index, message: p.message, text: p.text, status: 'error', kind: 'stream', cause: String(err) } : p))
          },
        },
        { signal: controller.signal },
      )

      if (controller.signal.aborted) return

      if (!sawError) {
        succeeded = true
        if (!sawHud) setHudStale(true)
        setExtraTurns((prev) => [
          ...prev,
          { index, role: 'player', text: message },
          { index, role: 'narrator', text: narratorText },
        ])
        setDoneAnnouncement(t('game.turn.done', { index }))
        setPending(null)
        setDraft((d) => (d === message ? '' : d))
      }
    } catch (err) {
      if (controller.signal.aborted) return
      const classified = classifyError(err)
      setPending((p) =>
        p
          ? { index: p.index, message: p.message, text: p.text, status: 'error', kind: classified.kind, title: classified.title, body: classified.body, cause: classified.cause }
          : p,
      )
      setHudStale(true)
      setDraft(message)
    } finally {
      if (abortRef.current === controller) abortRef.current = null
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

  const turns = state.phase === 'ready' ? [...state.session.turns, ...extraTurns] : []
  const hudView = state.phase === 'ready' ? (hud ?? state.session.hud) : null
  const castView = state.phase === 'ready' ? (cast ?? state.session.cast) : null
  const inputId_ = `game-input-${inputId}`

  const sceneText = useMemo(() => {
    if (state.phase !== 'ready') return ''
    const parts = [state.session.prologue, ...turns.map((turn) => turn.text)]
    if (pending) {
      if (pending.status === 'streaming') {
        const cutoff = findUnclosedBracket(pending.text)
        parts.push(cutoff === -1 ? pending.text : pending.text.slice(0, cutoff))
      } else {
        parts.push(pending.text)
      }
    }
    return parts.join('\n')
  }, [state.phase, state.phase === 'ready' ? state.session.prologue : null, turns, pending?.status, pending?.text])

  const scene = useMemo(() => reduceScene(EMPTY_SCENE, sceneText), [sceneText])

  const assets: SessionAssets | null = state.phase === 'ready' ? state.session.assets : null
  const hasArt = assets !== null && (Object.keys(assets.sprites).length > 0 || Object.keys(assets.backgrounds).length > 0)

  const resolvedBackground = assets && scene.background ? resolveBackground(assets, scene.background) : null

  useEffect(() => {
    if (resolvedBackground !== null) setBackgroundUrl(resolvedBackground)
  }, [resolvedBackground])

  const resolvedSprites = assets
    ? scene.sprites
        .map((s) => ({ ...s, url: resolveSprite(assets, s.character, s.emotion) }))
        .filter((s): s is typeof s & { url: string } => s.url !== null)
    : []

  const visibleSprites = resolvedSprites.filter((s) => !brokenSpriteUrls.has(s.url))

  const spritesKey = scene.sprites.map((s) => `${s.character}:${s.emotion}`).join('|')

  useEffect(() => {
    if (state.phase !== 'ready') return
    const charactersKey = spritesKey
    const prev = prevAnnounceRef.current
    prevAnnounceRef.current = { background: scene.background, charactersKey }
    if (prev === null) return

    const backgroundChanged = prev.background !== scene.background
    const charactersChanged = prev.charactersKey !== charactersKey
    if (!backgroundChanged && !charactersChanged) return

    const backgroundText = scene.background ?? ''
    const charactersText =
      resolvedSprites.length === 0
        ? t('game.scene.empty')
        : resolvedSprites.map((s) => t('game.scene.characterEmotion', { character: s.character, emotion: s.emotion })).join(', ')

    if (backgroundChanged && charactersChanged) {
      setSceneAnnouncement(t('game.scene.announce', { background: backgroundText, characters: charactersText }))
    } else if (backgroundChanged) {
      setSceneAnnouncement(t('game.scene.announceBackground', { background: backgroundText }))
    } else {
      setSceneAnnouncement(t('game.scene.announceCharacters', { characters: charactersText }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase, scene.background, spritesKey])

  const castKey = cast === null ? '\0null' : cast.map((m) => m.id).join('|')

  useEffect(() => {
    const prev = prevCastKeyRef.current
    prevCastKeyRef.current = castKey
    if (prev === null || prev === '\0null') return
    if (prev === castKey) return

    const characters = cast === null || cast.length === 0 ? t('game.cast.empty') : cast.map((m) => m.name || m.id).join(', ')
    setCastAnnouncement(t('game.cast.announce', { characters }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [castKey])

  const handleToggleStage = () => {
    setStageEnabled((prev) => {
      const next = !prev
      writeStagePreference(next)
      return next
    })
  }

  return (
    <div className="game-panel" aria-label={regionLabel}>
      {stageEnabled && backgroundUrl ? (
        <div className="game-stage-bg" aria-hidden="true" style={{ backgroundImage: `url("${backgroundUrl}")` }} />
      ) : null}

      <div className="game-stage-content">
      {state.phase === 'ready' && hasArt ? (
        <div className="game-stage-toggle">
          <button type="button" aria-pressed={stageEnabled} onClick={handleToggleStage}>
            {stageEnabled ? t('game.stage.hide') : t('game.stage.show')}
          </button>
        </div>
      ) : null}

      {stageEnabled && visibleSprites.length > 0 ? (
        <div className="game-stage-sprites">
          {visibleSprites.map((sprite) => (
            <img
              key={sprite.character}
              src={sprite.url}
              alt={t('game.sprite.alt', { character: sprite.character, emotion: sprite.emotion })}
              loading="lazy"
              decoding="async"
              onError={() => setBrokenSpriteUrls((prev) => new Set(prev).add(sprite.url))}
            />
          ))}
        </div>
      ) : null}

      <Hud hud={hudView} busy={turnPhase === 'streaming'} stale={hudStale} />
      <CastRow cast={castView} busy={turnPhase === 'streaming'} stale={hudStale} />

      {state.phase === 'loading' ? (
        <div className="game-history game-history--skeleton" aria-hidden="true">
          <div className="game-skeleton-block" />
          <div className="game-skeleton-block" />
        </div>
      ) : null}
      {state.phase === 'loading' ? <Loading label={t('game.loading')} visuallyHidden /> : null}

      {state.phase === 'notFound' ? <ErrorState title={t('game.notFound.title')} body={t('game.notFound.body')} /> : null}

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
                  <ErrorState title={pending.title} body={pending.body} />
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

      <p className="visually-hidden" aria-live="polite" role="status">
        {[sceneAnnouncement, castAnnouncement].filter(Boolean).join(' ')}
      </p>

      {state.phase === 'ready' && !atBottom ? (
        <button type="button" className="game-scrollLatest game-scrollLatest--floating" onClick={jumpToLatest}>
          {t('game.scrollToLatest')}
        </button>
      ) : null}

      {state.phase === 'ready' ? (
        <form className="game-footer" onSubmit={handleFormSubmit}>
          <label htmlFor={inputId_} className="visually-hidden">
            {t('game.input.label')}
          </label>
          <textarea
            id={inputId_}
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
      </div>
    </div>
  )
}
