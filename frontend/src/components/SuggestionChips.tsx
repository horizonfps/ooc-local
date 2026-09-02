import { t } from '../i18n'
import './suggestions.css'

const MAX_CHIPS = 3

export function SuggestionChips(props: { suggestions: string[]; onSend: (text: string) => void; onEdit: (text: string) => void }) {
  const { suggestions, onSend, onEdit } = props
  const visible = suggestions.filter((s) => s.trim() !== '').slice(0, MAX_CHIPS)

  if (visible.length === 0) return null

  return (
    <div className="suggestions" role="group" aria-label={t('game.suggest.regionLabel')}>
      <ul className="suggestions__list">
        {visible.map((text, i) => (
          <li key={i} className="suggestions__item">
            <button type="button" className="suggestions__chip" aria-label={t('game.suggest.send.aria', { text })} onClick={() => onSend(text)}>
              {text}
            </button>
            <button type="button" className="suggestions__edit" aria-label={t('game.suggest.edit.aria', { text })} onClick={() => onEdit(text)}>
              {t('game.suggest.edit')}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
