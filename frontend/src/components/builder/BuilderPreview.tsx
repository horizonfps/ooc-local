import { useEffect, useRef, useState } from 'react'
import { GamePanel } from '../GamePanel'
import { EmptyState } from '../EmptyState'
import { ErrorState } from '../ErrorState'
import { Loading } from '../Loading'
import { createSession, deleteSession } from '../../api'
import { t } from '../../i18n'
import type { BuilderDraft } from '../../screens/BuilderEditorScreen'
import '../../screens/builderEditor.css'

export type BuilderPreviewProps = {
  scenarioId: string
  draft: BuilderDraft
  loadedStartIds: string[]
  dirty: boolean
  savedAt: number | null
  invalidReason?: string
  onSave: () => Promise<void>
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'starting' }
  | { kind: 'ready'; sessionId: string; createdAt: number }
  | { kind: 'error' }

function defaultStartId(draft: BuilderDraft): string {
  const ids = Object.keys(draft.starts)
  if (draft.meta.default_start in draft.starts) return draft.meta.default_start
  return ids[0] ?? ''
}

async function discard(id: string) {
  try {
    await deleteSession(id)
  } catch {
    // best-effort: the backend sweeps ephemeral sessions on boot
  }
}

export function BuilderPreview(props: BuilderPreviewProps) {
  const { scenarioId, draft, loadedStartIds, dirty, savedAt, invalidReason, onSave } = props

  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [selectedStartId, setSelectedStartId] = useState<string>(() => defaultStartId(draft))
  const [turnsPlayed, setTurnsPlayed] = useState(0)
  const [announcement, setAnnouncement] = useState('')
  const [restartConfirmOpen, setRestartConfirmOpen] = useState(false)
  const [switchTarget, setSwitchTarget] = useState<string | null>(null)
  const [focusToken, setFocusToken] = useState(0)

  const sessionIdRef = useRef<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const restartDialogRef = useRef<HTMLDialogElement>(null)
  const restartCancelRef = useRef<HTMLButtonElement>(null)
  const switchDialogRef = useRef<HTMLDialogElement>(null)
  const switchCancelRef = useRef<HTMLButtonElement>(null)

  const startIds = Object.keys(draft.starts)

  useEffect(() => {
    if (!(selectedStartId in draft.starts)) {
      setSelectedStartId(startIds[0] ?? '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.starts])

  const isFirstScenario = useRef(true)
  useEffect(() => {
    if (isFirstScenario.current) {
      isFirstScenario.current = false
      return
    }
    const current = sessionIdRef.current
    sessionIdRef.current = null
    if (current) void discard(current)
    setPhase({ kind: 'idle' })
    setTurnsPlayed(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId])

  useEffect(() => {
    function handleBeforeUnload() {
      const current = sessionIdRef.current
      if (current) void deleteSession(current, { keepalive: true }).catch(() => {})
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
      const current = sessionIdRef.current
      if (current) void deleteSession(current, { keepalive: true }).catch(() => {})
    }
  }, [])

  useEffect(() => {
    if (restartConfirmOpen) {
      restartDialogRef.current?.showModal()
      restartCancelRef.current?.focus()
    } else {
      restartDialogRef.current?.close()
    }
  }, [restartConfirmOpen])

  useEffect(() => {
    if (switchTarget !== null) {
      switchDialogRef.current?.showModal()
      switchCancelRef.current?.focus()
    } else {
      switchDialogRef.current?.close()
    }
  }, [switchTarget])

  useEffect(() => {
    if (focusToken === 0) return
    headingRef.current?.focus()
  }, [focusToken])

  async function startSession(startId: string) {
    setPhase({ kind: 'starting' })
    try {
      const session = await createSession(scenarioId, { startId, ephemeral: true })
      sessionIdRef.current = session.id
      setPhase({ kind: 'ready', sessionId: session.id, createdAt: Date.now() })
      setTurnsPlayed(0)
      setFocusToken((n) => n + 1)
    } catch {
      sessionIdRef.current = null
      setPhase({ kind: 'error' })
    }
  }

  async function discardAndStart(startId: string) {
    const current = sessionIdRef.current
    sessionIdRef.current = null
    if (current) await discard(current)
    await startSession(startId)
  }

  async function restartTo(startId: string) {
    await discardAndStart(startId)
    setAnnouncement(t('builder.preview.restarted'))
  }

  function handleStart() {
    if (invalidReason) return
    void startSession(selectedStartId)
  }

  function handleRetry() {
    void startSession(selectedStartId)
  }

  function handleRestartClick() {
    if (phase.kind !== 'ready') return
    if (turnsPlayed > 0) {
      setRestartConfirmOpen(true)
      return
    }
    void restartTo(selectedStartId)
  }

  function handleRestartConfirm() {
    setRestartConfirmOpen(false)
    void restartTo(selectedStartId)
  }

  async function handleSaveAndRestart() {
    try {
      await onSave()
    } catch {
      return
    }
    await restartTo(selectedStartId)
  }

  function handleOutdatedRestart() {
    void restartTo(selectedStartId)
  }

  function handleStartChange(nextId: string) {
    if (phase.kind !== 'ready') {
      setSelectedStartId(nextId)
      return
    }
    if (turnsPlayed > 0) {
      setSwitchTarget(nextId)
      return
    }
    setSelectedStartId(nextId)
    void restartTo(nextId)
  }

  function closeSwitchConfirm() {
    setSwitchTarget(null)
  }

  function handleSwitchConfirm() {
    if (switchTarget === null) return
    const nextId = switchTarget
    setSwitchTarget(null)
    setSelectedStartId(nextId)
    void restartTo(nextId)
  }

  const selectedStartIsLoaded = loadedStartIds.includes(selectedStartId)
  const switchTargetName = switchTarget !== null ? draft.starts[switchTarget]?.name || switchTarget : ''
  const showOutdated = phase.kind === 'ready' && !dirty && savedAt !== null && savedAt > phase.createdAt

  return (
    <div className="builder-preview">
      <div className="builder-preview-header">
        <h2 ref={headingRef} tabIndex={-1}>
          {t('builder.preview.heading')}
        </h2>
        <p className="builder-preview-ephemeralHint">{t('builder.preview.ephemeralHint')}</p>

        {startIds.length > 0 ? (
          <div className="builder-preview-startPicker">
            <label htmlFor="builder-preview-start">{t('builder.preview.startLabel')}</label>
            <select
              id="builder-preview-start"
              value={selectedStartId}
              onChange={(e) => handleStartChange(e.target.value)}
            >
              {startIds.map((id) => (
                <option key={id} value={id} disabled={!loadedStartIds.includes(id)}>
                  {draft.starts[id].name || id}
                  {id === draft.meta.default_start ? ` (${t('builder.starts.defaultBadge')})` : ''}
                </option>
              ))}
            </select>
            {!selectedStartIsLoaded ? <p className="builder-preview-hint">{t('builder.preview.startUnsaved')}</p> : null}
          </div>
        ) : null}

        {dirty ? (
          <div className="builder-preview-warning" role="status">
            <p>{t('builder.preview.stale')}</p>
            {phase.kind === 'ready' ? (
              <div className="builder-preview-warning-actions">
                <button type="button" onClick={() => void handleSaveAndRestart()}>
                  {t('builder.preview.saveAndRestart')}
                </button>
                <button type="button" onClick={handleRestartClick}>
                  {t('builder.preview.restart')}
                </button>
              </div>
            ) : null}
          </div>
        ) : showOutdated ? (
          <div className="builder-preview-warning" role="status">
            <p>{t('builder.preview.outdated')}</p>
            <div className="builder-preview-warning-actions">
              <button type="button" onClick={handleOutdatedRestart}>
                {t('builder.preview.restart')}
              </button>
            </div>
          </div>
        ) : null}

        {phase.kind === 'ready' ? (
          <button type="button" className="builder-preview-restart" onClick={handleRestartClick}>
            {t('builder.preview.restart')}
          </button>
        ) : null}
      </div>

      <p role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </p>

      <div className="builder-preview-body">
        {invalidReason ? (
          <ErrorState title={t('builder.preview.invalid.title')} body={t('builder.preview.invalid.body', { reason: invalidReason })} />
        ) : phase.kind === 'idle' ? (
          <EmptyState
            title={t('builder.preview.idle.title')}
            body={t('builder.preview.idle.body')}
            action={
              <button type="button" onClick={handleStart} disabled={!selectedStartIsLoaded || startIds.length === 0}>
                {t('builder.preview.start')}
              </button>
            }
          />
        ) : phase.kind === 'starting' ? (
          <>
            <div className="builder-skeleton-block" aria-hidden="true" />
            <div className="builder-skeleton-block" aria-hidden="true" />
            <Loading label={t('builder.preview.starting')} visuallyHidden />
          </>
        ) : phase.kind === 'error' ? (
          <ErrorState title={t('error.unexpected.title')} body={t('builder.preview.start.error')} onRetry={handleRetry} />
        ) : (
          <GamePanel
            sessionId={phase.sessionId}
            regionLabel={t('builder.preview.regionLabel')}
            onTurnsChanged={setTurnsPlayed}
          />
        )}
      </div>

      <dialog
        ref={restartDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-preview-restart-title"
        onClose={() => setRestartConfirmOpen(false)}
        onCancel={(event) => {
          event.preventDefault()
          setRestartConfirmOpen(false)
        }}
      >
        <h2 id="builder-preview-restart-title">{t('builder.preview.restart.title')}</h2>
        <p>{t('builder.preview.restart.body', { count: turnsPlayed })}</p>
        <div className="builder-editor-dialog-actions">
          <button type="button" ref={restartCancelRef} onClick={() => setRestartConfirmOpen(false)}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={handleRestartConfirm}>
            {t('builder.preview.restart.submit')}
          </button>
        </div>
      </dialog>

      <dialog
        ref={switchDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-preview-switchStart-title"
        onClose={closeSwitchConfirm}
        onCancel={(event) => {
          event.preventDefault()
          closeSwitchConfirm()
        }}
      >
        <h2 id="builder-preview-switchStart-title">{t('builder.preview.switchStart.title', { name: switchTargetName })}</h2>
        <p>{t('builder.preview.switchStart.body')}</p>
        <div className="builder-editor-dialog-actions">
          <button type="button" ref={switchCancelRef} onClick={closeSwitchConfirm}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={handleSwitchConfirm}>
            {t('builder.preview.switchStart.submit')}
          </button>
        </div>
      </dialog>
    </div>
  )
}
