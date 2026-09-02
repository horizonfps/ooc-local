import { t } from '../i18n'
import type { CastMember, MindView } from '../api'
import './infoTracker.css'

export function InfoTracker(props: {
  minds: Record<string, MindView> | null
  cast: CastMember[] | null
  busy?: boolean
  stale?: boolean
}) {
  const { minds, cast, busy = false, stale = false } = props

  if (cast === null) return null

  const className = stale ? 'info info--stale' : 'info'
  const hasAnyMind = cast.length > 0 && cast.some((member) => minds != null && Object.prototype.hasOwnProperty.call(minds, member.id))

  return (
    <details className={className} open>
      <summary>{t('game.info.label')}</summary>
      <div className="info__body" role="group" aria-label={t('game.info.regionLabel')} aria-busy={busy}>
        {cast.length === 0 ? (
          <p className="info__empty">{t('game.cast.empty')}</p>
        ) : !hasAnyMind ? (
          <p className="info__pending">{t('game.info.pending')}</p>
        ) : (
          <ul className="info__list">
            {cast.map((member) => {
              const name = member.name || member.id
              const mind = minds != null && Object.prototype.hasOwnProperty.call(minds, member.id) ? minds[member.id] : undefined
              return (
                <li key={member.id} className="info__row">
                  <span className="info__emoji" aria-hidden="true">
                    {mind?.emoji ?? ''}
                  </span>
                  <div className="info__content">
                    <p className="info__line">
                      <span className="info__name">{name}</span>
                      {' · '}
                      <span className="info__attitude">{mind ? mind.attitude : t('game.info.unknown')}</span>
                    </p>
                    {mind && mind.event !== '' ? <p className="info__event">{t('game.info.event', { event: mind.event })}</p> : null}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </details>
  )
}
