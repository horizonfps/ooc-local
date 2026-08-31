import { useEffect, useRef, useState } from 'react'
import { t } from '../i18n'
import type { StringKey } from '../i18n'
import './hud.css'

export type HudView = {
  turn: number
  location?: string | null
  time: string
  weather?: string | null
}

export const WEATHER_KEYS: Record<string, StringKey> = {
  clear: 'hud.weather.clear',
  cloudy: 'hud.weather.cloudy',
  rain: 'hud.weather.rain',
  storm: 'hud.weather.storm',
  snow: 'hud.weather.snow',
  fog: 'hud.weather.fog',
  night: 'hud.weather.night',
}

const WEATHER_EMOJI: Record<string, string> = {
  clear: '☀️',
  cloudy: '☁️',
  rain: '🌧️',
  storm: '⛈️',
  snow: '❄️',
  fog: '🌫️',
  night: '🌙',
}

const HIGHLIGHT_MS = 600

type FieldKey = 'turn' | 'location' | 'time' | 'weather'
const FIELD_KEYS: FieldKey[] = ['turn', 'location', 'time', 'weather']

function textField(value?: string | null): { text: string; title?: string } {
  if (value) return { text: value, title: value }
  return { text: t('hud.placeholder'), title: t('hud.unavailable') }
}

function weatherField(weather?: string | null): { text: string; title?: string; emoji?: string } {
  if (weather && weather in WEATHER_KEYS) {
    return { text: t(WEATHER_KEYS[weather]), emoji: WEATHER_EMOJI[weather] }
  }
  return { text: t('hud.weather.unknown'), title: weather || undefined }
}

function fieldsEqual(a: HudView, b: HudView): Record<FieldKey, boolean> {
  return {
    turn: a.turn === b.turn,
    location: (a.location ?? null) === (b.location ?? null),
    time: a.time === b.time,
    weather: (a.weather ?? null) === (b.weather ?? null),
  }
}

export function Hud(props: { hud: HudView | null; busy?: boolean; stale?: boolean }) {
  const { hud, busy = false, stale = false } = props
  const prevRef = useRef<HudView | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [highlighted, setHighlighted] = useState<Set<FieldKey>>(new Set())

  useEffect(() => {
    const prev = prevRef.current
    prevRef.current = hud
    if (!hud || !prev) return
    const equal = fieldsEqual(hud, prev)
    const changed = FIELD_KEYS.filter((key) => !equal[key])
    if (changed.length === 0) return
    setHighlighted(new Set(changed))
    clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => setHighlighted(new Set()), HIGHLIGHT_MS)
  }, [hud])

  useEffect(() => () => clearTimeout(timeoutRef.current), [])

  const turnText = hud ? String(hud.turn) : t('hud.placeholder')
  const location = hud ? textField(hud.location) : textField(null)
  const time = hud ? { text: hud.time } : { text: t('hud.placeholder') }
  const weather = hud ? weatherField(hud.weather) : { text: t('hud.placeholder') }

  const announce = hud
    ? t('hud.announce', { turn: turnText, location: location.text, time: time.text, weather: weather.text })
    : ''

  const fieldClass = (key: FieldKey) =>
    highlighted.has(key) ? 'hud__field hud__field--highlight' : 'hud__field'

  return (
    <div className="hud" aria-live="polite" aria-atomic="true" aria-busy={busy}>
      <dl className="hud__grid">
        <div className={fieldClass('turn')} data-field="turn">
          <dt>{t('hud.turn')}</dt>
          <dd>{turnText}</dd>
        </div>
        <div className={fieldClass('location')} data-field="location">
          <dt>{t('hud.location')}</dt>
          <dd title={location.title}>{location.text}</dd>
        </div>
        <div className={fieldClass('time')} data-field="time">
          <dt>{t('hud.time')}</dt>
          <dd>{time.text}</dd>
        </div>
        <div className={fieldClass('weather')} data-field="weather">
          <dt>{t('hud.weather')}</dt>
          <dd title={weather.title}>
            {weather.emoji ? <span aria-hidden="true">{weather.emoji} </span> : null}
            {weather.text}
          </dd>
        </div>
      </dl>
      <span className="hud__sr-only">{announce}</span>
      {stale && <p className="hud__stale">{t('hud.stale')}</p>}
    </div>
  )
}
