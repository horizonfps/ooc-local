import { t } from '../i18n'
import type { InputMode } from '../api'
import './modeSelector.css'

const MODES: InputMode[] = ['do', 'say', 'story']

export function ModeSelector(props: { value: InputMode; onChange: (mode: InputMode) => void; name: string; disabled?: boolean }) {
  const { value, onChange, name, disabled = false } = props
  const hintId = `${name}-hint`

  return (
    <div className="modeSelector">
      <div className="modeSelector__group" role="radiogroup" aria-label={t('game.mode.regionLabel')} aria-describedby={hintId}>
        {MODES.map((mode) => {
          const inputId = `${name}-${mode}`
          const labelClass = value === mode ? 'modeSelector__label modeSelector__label--active' : 'modeSelector__label'
          return (
            <span key={mode} className="modeSelector__option">
              <input
                type="radio"
                className="visually-hidden"
                id={inputId}
                name={name}
                value={mode}
                checked={value === mode}
                disabled={disabled}
                onChange={() => onChange(mode)}
              />
              <label htmlFor={inputId} className={labelClass}>
                {t(`game.mode.${mode}`)}
              </label>
            </span>
          )
        })}
      </div>
      <p id={hintId} className="modeSelector__hint">
        {t(`game.mode.${value}.hint`)}
      </p>
    </div>
  )
}
