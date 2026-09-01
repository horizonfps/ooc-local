import { t } from '../i18n'
import type { CastMember } from '../api'
import './cast.css'

export function CastRow(props: { cast: CastMember[] | null; busy?: boolean; stale?: boolean }) {
  const { cast, busy = false, stale = false } = props

  const className = stale ? 'cast cast--stale' : 'cast'

  return (
    <div className={className} role="group" aria-label={t('game.cast.regionLabel')} aria-busy={busy}>
      <span className="cast__label" aria-hidden="true">
        {t('game.cast.label')}
      </span>
      {cast === null ? (
        <span className="cast__chip" title={t('game.cast.unavailable')}>
          {t('hud.placeholder')}
        </span>
      ) : cast.length === 0 ? (
        <span className="cast__chip cast__chip--empty">{t('game.cast.empty')}</span>
      ) : (
        cast.map((member) => {
          const name = member.name || member.id
          return (
            <span key={member.id} className="cast__chip" title={name}>
              {name}
            </span>
          )
        })
      )}
    </div>
  )
}
