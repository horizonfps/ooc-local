import { useEffect, useRef, useState } from 'react'
import type { TabProps } from '../../screens/BuilderEditorScreen'
import type { HudDefaults, StartDoc } from '../../api'
import { t } from '../../i18n'
import '../../screens/builderEditor.css'

const ID_RE = /^[a-z0-9-]+$/
const WEATHER_CODES = ['clear', 'cloudy', 'rain', 'storm', 'snow', 'fog', 'night'] as const
const MAX_SUGGESTIONS = 3
const NARROW_QUERY = '(max-width: 899px)'

function matchMediaSupported(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
}

function useIsNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => (matchMediaSupported() ? window.matchMedia(NARROW_QUERY).matches : false))
  useEffect(() => {
    if (!matchMediaSupported()) return
    const mql = window.matchMedia(NARROW_QUERY)
    const handler = () => setNarrow(mql.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])
  return narrow
}

function nextSuggestedId(existing: readonly string[]): string {
  let n = 2
  while (existing.includes(`start-${n}`)) n += 1
  return `start-${n}`
}

function toggleCharacter(start: StartDoc, charId: string): string[] | null {
  const current = start.characters ?? []
  const next = current.includes(charId) ? current.filter((c) => c !== charId) : [...current, charId]
  return next.length === 0 ? null : next
}

export function StartsTab(props: TabProps) {
  const { draft, onChange, errors, goToTab } = props
  const startIds = Object.keys(draft.starts)
  const isNarrow = useIsNarrow()

  const [selectedId, setSelectedId] = useState<string>(
    draft.meta.default_start in draft.starts ? draft.meta.default_start : (startIds[0] ?? ''),
  )
  const [announcement, setAnnouncement] = useState('')

  const [createOpen, setCreateOpen] = useState(false)
  const [createId, setCreateId] = useState('')
  const [createName, setCreateName] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const nameFieldRef = useRef<HTMLInputElement>(null)
  const createDialogRef = useRef<HTMLDialogElement>(null)
  const createIdRef = useRef<HTMLInputElement>(null)
  const createTriggerRef = useRef<HTMLButtonElement>(null)
  const deleteDialogRef = useRef<HTMLDialogElement>(null)
  const deleteCancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!(selectedId in draft.starts)) {
      setSelectedId(startIds[0] ?? '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.starts])

  useEffect(() => {
    if (createOpen) {
      createDialogRef.current?.showModal()
      createIdRef.current?.focus()
      createIdRef.current?.select()
    } else {
      createDialogRef.current?.close()
    }
  }, [createOpen])

  useEffect(() => {
    if (deleteTarget !== null) {
      deleteDialogRef.current?.showModal()
      deleteCancelRef.current?.focus()
    } else {
      deleteDialogRef.current?.close()
    }
  }, [deleteTarget])

  function fieldError(field: string): string | null {
    return errors.find((e) => e.tab === 'starts' && e.field === field)?.message ?? null
  }

  function selectStart(id: string) {
    if (id === selectedId) return
    setSelectedId(id)
    const name = draft.starts[id]?.name || id
    setAnnouncement(t('builder.detail.selected', { name }))
    requestAnimationFrame(() => nameFieldRef.current?.focus())
  }

  function updateStart(id: string, patch: Partial<StartDoc>) {
    onChange({ ...draft, starts: { ...draft.starts, [id]: { ...draft.starts[id], ...patch } } })
  }

  function updateHud(id: string, patch: Partial<HudDefaults>) {
    const start = draft.starts[id]
    updateStart(id, { hud: { ...start.hud, ...patch } })
  }

  function updateSuggestion(id: string, index: number, value: string) {
    const start = draft.starts[id]
    const next = start.suggestions.slice()
    next[index] = value
    updateStart(id, { suggestions: next })
  }

  function addSuggestion(id: string) {
    const start = draft.starts[id]
    if (start.suggestions.length >= MAX_SUGGESTIONS) return
    updateStart(id, { suggestions: [...start.suggestions, ''] })
  }

  function removeSuggestion(id: string, index: number) {
    const start = draft.starts[id]
    updateStart(id, { suggestions: start.suggestions.filter((_, i) => i !== index) })
  }

  function openCreate() {
    setCreateId(nextSuggestedId(startIds))
    setCreateName('')
    setCreateError(null)
    setCreateOpen(true)
  }

  function closeCreate() {
    setCreateOpen(false)
    createTriggerRef.current?.focus()
  }

  function handleCreateSubmit(event: React.FormEvent) {
    event.preventDefault()
    const id = createId.trim()
    if (!id || !ID_RE.test(id)) {
      setCreateError(t('builder.field.slugInvalid'))
      return
    }
    if (id in draft.starts) {
      setCreateError(t('builder.field.slugTaken', { slug: id }))
      return
    }
    const baseHud = draft.starts[draft.meta.default_start]?.hud ?? draft.starts[startIds[0]]?.hud
    const newStart: StartDoc = {
      id,
      name: createName.trim(),
      prologue: '',
      opening_scene: '',
      play_guide: null,
      suggestions: [],
      hud: baseHud ? { ...baseHud } : { location: '', time: '00:00', weather: 'clear' },
      characters: null,
    }
    onChange({ ...draft, starts: { ...draft.starts, [id]: newStart } })
    setCreateOpen(false)
    setSelectedId(id)
    createTriggerRef.current?.focus()
  }

  function openDelete(id: string) {
    if (startIds.length <= 1) return
    setDeleteTarget(id)
  }

  function closeDelete() {
    setDeleteTarget(null)
  }

  function handleDeleteConfirm() {
    if (deleteTarget === null) return
    const id = deleteTarget
    const wasDefault = draft.meta.default_start === id
    const remainingIds = startIds.filter((existing) => existing !== id)
    const nextStarts = { ...draft.starts }
    delete nextStarts[id]
    const nextDefault = wasDefault ? (remainingIds[0] ?? draft.meta.default_start) : draft.meta.default_start
    onChange({ ...draft, starts: nextStarts, meta: { ...draft.meta, default_start: nextDefault } })
    setDeleteTarget(null)
    if (selectedId === id) setSelectedId(remainingIds[0] ?? '')
    if (wasDefault && remainingIds[0]) {
      const promotedName = draft.starts[remainingIds[0]].name || remainingIds[0]
      setAnnouncement(t('builder.starts.delete.defaultMoved', { name: promotedName }))
    }
  }

  const selectedStart: StartDoc | undefined = draft.starts[selectedId]
  const characterIds = Object.keys(draft.characters)
  const deleteTargetName = deleteTarget !== null ? draft.starts[deleteTarget]?.name || deleteTarget : ''

  return (
    <div className="builder-starts-tab">
      <h2>{t('builder.starts.heading')}</h2>

      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>

      <div className="builder-starts-body">
        {isNarrow ? (
          <div className="builder-starts-selectRow">
            <label htmlFor="builder-starts-select">{t('builder.starts.listLabel')}</label>
            <select
              id="builder-starts-select"
              value={selectedId}
              onChange={(e) => selectStart(e.target.value)}
            >
              {startIds.map((id) => (
                <option key={id} value={id}>
                  {draft.starts[id].name || id}
                </option>
              ))}
            </select>
            <div className="builder-starts-selectActions">
              <button type="button" ref={createTriggerRef} onClick={openCreate}>
                {t('builder.starts.create')}
              </button>
              <button
                type="button"
                disabled={startIds.length <= 1}
                title={startIds.length <= 1 ? t('builder.starts.delete.lastDisabled') : undefined}
                aria-label={selectedStart ? t('builder.starts.delete.title', { name: selectedStart.name || selectedId }) : undefined}
                onClick={() => openDelete(selectedId)}
              >
                {t('builder.starts.delete')}
              </button>
            </div>
          </div>
        ) : (
          <div className="builder-starts-list">
            <p id="builder-starts-listLabel" className="builder-starts-listLabel">
              {t('builder.starts.listLabel')}
            </p>
            <ul aria-labelledby="builder-starts-listLabel">
              {startIds.map((id) => {
                const start = draft.starts[id]
                return (
                  <li key={id} className={id === selectedId ? 'is-selected' : ''}>
                    <button
                      type="button"
                      className="builder-starts-listItem"
                      aria-current={id === selectedId || undefined}
                      onClick={() => selectStart(id)}
                    >
                      <span className="builder-starts-listItemName">{start.name || id}</span>
                      {draft.meta.default_start === id ? (
                        <span className="builder-starts-badge">{t('builder.starts.defaultBadge')}</span>
                      ) : null}
                      <span className="field-hint">{t('builder.field.counter', { count: start.suggestions.length, max: MAX_SUGGESTIONS })}</span>
                    </button>
                    <button
                      type="button"
                      disabled={startIds.length <= 1}
                      title={startIds.length <= 1 ? t('builder.starts.delete.lastDisabled') : undefined}
                      aria-label={t('builder.starts.delete.title', { name: start.name || id })}
                      onClick={() => openDelete(id)}
                    >
                      {t('builder.starts.delete')}
                    </button>
                  </li>
                )
              })}
            </ul>
            <button type="button" ref={createTriggerRef} onClick={openCreate}>
              {t('builder.starts.create')}
            </button>
          </div>
        )}

        {selectedStart ? (
          <div className="builder-starts-detail">
            <div className="builder-field">
              <label htmlFor="builder-field-starts.name">{t('builder.starts.name')}</label>
              <input
                id="builder-field-starts.name"
                ref={nameFieldRef}
                value={selectedStart.name}
                onChange={(e) => updateStart(selectedId, { name: e.target.value })}
                aria-invalid={fieldError(`starts.${selectedId}.name`) ? 'true' : undefined}
                aria-describedby={fieldError(`starts.${selectedId}.name`) ? 'builder-field-starts.name-error' : undefined}
              />
              {fieldError(`starts.${selectedId}.name`) ? (
                <p role="alert" id="builder-field-starts.name-error" className="field-error">
                  {fieldError(`starts.${selectedId}.name`)}
                </p>
              ) : null}
            </div>

            <div className="builder-field">
              <label>
                <input
                  type="radio"
                  name="builder-starts-default"
                  checked={draft.meta.default_start === selectedId}
                  onChange={() => onChange({ ...draft, meta: { ...draft.meta, default_start: selectedId } })}
                />
                {t('builder.starts.defaultToggle')}
              </label>
            </div>

            <div className="builder-field">
              <label htmlFor="builder-field-starts.prologue">{t('builder.starts.prologue')}</label>
              <textarea
                id="builder-field-starts.prologue"
                className="builder-field-textarea"
                rows={8}
                value={selectedStart.prologue}
                onChange={(e) => updateStart(selectedId, { prologue: e.target.value })}
                aria-invalid={fieldError(`starts.${selectedId}.prologue`) ? 'true' : undefined}
                aria-describedby={
                  [
                    fieldError(`starts.${selectedId}.prologue`) ? 'builder-field-starts.prologue-error' : null,
                    'builder-field-starts.prologue-hint',
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
              />
              <p className="field-hint" id="builder-field-starts.prologue-hint">
                {t('builder.starts.prologue.hint')}
              </p>
              {fieldError(`starts.${selectedId}.prologue`) ? (
                <p role="alert" id="builder-field-starts.prologue-error" className="field-error">
                  {fieldError(`starts.${selectedId}.prologue`)}
                </p>
              ) : null}
            </div>

            <div className="builder-field">
              <label htmlFor="builder-field-starts.opening_scene">{t('builder.starts.openingScene')}</label>
              <textarea
                id="builder-field-starts.opening_scene"
                className="builder-field-textarea"
                rows={6}
                value={selectedStart.opening_scene}
                onChange={(e) => updateStart(selectedId, { opening_scene: e.target.value })}
                aria-invalid={fieldError(`starts.${selectedId}.opening_scene`) ? 'true' : undefined}
                aria-describedby={
                  [
                    fieldError(`starts.${selectedId}.opening_scene`) ? 'builder-field-starts.opening_scene-error' : null,
                    'builder-field-starts.opening_scene-hint',
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
              />
              <p className="field-hint" id="builder-field-starts.opening_scene-hint">
                {t('builder.starts.openingScene.hint')}
              </p>
              {fieldError(`starts.${selectedId}.opening_scene`) ? (
                <p role="alert" id="builder-field-starts.opening_scene-error" className="field-error">
                  {fieldError(`starts.${selectedId}.opening_scene`)}
                </p>
              ) : null}
            </div>

            <div className="builder-field">
              <label htmlFor="builder-field-starts.play_guide">
                {t('builder.starts.playGuide')} <span className="field-hint">({t('common.optional')})</span>
              </label>
              <textarea
                id="builder-field-starts.play_guide"
                className="builder-field-textarea"
                rows={4}
                value={selectedStart.play_guide ?? ''}
                onChange={(e) => updateStart(selectedId, { play_guide: e.target.value === '' ? null : e.target.value })}
                aria-describedby="builder-field-starts.play_guide-hint"
              />
              <p className="field-hint" id="builder-field-starts.play_guide-hint">
                {t('builder.starts.playGuide.hint')}
              </p>
            </div>

            <fieldset className="builder-field builder-starts-suggestions">
              <legend>{t('builder.starts.suggestions.legend')}</legend>
              {selectedStart.suggestions.map((suggestion, index) => {
                const field = `starts.${selectedId}.suggestions.${index}`
                const message = fieldError(field)
                return (
                  <div className="builder-starts-suggestionRow" key={index}>
                    <label htmlFor={`builder-field-${field}`}>
                      {t('builder.starts.suggestions.item', { index: index + 1 })}
                    </label>
                    <input
                      id={`builder-field-${field}`}
                      value={suggestion}
                      onChange={(e) => updateSuggestion(selectedId, index, e.target.value)}
                      aria-invalid={message ? 'true' : undefined}
                      aria-describedby={message ? `${field}-error` : undefined}
                    />
                    <button
                      type="button"
                      aria-label={t('builder.starts.suggestions.remove', { index: index + 1 })}
                      onClick={() => removeSuggestion(selectedId, index)}
                    >
                      {t('common.remove')}
                    </button>
                    {message ? (
                      <p role="alert" id={`${field}-error`} className="field-error">
                        {message}
                      </p>
                    ) : null}
                  </div>
                )
              })}
              <button
                type="button"
                disabled={selectedStart.suggestions.length >= MAX_SUGGESTIONS}
                onClick={() => addSuggestion(selectedId)}
              >
                {t('builder.starts.suggestions.add')}
              </button>
              <p className="field-hint">{t('builder.starts.suggestions.max')}</p>
            </fieldset>

            <fieldset className="builder-field builder-starts-hud">
              <legend>{t('builder.starts.hud.legend')}</legend>
              <div className="builder-field">
                <label htmlFor="builder-field-starts.hud.location">{t('builder.starts.hud.location')}</label>
                <input
                  id="builder-field-starts.hud.location"
                  value={selectedStart.hud.location}
                  onChange={(e) => updateHud(selectedId, { location: e.target.value })}
                  aria-invalid={fieldError(`starts.${selectedId}.hud.location`) ? 'true' : undefined}
                  aria-describedby={fieldError(`starts.${selectedId}.hud.location`) ? 'builder-field-starts.hud.location-error' : undefined}
                />
                {fieldError(`starts.${selectedId}.hud.location`) ? (
                  <p role="alert" id="builder-field-starts.hud.location-error" className="field-error">
                    {fieldError(`starts.${selectedId}.hud.location`)}
                  </p>
                ) : null}
              </div>
              <div className="builder-field">
                <label htmlFor="builder-field-starts.hud.time">{t('builder.starts.hud.time')}</label>
                <input
                  id="builder-field-starts.hud.time"
                  type="time"
                  value={selectedStart.hud.time}
                  onChange={(e) => updateHud(selectedId, { time: e.target.value })}
                  aria-invalid={fieldError(`starts.${selectedId}.hud.time`) ? 'true' : undefined}
                  aria-describedby={fieldError(`starts.${selectedId}.hud.time`) ? 'builder-field-starts.hud.time-error' : undefined}
                />
                {fieldError(`starts.${selectedId}.hud.time`) ? (
                  <p role="alert" id="builder-field-starts.hud.time-error" className="field-error">
                    {fieldError(`starts.${selectedId}.hud.time`)}
                  </p>
                ) : null}
              </div>
              <div className="builder-field">
                <label htmlFor="builder-field-starts.hud.weather">{t('builder.starts.hud.weather')}</label>
                <select
                  id="builder-field-starts.hud.weather"
                  value={selectedStart.hud.weather}
                  onChange={(e) => updateHud(selectedId, { weather: e.target.value })}
                  aria-invalid={fieldError(`starts.${selectedId}.hud.weather`) ? 'true' : undefined}
                  aria-describedby={fieldError(`starts.${selectedId}.hud.weather`) ? 'builder-field-starts.hud.weather-error' : undefined}
                >
                  {WEATHER_CODES.map((code) => (
                    <option key={code} value={code}>
                      {t(`hud.weather.${code}`)}
                    </option>
                  ))}
                </select>
                {fieldError(`starts.${selectedId}.hud.weather`) ? (
                  <p role="alert" id="builder-field-starts.hud.weather-error" className="field-error">
                    {fieldError(`starts.${selectedId}.hud.weather`)}
                  </p>
                ) : null}
              </div>
            </fieldset>

            <fieldset className="builder-field builder-starts-cast">
              <legend>{t('builder.starts.cast.legend')}</legend>
              {characterIds.length === 0 ? (
                <button type="button" className="builder-starts-castEmptyLink field-hint" onClick={() => goToTab('characters')}>
                  {t('builder.starts.cast.empty')}
                </button>
              ) : (
                <>
                  <p className="field-hint">{t('builder.starts.cast.hint')}</p>
                  <div className="builder-starts-castList">
                    {characterIds.map((charId) => (
                      <label key={charId} className="builder-starts-castItem">
                        <input
                          type="checkbox"
                          checked={(selectedStart.characters ?? []).includes(charId)}
                          onChange={() => updateStart(selectedId, { characters: toggleCharacter(selectedStart, charId) })}
                        />
                        {draft.characters[charId].name}
                      </label>
                    ))}
                  </div>
                </>
              )}
            </fieldset>
          </div>
        ) : null}
      </div>

      <dialog
        ref={createDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-starts-create-title"
        onClose={() => setCreateOpen(false)}
        onCancel={(event) => {
          event.preventDefault()
          closeCreate()
        }}
      >
        <h2 id="builder-starts-create-title">{t('builder.starts.create.title')}</h2>
        <form onSubmit={handleCreateSubmit}>
          <div className="builder-field">
            <label htmlFor="builder-starts-create-id">{t('builder.starts.create.idLabel')}</label>
            <input
              id="builder-starts-create-id"
              ref={createIdRef}
              value={createId}
              onChange={(e) => setCreateId(e.target.value)}
              aria-invalid={createError ? 'true' : undefined}
              aria-describedby="builder-starts-create-id-hint"
            />
            <p className="field-hint" id="builder-starts-create-id-hint">
              {t('builder.starts.create.idHint')}
            </p>
          </div>
          <div className="builder-field">
            <label htmlFor="builder-starts-create-name">{t('builder.starts.name')}</label>
            <input id="builder-starts-create-name" value={createName} onChange={(e) => setCreateName(e.target.value)} />
          </div>
          {createError ? (
            <p role="alert" className="field-error">
              {createError}
            </p>
          ) : null}
          <div className="builder-editor-dialog-actions">
            <button type="button" onClick={closeCreate}>
              {t('common.cancel')}
            </button>
            <button type="submit">{t('builder.starts.create.submit')}</button>
          </div>
        </form>
      </dialog>

      <dialog
        ref={deleteDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-starts-delete-title"
        onClose={() => setDeleteTarget(null)}
        onCancel={(event) => {
          event.preventDefault()
          closeDelete()
        }}
      >
        <h2 id="builder-starts-delete-title">{t('builder.starts.delete.title', { name: deleteTargetName })}</h2>
        <p>{t('builder.starts.delete.body', { id: deleteTarget ?? '' })}</p>
        <div className="builder-editor-dialog-actions">
          <button type="button" ref={deleteCancelRef} onClick={closeDelete}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={handleDeleteConfirm}>
            {t('builder.starts.delete')}
          </button>
        </div>
      </dialog>
    </div>
  )
}
