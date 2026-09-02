import { useEffect, useRef, useState } from 'react'
import { t } from '../i18n'
import type { StatView } from '../api'
import './statBars.css'

const HIGHLIGHT_MS = 600

function fillPercent(value: number, min: number, max: number): number {
  if (max <= min) return 0
  const ratio = (value - min) / (max - min)
  return Math.max(0, Math.min(1, ratio)) * 100
}

export function StatBars(props: { stats: StatView[] | null; busy?: boolean; stale?: boolean }) {
  const { stats, busy = false, stale = false } = props
  const prevRef = useRef<StatView[] | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [highlighted, setHighlighted] = useState<Set<string>>(new Set())

  useEffect(() => {
    const prev = prevRef.current
    prevRef.current = stats
    if (!stats || !prev) return
    const prevById = new Map(prev.map((s) => [s.id, s.value]))
    const changed = stats.filter((s) => prevById.has(s.id) && prevById.get(s.id) !== s.value).map((s) => s.id)
    if (changed.length === 0) return
    setHighlighted(new Set(changed))
    clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => setHighlighted(new Set()), HIGHLIGHT_MS)
  }, [stats])

  useEffect(() => () => clearTimeout(timeoutRef.current), [])

  if (stats === null || stats.length === 0) return null

  const className = stale ? 'statBars statBars--stale' : 'statBars'

  return (
    <div className={className} role="group" aria-label={t('hud.stats.regionLabel')} aria-busy={busy}>
      <ul className="statBars__list">
        {stats.map((stat) => {
          const pct = fillPercent(stat.value, stat.min, stat.max)
          const itemClass = highlighted.has(stat.id) ? 'statBars__item statBars__item--highlight' : 'statBars__item'
          return (
            <li key={stat.id} className={itemClass} data-stat={stat.id}>
              <div className="statBars__header">
                <span className="statBars__icon" aria-hidden="true">
                  {stat.icon ?? ''}
                </span>
                <span className="statBars__name" title={stat.name}>
                  {stat.name}
                </span>
                <span className="statBars__value">{t('hud.stat.value', { value: stat.value, max: stat.max })}</span>
              </div>
              <div className="statBars__track" aria-hidden="true">
                <div className="statBars__fill" style={{ width: `${pct}%`, background: stat.color ?? undefined }} />
              </div>
              <div className="statBars__levelSlot">
                {stat.level !== null ? (
                  <span className="statBars__level" title={stat.level}>
                    {t('hud.stat.level', { level: stat.level })}
                  </span>
                ) : null}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
