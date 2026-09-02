import { useEffect, useRef, useState } from 'react'
import type { TabProps } from '../../screens/BuilderEditorScreen'
import type { StatDef, StatLevel } from '../../api'
import { t } from '../../i18n'
import { EmptyState } from '../EmptyState'
import '../../screens/builderEditor.css'

function nextSuggestedStatId(existing: readonly string[]): string {
  let n = 1
  while (existing.includes(`stat-${n}`)) n += 1
  return `stat-${n}`
}

function newStat(id: string): StatDef {
  return { id, name: '', icon: null, color: null, min: 0, max: 100, default: 50, description: null, levels: [] }
}

function IntegerField(props: {
  id: string
  label: string
  hint?: string
  hintId?: string
  value: number
  pending: string | undefined
  error: string | null
  onChangeRaw: (raw: string) => void
  onBlur: () => void
  className?: string
}) {
  const { id, label, hint, hintId, value, pending, error, onChangeRaw, onBlur, className } = props
  const message = pending !== undefined ? t('builder.validate.integerRequired') : error
  const errorId = `${id}-error`
  return (
    <div className={['builder-field', className].filter(Boolean).join(' ')}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        step={1}
        inputMode="numeric"
        value={pending ?? String(value)}
        onChange={(e) => onChangeRaw(e.target.value)}
        onBlur={onBlur}
        aria-invalid={message ? 'true' : undefined}
        aria-describedby={[message ? errorId : null, hintId].filter(Boolean).join(' ') || undefined}
      />
      {hint ? (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      {message ? (
        <p role="alert" id={errorId} className="field-error">
          {message}
        </p>
      ) : null}
    </div>
  )
}

export function StatsTab(props: TabProps) {
  const { draft, onChange, errors } = props

  const [selectedIndex, setSelectedIndex] = useState<number>(() => {
    const withError = draft.stats.findIndex((_, i) => errors.some((e) => e.tab === 'stats' && e.field.startsWith(`stats.${i}.`)))
    return withError >= 0 ? withError : 0
  })
  const [announcement, setAnnouncement] = useState('')
  const [pendingNumbers, setPendingNumbers] = useState<Record<string, string>>({})

  const createTriggerRef = useRef<HTMLButtonElement>(null)
  const addLevelButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (selectedIndex > draft.stats.length - 1) {
      setSelectedIndex(Math.max(0, draft.stats.length - 1))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.stats.length])

  function fieldError(field: string): string | null {
    return errors.find((e) => e.tab === 'stats' && e.field === field)?.message ?? null
  }

  function statHasError(i: number): boolean {
    return errors.some((e) => e.tab === 'stats' && e.field.startsWith(`stats.${i}.`))
  }

  function statLabelOf(stat: StatDef): string {
    return stat.name || stat.id || t('builder.stats.unnamed')
  }

  function updateStat(index: number, patch: Partial<StatDef>) {
    onChange({ ...draft, stats: draft.stats.map((stat, i) => (i === index ? { ...stat, ...patch } : stat)) })
  }

  function updateLevel(index: number, levelIndex: number, patch: Partial<StatLevel>) {
    const stat = draft.stats[index]
    const nextLevels = stat.levels.map((level, i) => (i === levelIndex ? { ...level, ...patch } : level))
    updateStat(index, { levels: nextLevels })
  }

  function commitNumber(field: string, raw: string, commit: (n: number) => void) {
    if (/^-?\d+$/.test(raw)) {
      commit(Number(raw))
      setPendingNumbers((prev) => {
        if (!(field in prev)) return prev
        const next = { ...prev }
        delete next[field]
        return next
      })
    } else {
      setPendingNumbers((prev) => ({ ...prev, [field]: raw }))
    }
  }

  function clearPending(field: string) {
    setPendingNumbers((prev) => {
      if (!(field in prev)) return prev
      const next = { ...prev }
      delete next[field]
      return next
    })
  }

  function selectStat(index: number) {
    if (index === selectedIndex) return
    setSelectedIndex(index)
    setAnnouncement(t('builder.detail.selected', { name: statLabelOf(draft.stats[index]) }))
    requestAnimationFrame(() => {
      document.getElementById(`builder-field-stats.${index}.name`)?.focus()
    })
  }

  function createStat() {
    const id = nextSuggestedStatId(draft.stats.map((s) => s.id))
    const newIndex = draft.stats.length
    onChange({ ...draft, stats: [...draft.stats, newStat(id)] })
    setSelectedIndex(newIndex)
    setAnnouncement(t('builder.stats.added', { id }))
    requestAnimationFrame(() => {
      document.getElementById(`builder-field-stats.${newIndex}.name`)?.focus()
    })
  }

  function removeStat(index: number) {
    const removedName = statLabelOf(draft.stats[index])
    const nextStats = draft.stats.filter((_, i) => i !== index)
    onChange({ ...draft, stats: nextStats })
    setAnnouncement(t('builder.stats.removed', { name: removedName }))
    if (nextStats.length === 0) {
      setSelectedIndex(0)
      requestAnimationFrame(() => createTriggerRef.current?.focus())
      return
    }
    const focusIndex = index < nextStats.length ? index : nextStats.length - 1
    setSelectedIndex(focusIndex)
    requestAnimationFrame(() => {
      document.getElementById(`builder-stats-listItem-${focusIndex}`)?.focus()
    })
  }

  function addLevel() {
    const stat = draft.stats[selectedIndex]
    const lastFrom = stat.levels.length > 0 ? stat.levels[stat.levels.length - 1].from : null
    const from = lastFrom === null ? stat.min : Math.min(lastFrom + 1, stat.max)
    const newIndex = stat.levels.length
    updateStat(selectedIndex, { levels: [...stat.levels, { from, text: '' }] })
    setAnnouncement(t('builder.stats.levels.added', { index: newIndex + 1 }))
    requestAnimationFrame(() => {
      document.getElementById(`builder-field-stats.${selectedIndex}.levels.${newIndex}.text`)?.focus()
    })
  }

  function removeLevel(levelIndex: number) {
    const stat = draft.stats[selectedIndex]
    const nextLevels = stat.levels.filter((_, i) => i !== levelIndex)
    updateStat(selectedIndex, { levels: nextLevels })
    setAnnouncement(t('builder.stats.levels.removed', { index: levelIndex + 1 }))
    requestAnimationFrame(() => {
      if (nextLevels.length === 0) {
        addLevelButtonRef.current?.focus()
        return
      }
      const focusIndex = levelIndex < nextLevels.length ? levelIndex : nextLevels.length - 1
      document.getElementById(`builder-field-stats.${selectedIndex}.levels.${focusIndex}.text`)?.focus()
    })
  }

  const selectedStat: StatDef | undefined = draft.stats[selectedIndex]

  return (
    <div className="builder-stats-tab">
      <h2>{t('builder.stats.heading')}</h2>

      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>

      <div className="builder-field">
        <label>
          <input
            type="checkbox"
            checked={draft.meta.allow_dynamic_stats}
            onChange={(e) => onChange({ ...draft, meta: { ...draft.meta, allow_dynamic_stats: e.target.checked } })}
          />
          {t('builder.stats.allowDynamic')}
        </label>
        <p className="field-hint">{t('builder.stats.allowDynamic.hint')}</p>
      </div>

      {draft.stats.length === 0 ? (
        <EmptyState
          title={t('builder.stats.empty.title')}
          body={t('builder.stats.empty.body')}
          action={
            <button type="button" ref={createTriggerRef} onClick={createStat}>
              {t('builder.stats.create')}
            </button>
          }
        />
      ) : (
        <div className="builder-masterDetail">
          <div className="builder-stats-list">
            <p id="builder-stats-listLabel" className="builder-list-label">
              {t('builder.stats.listLabel')}
            </p>
            <p className="field-hint">{t('builder.stats.orderHint')}</p>
            <ul className="builder-list" aria-labelledby="builder-stats-listLabel">
              {draft.stats.map((stat, i) => {
                const hasError = statHasError(i)
                return (
                  <li key={i} className={[i === selectedIndex ? 'is-selected' : '', hasError ? 'is-invalid' : ''].filter(Boolean).join(' ')}>
                    <button
                      type="button"
                      id={`builder-stats-listItem-${i}`}
                      className="builder-list-item"
                      aria-current={i === selectedIndex || undefined}
                      onClick={() => selectStat(i)}
                    >
                      {stat.icon ? <span aria-hidden="true">{stat.icon}</span> : null}
                      <span className="builder-stats-listItemText">
                        <span>{statLabelOf(stat)}</span>
                        <span className="field-hint">
                          {t('builder.stats.itemMeta', { min: stat.min, max: stat.max, default: stat.default })}
                        </span>
                      </span>
                      {stat.levels.length > 0 ? (
                        <span className="builder-starts-badge">
                          {stat.levels.length === 1
                            ? t('builder.stats.levelsBadgeOne')
                            : t('builder.stats.levelsBadgeOther', { count: stat.levels.length })}
                        </span>
                      ) : null}
                      {hasError ? <span className="visually-hidden">{t('builder.starts.itemInvalid')}</span> : null}
                    </button>
                    <button
                      type="button"
                      aria-label={t('builder.stats.remove.title', { name: statLabelOf(stat) })}
                      onClick={() => removeStat(i)}
                    >
                      {t('common.remove')}
                    </button>
                  </li>
                )
              })}
            </ul>
            <button type="button" ref={createTriggerRef} onClick={createStat}>
              {t('builder.stats.create')}
            </button>
          </div>

          {selectedStat ? (
            <div className="builder-stats-detail">
              <div className="builder-field">
                <label htmlFor={`builder-field-stats.${selectedIndex}.id`}>{t('builder.stats.id')}</label>
                <input
                  id={`builder-field-stats.${selectedIndex}.id`}
                  value={selectedStat.id}
                  onChange={(e) => updateStat(selectedIndex, { id: e.target.value })}
                  onBlur={(e) => updateStat(selectedIndex, { id: e.target.value.trim() })}
                  aria-invalid={fieldError(`stats.${selectedIndex}.id`) ? 'true' : undefined}
                  aria-describedby={
                    [
                      fieldError(`stats.${selectedIndex}.id`) ? `builder-field-stats.${selectedIndex}.id-error` : null,
                      `builder-field-stats.${selectedIndex}.id-hint`,
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                />
                <p className="field-hint" id={`builder-field-stats.${selectedIndex}.id-hint`}>
                  {t('builder.stats.id.hint')}
                </p>
                {fieldError(`stats.${selectedIndex}.id`) ? (
                  <p role="alert" id={`builder-field-stats.${selectedIndex}.id-error`} className="field-error">
                    {fieldError(`stats.${selectedIndex}.id`)}
                  </p>
                ) : null}
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-stats.${selectedIndex}.name`}>{t('builder.stats.name')}</label>
                <input
                  id={`builder-field-stats.${selectedIndex}.name`}
                  value={selectedStat.name}
                  onChange={(e) => updateStat(selectedIndex, { name: e.target.value })}
                  onBlur={(e) => updateStat(selectedIndex, { name: e.target.value.trim() })}
                  aria-invalid={fieldError(`stats.${selectedIndex}.name`) ? 'true' : undefined}
                  aria-describedby={
                    fieldError(`stats.${selectedIndex}.name`) ? `builder-field-stats.${selectedIndex}.name-error` : undefined
                  }
                />
                {fieldError(`stats.${selectedIndex}.name`) ? (
                  <p role="alert" id={`builder-field-stats.${selectedIndex}.name-error`} className="field-error">
                    {fieldError(`stats.${selectedIndex}.name`)}
                  </p>
                ) : null}
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-stats.${selectedIndex}.icon`}>{t('builder.stats.icon')}</label>
                <input
                  id={`builder-field-stats.${selectedIndex}.icon`}
                  value={selectedStat.icon ?? ''}
                  onChange={(e) =>
                    updateStat(selectedIndex, { icon: e.target.value.trim() === '' ? null : e.target.value.trim() })
                  }
                  aria-invalid={fieldError(`stats.${selectedIndex}.icon`) ? 'true' : undefined}
                  aria-describedby={
                    [
                      fieldError(`stats.${selectedIndex}.icon`) ? `builder-field-stats.${selectedIndex}.icon-error` : null,
                      `builder-field-stats.${selectedIndex}.icon-hint`,
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                />
                <p className="field-hint" id={`builder-field-stats.${selectedIndex}.icon-hint`}>
                  {t('builder.stats.icon.hint')}
                </p>
                {fieldError(`stats.${selectedIndex}.icon`) ? (
                  <p role="alert" id={`builder-field-stats.${selectedIndex}.icon-error`} className="field-error">
                    {fieldError(`stats.${selectedIndex}.icon`)}
                  </p>
                ) : null}
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-stats.${selectedIndex}.color`}>{t('builder.stats.color')}</label>
                <input
                  id={`builder-field-stats.${selectedIndex}.color`}
                  value={selectedStat.color ?? ''}
                  onChange={(e) => updateStat(selectedIndex, { color: e.target.value })}
                  onBlur={(e) => {
                    const trimmed = e.target.value.trim()
                    updateStat(selectedIndex, { color: trimmed === '' ? null : trimmed })
                  }}
                  aria-invalid={fieldError(`stats.${selectedIndex}.color`) ? 'true' : undefined}
                  aria-describedby={
                    [
                      fieldError(`stats.${selectedIndex}.color`) ? `builder-field-stats.${selectedIndex}.color-error` : null,
                      `builder-field-stats.${selectedIndex}.color-hint`,
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                />
                <p className="field-hint" id={`builder-field-stats.${selectedIndex}.color-hint`}>
                  {t('builder.stats.color.hint')}
                </p>
                {fieldError(`stats.${selectedIndex}.color`) ? (
                  <p role="alert" id={`builder-field-stats.${selectedIndex}.color-error`} className="field-error">
                    {fieldError(`stats.${selectedIndex}.color`)}
                  </p>
                ) : null}
              </div>

              <div className="builder-stats-numberRow">
                <IntegerField
                  id={`builder-field-stats.${selectedIndex}.min`}
                  label={t('builder.stats.min')}
                  value={selectedStat.min}
                  pending={pendingNumbers[`stats.${selectedIndex}.min`]}
                  error={fieldError(`stats.${selectedIndex}.min`)}
                  onChangeRaw={(raw) =>
                    commitNumber(`stats.${selectedIndex}.min`, raw, (n) => updateStat(selectedIndex, { min: n }))
                  }
                  onBlur={() => clearPending(`stats.${selectedIndex}.min`)}
                />
                <IntegerField
                  id={`builder-field-stats.${selectedIndex}.max`}
                  label={t('builder.stats.max')}
                  value={selectedStat.max}
                  pending={pendingNumbers[`stats.${selectedIndex}.max`]}
                  error={fieldError(`stats.${selectedIndex}.max`)}
                  onChangeRaw={(raw) =>
                    commitNumber(`stats.${selectedIndex}.max`, raw, (n) => updateStat(selectedIndex, { max: n }))
                  }
                  onBlur={() => clearPending(`stats.${selectedIndex}.max`)}
                />
                <IntegerField
                  id={`builder-field-stats.${selectedIndex}.default`}
                  label={t('builder.stats.default')}
                  hint={t('builder.stats.default.hint')}
                  hintId={`builder-field-stats.${selectedIndex}.default-hint`}
                  value={selectedStat.default}
                  pending={pendingNumbers[`stats.${selectedIndex}.default`]}
                  error={fieldError(`stats.${selectedIndex}.default`)}
                  onChangeRaw={(raw) =>
                    commitNumber(`stats.${selectedIndex}.default`, raw, (n) => updateStat(selectedIndex, { default: n }))
                  }
                  onBlur={() => clearPending(`stats.${selectedIndex}.default`)}
                />
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-stats.${selectedIndex}.description`}>{t('builder.stats.description')}</label>
                <textarea
                  id={`builder-field-stats.${selectedIndex}.description`}
                  className="builder-field-textarea"
                  rows={3}
                  value={selectedStat.description ?? ''}
                  onChange={(e) =>
                    updateStat(selectedIndex, { description: e.target.value.trim() === '' ? null : e.target.value })
                  }
                  aria-invalid={fieldError(`stats.${selectedIndex}.description`) ? 'true' : undefined}
                  aria-describedby={
                    [
                      fieldError(`stats.${selectedIndex}.description`)
                        ? `builder-field-stats.${selectedIndex}.description-error`
                        : null,
                      `builder-field-stats.${selectedIndex}.description-hint`,
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                />
                <p className="field-hint" id={`builder-field-stats.${selectedIndex}.description-hint`}>
                  {t('builder.stats.description.hint')}
                </p>
                {fieldError(`stats.${selectedIndex}.description`) ? (
                  <p role="alert" id={`builder-field-stats.${selectedIndex}.description-error`} className="field-error">
                    {fieldError(`stats.${selectedIndex}.description`)}
                  </p>
                ) : null}
              </div>

              <fieldset className="builder-field builder-stats-levels">
                <legend>{t('builder.stats.levels.legend')}</legend>
                <p className="field-hint">{t('builder.stats.levels.hint')}</p>
                {selectedStat.levels.length === 0 ? (
                  <p className="field-hint">{t('builder.stats.levels.empty')}</p>
                ) : (
                  selectedStat.levels.map((level, j) => {
                    const fromField = `stats.${selectedIndex}.levels.${j}.from`
                    const textField = `stats.${selectedIndex}.levels.${j}.text`
                    const textError = fieldError(textField)
                    const textErrorId = `builder-field-${textField}-error`
                    return (
                      <div className="builder-stats-levelRow" key={j}>
                        <IntegerField
                          id={`builder-field-${fromField}`}
                          className="builder-stats-levelFrom"
                          label={t('builder.stats.levels.from', { index: j + 1 })}
                          value={level.from}
                          pending={pendingNumbers[fromField]}
                          error={fieldError(fromField)}
                          onChangeRaw={(raw) => commitNumber(fromField, raw, (n) => updateLevel(selectedIndex, j, { from: n }))}
                          onBlur={() => clearPending(fromField)}
                        />
                        <div className="builder-field builder-stats-levelText">
                          <label htmlFor={`builder-field-${textField}`}>{t('builder.stats.levels.text', { index: j + 1 })}</label>
                          <input
                            id={`builder-field-${textField}`}
                            value={level.text}
                            onChange={(e) => updateLevel(selectedIndex, j, { text: e.target.value })}
                            aria-invalid={textError ? 'true' : undefined}
                            aria-describedby={textError ? textErrorId : undefined}
                          />
                          {textError ? (
                            <p role="alert" id={textErrorId} className="field-error">
                              {textError}
                            </p>
                          ) : null}
                        </div>
                        <button
                          type="button"
                          className="builder-stats-levelRemove"
                          aria-label={t('builder.stats.levels.remove', { index: j + 1 })}
                          onClick={() => removeLevel(j)}
                        >
                          {t('common.remove')}
                        </button>
                      </div>
                    )
                  })
                )}
                <button type="button" ref={addLevelButtonRef} onClick={addLevel}>
                  {t('builder.stats.levels.add')}
                </button>
              </fieldset>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
