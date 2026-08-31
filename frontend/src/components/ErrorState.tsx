import { t } from '../i18n'
import './states.css'

export function ErrorState(props: { title: string; body: string; cause?: string; onRetry?: () => void }) {
  return (
    <div className="state state-error">
      <p className="state-title">{props.title}</p>
      <p className="state-body">{props.body}</p>
      {props.cause ? (
        <details className="state-cause">
          <summary>{t('common.details')}</summary>
          <p>{props.cause}</p>
        </details>
      ) : null}
      {props.onRetry ? (
        <button type="button" onClick={props.onRetry}>
          {t('common.retry')}
        </button>
      ) : null}
    </div>
  )
}
