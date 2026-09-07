import { useEffect, useRef, useState } from 'react'
import type { TabProps } from '../../screens/BuilderEditorScreen'
import type { AchievementDoc, StartDoc, StatGateDoc } from '../../api'
import { t } from '../../i18n'
import { EmptyState } from '../EmptyState'
import '../../screens/builderEditor.css'

function nextSuggestedAchievementId(existing: readonly string[]): string {
  let n = 1
  while (existing.includes(`conquista-${n}`)) n += 1
  return `conquista-${n}`
}

function newAchievement(id: string): AchievementDoc {
  return { id, name: '', type: 'achievement', rarity: 'common', hint: null, condition: '', min_turn: null, stat_gates: [] }
}

function OptionalIntegerField(props: {
  id: string
  label: string
  hint: string
  hintId: string
  value: number | null
  error: string | null
  onChange: (value: number | null) => void
}) {
  const { id, label, hint, hintId, value, error, onChange } = props
  const errorId = `${id}-error`
  return (
    <div className="builder-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        step={1}
        inputMode="numeric"
        value={value === null ? '' : String(value)}
        onChange={(e) => {
          const raw = e.target.value
          if (raw.trim() === '') {
            onChange(null)
          } else if (/^-?\d+$/.test(raw)) {
            onChange(Number(raw))
          }
        }}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={[error ? errorId : null, hintId].filter(Boolean).join(' ') || undefined}
      />
      <p className="field-hint" id={hintId}>
        {hint}
      </p>
      {error ? (
        <p role="alert" id={errorId} className="field-error">
          {error}
        </p>
      ) : null}
    </div>
  )
}

function RequiredIntegerField(props: {
  id: string
  label: string
  value: number
  pending: string | undefined
  error: string | null
  onChangeRaw: (raw: string) => void
  onBlur: () => void
}) {
  const { id, label, value, pending, error, onChangeRaw, onBlur } = props
  const message = pending !== undefined ? t('builder.validate.integerRequired') : error
  const errorId = `${id}-error`
  return (
    <div className="builder-field">
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
        aria-describedby={message ? errorId : undefined}
      />
      {message ? (
        <p role="alert" id={errorId} className="field-error">
          {message}
        </p>
      ) : null}
    </div>
  )
}

function firstErrorStartId(errors: TabProps['errors']): string | null {
  const withError = errors.find((e) => e.tab === 'achievements')
  if (!withError) return null
  const match = /^achievements\.([^.]+)\./.exec(withError.field)
  return match ? match[1] : null
}

export function AchievementsTab(props: TabProps) {
  const { draft, onChange, errors } = props

  const startIds = Object.keys(draft.starts)

  const [selectedStartId, setSelectedStartId] = useState<string>(() => {
    const errorStartId = firstErrorStartId(errors)
    if (errorStartId && errorStartId in draft.starts) return errorStartId
    if (draft.meta.default_start in draft.starts) return draft.meta.default_start
    return startIds[0]
  })

  const entries: AchievementDoc[] = draft.starts[selectedStartId]?.achievements ?? []

  const [selectedIndex, setSelectedIndex] = useState<number>(() => {
    const withError = entries.findIndex((_, i) =>
      errors.some((e) => e.tab === 'achievements' && e.field.startsWith(`achievements.${selectedStartId}.${i}.`)),
    )
    return withError >= 0 ? withError : 0
  })
  const [announcement, setAnnouncement] = useState('')
  const [pendingNumbers, setPendingNumbers] = useState<Record<string, string>>({})

  const createTriggerRef = useRef<HTMLButtonElement>(null)
  const addGateButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (selectedIndex > entries.length - 1) {
      setSelectedIndex(Math.max(0, entries.length - 1))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entries.length])

  function fieldError(field: string): string | null {
    return errors.find((e) => e.tab === 'achievements' && e.field === field)?.message ?? null
  }

  function entryHasError(i: number): boolean {
    return errors.some((e) => e.tab === 'achievements' && e.field.startsWith(`achievements.${selectedStartId}.${i}.`))
  }

  function entryLabelOf(entry: AchievementDoc): string {
    return entry.name.trim() || t('builder.achievements.unnamed')
  }

  function updateStart(patch: Partial<StartDoc>) {
    const start = draft.starts[selectedStartId]
    onChange({ ...draft, starts: { ...draft.starts, [selectedStartId]: { ...start, ...patch } } })
  }

  function updateEntry(index: number, patch: Partial<AchievementDoc>) {
    updateStart({ achievements: entries.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)) })
  }

  function updateGate(entryIndex: number, gateIndex: number, patch: Partial<StatGateDoc>) {
    const entry = entries[entryIndex]
    const stat_gates = entry.stat_gates.map((gate, j) => (j === gateIndex ? { ...gate, ...patch } : gate))
    updateEntry(entryIndex, { stat_gates })
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

  function addGate() {
    const entry = entries[selectedIndex]
    const firstStatId = draft.stats[0]?.id ?? ''
    const newIndex = entry.stat_gates.length
    updateEntry(selectedIndex, { stat_gates: [...entry.stat_gates, { id: firstStatId, at_least: 0 }] })
    requestAnimationFrame(() => {
      document
        .getElementById(`builder-field-achievements.${selectedStartId}.${selectedIndex}.stat_gates.${newIndex}.id`)
        ?.focus()
    })
  }

  function removeGate(gateIndex: number) {
    const entry = entries[selectedIndex]
    const nextGates = entry.stat_gates.filter((_, j) => j !== gateIndex)
    updateEntry(selectedIndex, { stat_gates: nextGates })
    requestAnimationFrame(() => {
      if (nextGates.length === 0) {
        addGateButtonRef.current?.focus()
        return
      }
      const focusIndex = gateIndex < nextGates.length ? gateIndex : nextGates.length - 1
      document
        .getElementById(`builder-field-achievements.${selectedStartId}.${selectedIndex}.stat_gates.${focusIndex}.id`)
        ?.focus()
    })
  }

  function selectStart(startId: string) {
    if (startId === selectedStartId) return
    setSelectedStartId(startId)
    setSelectedIndex(0)
  }

  function selectEntry(index: number) {
    if (index === selectedIndex) return
    setSelectedIndex(index)
    setAnnouncement(t('builder.detail.selected', { name: entryLabelOf(entries[index]) }))
    requestAnimationFrame(() => {
      document.getElementById(`builder-field-achievements.${selectedStartId}.${index}.id`)?.focus()
    })
  }

  function createEntry() {
    const id = nextSuggestedAchievementId(entries.map((e) => e.id))
    const newIndex = entries.length
    updateStart({ achievements: [...entries, newAchievement(id)] })
    setSelectedIndex(newIndex)
    setAnnouncement(t('builder.achievements.added', { name: id }))
    requestAnimationFrame(() => {
      document.getElementById(`builder-field-achievements.${selectedStartId}.${newIndex}.id`)?.focus()
    })
  }

  function removeEntry(index: number) {
    const removedLabel = entryLabelOf(entries[index])
    const nextEntries = entries.filter((_, i) => i !== index)
    updateStart({ achievements: nextEntries })
    setAnnouncement(t('builder.achievements.removed', { name: removedLabel }))
    if (nextEntries.length === 0) {
      setSelectedIndex(0)
      requestAnimationFrame(() => createTriggerRef.current?.focus())
      return
    }
    const focusIndex = index < nextEntries.length ? index : nextEntries.length - 1
    const removedSelected = index === selectedIndex
    if (index < selectedIndex) setSelectedIndex(selectedIndex - 1)
    else if (removedSelected) setSelectedIndex(focusIndex)
    requestAnimationFrame(() => {
      const target = removedSelected
        ? `builder-field-achievements.${selectedStartId}.${focusIndex}.id`
        : `builder-achievements-listItem-${focusIndex}`
      document.getElementById(target)?.focus()
    })
  }

  const selectedEntry: AchievementDoc | undefined = entries[selectedIndex]

  return (
    <div className="builder-achievements-tab">
      <h2>{t('builder.achievements.heading')}</h2>

      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>

      <div className="builder-field">
        <label htmlFor="builder-field-achievements-start">{t('builder.achievements.startLabel')}</label>
        <select
          id="builder-field-achievements-start"
          value={selectedStartId}
          onChange={(e) => selectStart(e.target.value)}
        >
          {startIds.map((startId) => (
            <option key={startId} value={startId}>
              {draft.starts[startId].name.trim() || startId}
            </option>
          ))}
        </select>
        <p className="field-hint">{t('builder.achievements.startHint')}</p>
      </div>

      {entries.length === 0 ? (
        <EmptyState
          title={t('builder.achievements.empty.title')}
          body={t('builder.achievements.empty.body')}
          action={
            <button type="button" ref={createTriggerRef} onClick={createEntry}>
              {t('builder.achievements.create')}
            </button>
          }
        />
      ) : (
        <div className="builder-masterDetail">
          <div className="builder-achievements-list">
            <p id="builder-achievements-listLabel" className="builder-list-label">
              {t('builder.achievements.listLabel')}
            </p>
            <ul className="builder-list" aria-labelledby="builder-achievements-listLabel">
              {entries.map((entry, i) => {
                const hasError = entryHasError(i)
                return (
                  <li
                    key={i}
                    className={[i === selectedIndex ? 'is-selected' : '', hasError ? 'is-invalid' : ''].filter(Boolean).join(' ')}
                  >
                    <button
                      type="button"
                      id={`builder-achievements-listItem-${i}`}
                      className="builder-list-item"
                      aria-current={i === selectedIndex || undefined}
                      onClick={() => selectEntry(i)}
                    >
                      <span className="builder-achievements-listItemText">
                        <span>{entryLabelOf(entry)}</span>
                        <span className="builder-starts-badge">
                          {entry.type === 'ending' ? t('builder.achievements.type.ending') : t('builder.achievements.type.achievement')}
                        </span>
                      </span>
                      {hasError ? <span className="visually-hidden">{t('builder.starts.itemInvalid')}</span> : null}
                    </button>
                    <button
                      type="button"
                      aria-label={t('builder.achievements.remove.title', { name: entryLabelOf(entry) })}
                      onClick={() => removeEntry(i)}
                    >
                      {t('common.remove')}
                    </button>
                  </li>
                )
              })}
            </ul>
            <button type="button" ref={createTriggerRef} onClick={createEntry}>
              {t('builder.achievements.create')}
            </button>
          </div>

          {selectedEntry ? (
            <div className="builder-achievements-detail">
              <div className="builder-field">
                <label htmlFor={`builder-field-achievements.${selectedStartId}.${selectedIndex}.id`}>
                  {t('builder.achievements.id')}
                </label>
                <input
                  id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.id`}
                  value={selectedEntry.id}
                  onChange={(e) => updateEntry(selectedIndex, { id: e.target.value })}
                  onBlur={(e) => updateEntry(selectedIndex, { id: e.target.value.trim() })}
                  aria-invalid={fieldError(`achievements.${selectedStartId}.${selectedIndex}.id`) ? 'true' : undefined}
                  aria-describedby={
                    fieldError(`achievements.${selectedStartId}.${selectedIndex}.id`)
                      ? `builder-field-achievements.${selectedStartId}.${selectedIndex}.id-error`
                      : undefined
                  }
                />
                {fieldError(`achievements.${selectedStartId}.${selectedIndex}.id`) ? (
                  <p
                    role="alert"
                    id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.id-error`}
                    className="field-error"
                  >
                    {fieldError(`achievements.${selectedStartId}.${selectedIndex}.id`)}
                  </p>
                ) : null}
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-achievements.${selectedStartId}.${selectedIndex}.name`}>
                  {t('builder.achievements.name')}
                </label>
                <input
                  id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.name`}
                  value={selectedEntry.name}
                  onChange={(e) => updateEntry(selectedIndex, { name: e.target.value })}
                  onBlur={(e) => updateEntry(selectedIndex, { name: e.target.value.trim() })}
                  aria-invalid={fieldError(`achievements.${selectedStartId}.${selectedIndex}.name`) ? 'true' : undefined}
                  aria-describedby={
                    fieldError(`achievements.${selectedStartId}.${selectedIndex}.name`)
                      ? `builder-field-achievements.${selectedStartId}.${selectedIndex}.name-error`
                      : undefined
                  }
                />
                {fieldError(`achievements.${selectedStartId}.${selectedIndex}.name`) ? (
                  <p
                    role="alert"
                    id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.name-error`}
                    className="field-error"
                  >
                    {fieldError(`achievements.${selectedStartId}.${selectedIndex}.name`)}
                  </p>
                ) : null}
              </div>

              <fieldset className="builder-field">
                <legend>{t('builder.achievements.type')}</legend>
                <label>
                  <input
                    type="radio"
                    name={`builder-field-achievements.${selectedStartId}.${selectedIndex}.type`}
                    checked={selectedEntry.type === 'achievement'}
                    onChange={() => updateEntry(selectedIndex, { type: 'achievement' })}
                  />
                  {t('builder.achievements.type.achievement')}
                </label>
                <label>
                  <input
                    type="radio"
                    name={`builder-field-achievements.${selectedStartId}.${selectedIndex}.type`}
                    checked={selectedEntry.type === 'ending'}
                    onChange={() => updateEntry(selectedIndex, { type: 'ending' })}
                  />
                  {t('builder.achievements.type.ending')}
                </label>
                <p className="field-hint">{t('builder.achievements.type.hint')}</p>
              </fieldset>

              <div className="builder-field">
                <label htmlFor={`builder-field-achievements.${selectedStartId}.${selectedIndex}.rarity`}>
                  {t('builder.achievements.rarity')}
                </label>
                <select
                  id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.rarity`}
                  value={selectedEntry.rarity}
                  onChange={(e) => updateEntry(selectedIndex, { rarity: e.target.value as AchievementDoc['rarity'] })}
                >
                  <option value="common">{t('builder.achievements.rarity.common')}</option>
                  <option value="rare">{t('builder.achievements.rarity.rare')}</option>
                  <option value="epic">{t('builder.achievements.rarity.epic')}</option>
                  <option value="legendary">{t('builder.achievements.rarity.legendary')}</option>
                </select>
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-achievements.${selectedStartId}.${selectedIndex}.hint`}>
                  {t('builder.achievements.hint')}
                </label>
                <input
                  id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.hint`}
                  value={selectedEntry.hint ?? ''}
                  onChange={(e) =>
                    updateEntry(selectedIndex, { hint: e.target.value.trim() === '' ? null : e.target.value })
                  }
                  onBlur={(e) => {
                    const trimmed = e.target.value.trim()
                    updateEntry(selectedIndex, { hint: trimmed === '' ? null : trimmed })
                  }}
                  aria-describedby={`builder-field-achievements.${selectedStartId}.${selectedIndex}.hint-hint`}
                />
                <p className="field-hint" id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.hint-hint`}>
                  {t('builder.achievements.hint.hint')}
                </p>
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-achievements.${selectedStartId}.${selectedIndex}.condition`}>
                  {t('builder.achievements.condition')}
                </label>
                <textarea
                  id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.condition`}
                  className="builder-field-textarea"
                  rows={4}
                  value={selectedEntry.condition}
                  onChange={(e) => updateEntry(selectedIndex, { condition: e.target.value })}
                  aria-invalid={fieldError(`achievements.${selectedStartId}.${selectedIndex}.condition`) ? 'true' : undefined}
                  aria-describedby={
                    [
                      fieldError(`achievements.${selectedStartId}.${selectedIndex}.condition`)
                        ? `builder-field-achievements.${selectedStartId}.${selectedIndex}.condition-error`
                        : null,
                      `builder-field-achievements.${selectedStartId}.${selectedIndex}.condition-hint`,
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                />
                <p className="field-hint" id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.condition-hint`}>
                  {t('builder.achievements.condition.hint')}
                </p>
                {fieldError(`achievements.${selectedStartId}.${selectedIndex}.condition`) ? (
                  <p
                    role="alert"
                    id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.condition-error`}
                    className="field-error"
                  >
                    {fieldError(`achievements.${selectedStartId}.${selectedIndex}.condition`)}
                  </p>
                ) : null}
              </div>

              <OptionalIntegerField
                id={`builder-field-achievements.${selectedStartId}.${selectedIndex}.min_turn`}
                label={t('builder.achievements.minTurn')}
                hint={t('builder.achievements.minTurn.hint')}
                hintId={`builder-field-achievements.${selectedStartId}.${selectedIndex}.min_turn-hint`}
                value={selectedEntry.min_turn ?? null}
                error={fieldError(`achievements.${selectedStartId}.${selectedIndex}.min_turn`)}
                onChange={(value) => updateEntry(selectedIndex, { min_turn: value })}
              />

              <fieldset className="builder-field builder-achievements-gates">
                <legend>{t('builder.achievements.gates')}</legend>
                <p className="field-hint">{t('builder.achievements.gates.hint')}</p>
                {draft.stats.length === 0 ? <p className="field-hint">{t('builder.achievements.gates.noStats')}</p> : null}
                {selectedEntry.stat_gates.map((gate, j) => {
                  const idField = `achievements.${selectedStartId}.${selectedIndex}.stat_gates.${j}.id`
                  const atLeastField = `achievements.${selectedStartId}.${selectedIndex}.stat_gates.${j}.at_least`
                  return (
                    <div className="builder-achievements-gateRow" key={j}>
                      <div className="builder-field">
                        <label htmlFor={`builder-field-${idField}`}>{t('builder.achievements.gates.stat')}</label>
                        <select
                          id={`builder-field-${idField}`}
                          value={gate.id}
                          onChange={(e) => updateGate(selectedIndex, j, { id: e.target.value })}
                        >
                          {draft.stats.some((stat) => stat.id === gate.id) ? null : (
                            <option value={gate.id}>{gate.id}</option>
                          )}
                          {draft.stats.map((stat) => (
                            <option key={stat.id} value={stat.id}>
                              {stat.name.trim() || stat.id}
                            </option>
                          ))}
                        </select>
                      </div>
                      <RequiredIntegerField
                        id={`builder-field-${atLeastField}`}
                        label={t('builder.achievements.gates.atLeast')}
                        value={gate.at_least}
                        pending={pendingNumbers[atLeastField]}
                        error={fieldError(atLeastField)}
                        onChangeRaw={(raw) => commitNumber(atLeastField, raw, (n) => updateGate(selectedIndex, j, { at_least: n }))}
                        onBlur={() => clearPending(atLeastField)}
                      />
                      <button
                        type="button"
                        aria-label={t('builder.achievements.gates.remove.title', { id: gate.id })}
                        onClick={() => removeGate(j)}
                      >
                        {t('common.remove')}
                      </button>
                    </div>
                  )
                })}
                <button type="button" ref={addGateButtonRef} onClick={addGate} disabled={draft.stats.length === 0}>
                  {t('builder.achievements.gates.add')}
                </button>
              </fieldset>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
