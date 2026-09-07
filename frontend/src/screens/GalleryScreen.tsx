import { useEffect, useRef, useState } from 'react'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { Loading } from '../components/Loading'
import { classifyError, describeError } from '../errors'
import { intlLocale, t } from '../i18n'
import { navigate } from '../useHashRoute'
import { fetchGallery, type Gallery, type GalleryEntry } from '../api'
import '../components/achievements.css'
import './gallery.css'

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

const RARITIES = ['common', 'rare', 'epic', 'legendary'] as const
type Rarity = (typeof RARITIES)[number]

function rarityOf(rarity: string): Rarity {
  return (RARITIES as readonly string[]).includes(rarity) ? (rarity as Rarity) : 'common'
}

function rarityKey(rarity: string): 'game.rarity.common' | 'game.rarity.rare' | 'game.rarity.epic' | 'game.rarity.legendary' {
  return `game.rarity.${rarityOf(rarity)}` as const
}

type GalleryState =
  | { status: 'loading' }
  | { status: 'error'; error: unknown }
  | { status: 'notFound' }
  | { status: 'loaded'; gallery: Gallery }

function unlockedWhen(entry: GalleryEntry): string | null {
  const timestamp = entry.unlockedAt ? new Date(entry.unlockedAt).getTime() : NaN
  const when = Number.isFinite(timestamp) ? formatRelativeTime(entry.unlockedAt as string, intlLocale) : null
  if (entry.turn != null && when != null) return t('gallery.unlocked.when', { turn: entry.turn, when })
  if (when != null) return when
  return null
}

function GalleryEntryItem(props: { entry: GalleryEntry; elementId: string }) {
  const { entry, elementId } = props
  const when = entry.unlocked ? unlockedWhen(entry) : null
  return (
    <li id={elementId} className={`gallery-entry${entry.unlocked ? ' is-unlocked' : ''}`}>
      <span className={`gallery-entry-name game-rarity--${rarityOf(entry.rarity)}`}>
        {entry.unlocked ? entry.name : t('gallery.locked.name')}
      </span>
      {entry.unlocked ? null : <span className="visually-hidden">{t('gallery.locked.sr')}</span>}
      <span className="gallery-entry-rarity">{t(rarityKey(entry.rarity))}</span>
      {entry.unlocked ? (
        when != null ? <span className="gallery-entry-when">{when}</span> : null
      ) : (
        <span className="gallery-entry-hint">{entry.hint ? entry.hint : t('gallery.locked.noHint')}</span>
      )}
    </li>
  )
}

export function GalleryScreen(props: { scenarioId: string }) {
  const { scenarioId } = props
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [state, setState] = useState<GalleryState>({ status: 'loading' })

  const load = () => {
    setState({ status: 'loading' })
    fetchGallery(scenarioId)
      .then((gallery) => setState({ status: 'loaded', gallery }))
      .catch((error) => {
        if (classifyError(error).kind === 'notFound') {
          setState({ status: 'notFound' })
        } else {
          setState({ status: 'error', error })
        }
      })
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId])

  useEffect(() => {
    headingRef.current?.focus()
  }, [scenarioId])

  useEffect(() => {
    if (state.status !== 'loaded') return
    const previousTitle = document.title
    document.title = t('gallery.documentTitle', { scenario: state.gallery.scenarioName })
    return () => {
      document.title = previousTitle
    }
  }, [state])

  const error = state.status === 'error' ? describeError(state.error) : null
  const isEmpty = state.status === 'loaded' && state.gallery.starts.every((start) => start.achievements.length === 0 && start.endings.length === 0)

  return (
    <main className="gallery">
      <div className="gallery-topbar">
        <button type="button" className="gallery-back" onClick={() => navigate('#/')}>
          {t('gallery.back')}
        </button>
        <h1 ref={headingRef} tabIndex={-1}>
          {state.status === 'loaded' ? state.gallery.scenarioName : t('gallery.heading')}
        </h1>
      </div>

      {state.status === 'loading' ? (
        <>
          <ul className="gallery-skeleton" aria-hidden="true">
            <li />
            <li />
            <li />
          </ul>
          <Loading label={t('gallery.loading')} visuallyHidden />
        </>
      ) : null}

      {state.status === 'notFound' ? (
        <>
          <ErrorState title={t('gallery.notFound.title')} body={t('gallery.notFound.body')} />
          <div className="gallery-notFound-back">
            <button type="button" onClick={() => navigate('#/')}>
              {t('common.back')}
            </button>
          </div>
        </>
      ) : null}

      {error ? <ErrorState title={error.title} body={error.body} onRetry={load} /> : null}

      {state.status === 'loaded' && isEmpty ? (
        <EmptyState title={t('gallery.empty.title')} body={t('gallery.empty.body')} />
      ) : null}

      {state.status === 'loaded' && !isEmpty ? (
        <>
          <p className="gallery-progress">
            {t('gallery.progress', {
              achievements: state.gallery.totals.achievements,
              achievementsUnlocked: state.gallery.totals.achievementsUnlocked,
              endings: state.gallery.totals.endings,
              endingsUnlocked: state.gallery.totals.endingsUnlocked,
            })}
          </p>
          {state.gallery.starts.map((start) => (
            <section key={start.id} className="gallery-start">
              <h2>{start.name}</h2>
              <section className="gallery-section">
                <h3>{t('gallery.achievements.heading')}</h3>
                <ul>
                  {start.achievements.map((entry, index) => (
                    <GalleryEntryItem key={entry.id} entry={entry} elementId={`gallery-entry-${start.id}-achievements-${index}`} />
                  ))}
                </ul>
              </section>
              <section className="gallery-section">
                <h3>{t('gallery.endings.heading')}</h3>
                <ul>
                  {start.endings.map((entry, index) => (
                    <GalleryEntryItem key={entry.id} entry={entry} elementId={`gallery-entry-${start.id}-endings-${index}`} />
                  ))}
                </ul>
              </section>
            </section>
          ))}
        </>
      ) : null}
    </main>
  )
}
