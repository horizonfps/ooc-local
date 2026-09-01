import { useCallback, useEffect, useRef, useState } from 'react'
import { GamePanel } from '../components/GamePanel'
import type { SessionDetail } from '../api'
import { t } from '../i18n'
import { navigate } from '../useHashRoute'
import './game.css'

export function GameScreen(props: { sessionId: string }) {
  const { sessionId } = props
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [scenarioName, setScenarioName] = useState('')
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    setScenarioName('')
    setNotFound(false)
  }, [sessionId])

  useEffect(() => {
    headingRef.current?.focus()
  }, [sessionId])

  useEffect(() => {
    if (!scenarioName) return
    const previousTitle = document.title
    document.title = t('game.documentTitle', { scenario: scenarioName })
    return () => {
      document.title = previousTitle
    }
  }, [scenarioName])

  const handleNotFound = useCallback(() => setNotFound(true), [])
  const handleSessionLoaded = useCallback((session: SessionDetail) => setScenarioName(session.scenarioName), [])

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

      <GamePanel sessionId={sessionId} onNotFound={handleNotFound} onSessionLoaded={handleSessionLoaded} autoFocusInput={false} />

      {notFound ? (
        <div className="game-notFound-back">
          <button type="button" onClick={() => navigate('#/')}>
            {t('common.back')}
          </button>
        </div>
      ) : null}
    </main>
  )
}
