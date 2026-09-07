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
  const bars = stats.filter((s) => s.kind !== 'item' && s.kind !== 'skill')
  const items = stats.filter((s) => s.kind === 'item' && s.value > 0)
  const skills = stats.filter((s) => s.kind === 'skill')

  function chipClass(id: string): string {
    return highlighted.has(id) ? 'statBars__chip statBars__chip--highlight' : 'statBars__chip'
  }

  return (
    <div className={className} role="group" aria-label={t('hud.stats.regionLabel')} aria-busy={busy}>
      {bars.length > 0 ? (
        <ul className="statBars__list">
          {bars.map((stat) => {
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
      ) : null}
      {items.length > 0 ? (
        <div className="statBars__group" role="group" aria-labelledby="statBars-items-heading">
          <p className="statBars__groupHeading" id="statBars-items-heading">
            {t('hud.items.heading')}
          </p>
          <ul className="statBars__chips">
            {items.map((stat) => (
              <li key={stat.id} data-stat={stat.id} className={chipClass(stat.id)}>
                <span className="statBars__chipName" title={stat.name}>
                  {stat.name}
                </span>
                <span className="statBars__chipValue">{t('hud.item.count', { value: stat.value })}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {skills.length > 0 ? (
        <div className="statBars__group" role="group" aria-labelledby="statBars-skills-heading">
          <p className="statBars__groupHeading" id="statBars-skills-heading">
            {t('hud.skills.heading')}
          </p>
          <ul className="statBars__chips">
            {skills.map((stat) => (
              <li key={stat.id} data-stat={stat.id} className={chipClass(stat.id)}>
                <span className="statBars__chipName" title={stat.name}>
                  {stat.name}
                </span>
                {stat.max > 1 ? (
                  <span className="statBars__chipValue">{t('hud.stat.value', { value: stat.value, max: stat.max })}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
