import { useEffect, useRef, useState } from 'react'
import type { TabProps } from '../../screens/BuilderEditorScreen'
import type { CharacterDoc, CharacterMind } from '../../api'
import { t } from '../../i18n'
import { MAX_EMOTIONS } from '../../builder/validate'
import { EmptyState } from '../EmptyState'
import '../../screens/builderEditor.css'

const ID_RE = /^[a-z0-9-]+$/
const SUGGESTED_EMOTIONS = ['default', 'smile', 'sad', 'angry', 'shy', 'despair', 'joy', 'crying', 'hit', 'attacking', 'mocking']
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

function newCharacter(): CharacterDoc {
  return {
    name: '',
    role: '',
    appearance: '',
    personality: '',
    voice: '',
    mind: { feeling: '', goal: '', opinion_of_player: null, secret_plan: null },
    sprite: null,
    power_tier: null,
    emotions: ['default'],
  }
}

export function CharactersTab(props: TabProps) {
  const { draft, onChange, errors } = props
  const characterIds = Object.keys(draft.characters)
  const isNarrow = useIsNarrow()

  const [selectedId, setSelectedId] = useState<string>(characterIds[0] ?? '')
  const [announcement, setAnnouncement] = useState('')

  const [createOpen, setCreateOpen] = useState(false)
  const [createId, setCreateId] = useState('')
  const [createName, setCreateName] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const [emotionInput, setEmotionInput] = useState('')
  const [emotionError, setEmotionError] = useState<string | null>(null)
  const [emotionNotice, setEmotionNotice] = useState('')

  const maxAssignedTier = characterIds.reduce((max, id) => Math.max(max, draft.characters[id].power_tier ?? 0), 0)
  const [tierFloor, setTierFloor] = useState(0)
  const tierCount = Math.max(maxAssignedTier, tierFloor)
  const [dragId, setDragId] = useState<string | null>(null)

  const nameFieldRef = useRef<HTMLInputElement>(null)
  const createDialogRef = useRef<HTMLDialogElement>(null)
  const createIdRef = useRef<HTMLInputElement>(null)
  const createTriggerRef = useRef<HTMLButtonElement>(null)
  const deleteDialogRef = useRef<HTMLDialogElement>(null)
  const deleteCancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!(selectedId in draft.characters)) {
      setSelectedId(characterIds[0] ?? '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.characters])

  useEffect(() => {
    setEmotionInput('')
    setEmotionError(null)
    setEmotionNotice('')
  }, [selectedId])

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
    return errors.find((e) => e.tab === 'characters' && e.field === field)?.message ?? null
  }

  function characterHasError(id: string): boolean {
    return errors.some((e) => e.tab === 'characters' && (e.field === `characters.${id}` || e.field.startsWith(`characters.${id}.`)))
  }

  function selectCharacter(id: string) {
    if (id === selectedId) return
    setSelectedId(id)
    const name = draft.characters[id]?.name || id
    setAnnouncement(t('builder.detail.selected', { name }))
    requestAnimationFrame(() => nameFieldRef.current?.focus())
  }

  function updateCharacter(id: string, patch: Partial<CharacterDoc>) {
    onChange({ ...draft, characters: { ...draft.characters, [id]: { ...draft.characters[id], ...patch } } })
  }

  function updateMind(id: string, patch: Partial<CharacterMind>) {
    const character = draft.characters[id]
    updateCharacter(id, { mind: { ...character.mind, ...patch } })
  }

  function openCreate() {
    setCreateId('')
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
    if (id in draft.characters) {
      setCreateError(t('builder.field.slugTaken', { slug: id }))
      return
    }
    const created: CharacterDoc = { ...newCharacter(), name: createName.trim() }
    onChange({ ...draft, characters: { ...draft.characters, [id]: created } })
    setCreateOpen(false)
    setSelectedId(id)
    createTriggerRef.current?.focus()
  }

  function openDelete(id: string) {
    setDeleteTarget(id)
  }

  function closeDelete() {
    setDeleteTarget(null)
  }

  function handleDeleteConfirm() {
    if (deleteTarget === null) return
    const id = deleteTarget
    const name = draft.characters[id]?.name || id
    const remainingIds = characterIds.filter((existing) => existing !== id)
    const nextCharacters = { ...draft.characters }
    delete nextCharacters[id]

    const affectedStartNames: string[] = []
    const nextStarts = { ...draft.starts }
    for (const startId of Object.keys(nextStarts)) {
      const start = nextStarts[startId]
      if (start.characters && start.characters.includes(id)) {
        const filtered = start.characters.filter((c) => c !== id)
        nextStarts[startId] = { ...start, characters: filtered.length === 0 ? null : filtered }
        affectedStartNames.push(start.name || startId)
      }
    }

    onChange({ ...draft, characters: nextCharacters, starts: nextStarts })
    setDeleteTarget(null)
    if (selectedId === id) setSelectedId(remainingIds[0] ?? '')
    if (affectedStartNames.length > 0) {
      setAnnouncement(t('builder.characters.delete.castUpdated', { name, starts: affectedStartNames.join(', ') }))
    }
  }

  function addEmotion(id: string, raw: string) {
    const value = raw.trim()
    if (!value) return
    if (!ID_RE.test(value)) {
      setEmotionError(t('builder.field.slugInvalid'))
      return
    }
    const character = draft.characters[id]
    if (character.emotions.includes(value)) {
      setEmotionError(null)
      setEmotionInput('')
      return
    }
    if (character.emotions.length >= MAX_EMOTIONS) {
      setEmotionError(t('builder.characters.emotions.max', { max: MAX_EMOTIONS - 1 }))
      return
    }
    setEmotionError(null)
    updateCharacter(id, { emotions: [...character.emotions, value] })
    setEmotionInput('')
  }

  function handleEmotionKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault()
      addEmotion(selectedId, emotionInput)
    }
  }

  function handleTierDrop(event: React.DragEvent, tier: number | null) {
    event.preventDefault()
    const id = event.dataTransfer.getData('text/plain') || dragId
    setDragId(null)
    if (!id || !(id in draft.characters)) return
    if (draft.characters[id].power_tier === tier) return
    updateCharacter(id, { power_tier: tier })
    const name = draft.characters[id].name || id
    setAnnouncement(
      tier === null
        ? t('builder.characters.powerTiers.movedOut', { name })
        : t('builder.characters.powerTiers.moved', { name, tier }),
    )
  }

  function tierChip(id: string) {
    const character = draft.characters[id]
    return (
      <span
        role="listitem"
        key={id}
        className="builder-tag-chip builder-powerTiers-chip"
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData('text/plain', id)
          e.dataTransfer.effectAllowed = 'move'
          setDragId(id)
        }}
        onDragEnd={() => setDragId(null)}
      >
        {character.name || id}
      </span>
    )
  }

  function removeEmotion(id: string, emotion: string) {
    if (emotion === 'default') return
    const character = draft.characters[id]
    updateCharacter(id, { emotions: character.emotions.filter((e) => e !== emotion) })
    setEmotionNotice(t('builder.characters.emotions.hasAsset', { emotion }))
  }

  const selectedCharacter: CharacterDoc | undefined = draft.characters[selectedId]
  const deleteTargetName = deleteTarget !== null ? draft.characters[deleteTarget]?.name || deleteTarget : ''
  const deleteTargetSprite =
    deleteTarget !== null ? draft.characters[deleteTarget]?.sprite || deleteTarget : ''
  const suggestedEmotions = selectedCharacter
    ? SUGGESTED_EMOTIONS.filter((emotion) => !selectedCharacter.emotions.includes(emotion))
    : []

  return (
    <div className="builder-characters-tab">
      <h2>{t('builder.characters.heading')}</h2>

      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>

      {characterIds.length === 0 ? (
        <EmptyState
          title={t('builder.characters.empty.title')}
          body={t('builder.characters.empty.body')}
          action={
            <button type="button" ref={createTriggerRef} onClick={openCreate}>
              {t('builder.characters.create')}
            </button>
          }
        />
      ) : (
      <div className="builder-characters-body">
        {isNarrow ? (
          <div className="builder-characters-selectRow">
            <label htmlFor="builder-characters-select">{t('builder.characters.listLabel')}</label>
            <select
              id="builder-characters-select"
              value={selectedId}
              onChange={(e) => selectCharacter(e.target.value)}
            >
              {characterIds.map((id) => (
                <option key={id} value={id}>
                  {draft.characters[id].name || id}
                </option>
              ))}
            </select>
            <div className="builder-characters-selectActions">
              <button type="button" ref={createTriggerRef} onClick={openCreate}>
                {t('builder.characters.create')}
              </button>
              <button
                type="button"
                aria-label={selectedCharacter ? t('builder.characters.delete.title', { name: selectedCharacter.name || selectedId }) : undefined}
                onClick={() => openDelete(selectedId)}
              >
                {t('builder.characters.delete')}
              </button>
            </div>
          </div>
        ) : (
          <div className="builder-characters-list">
            <p id="builder-characters-listLabel" className="builder-characters-listLabel">
              {t('builder.characters.listLabel')}
            </p>
            <ul aria-labelledby="builder-characters-listLabel">
              {characterIds.map((id) => {
                const character = draft.characters[id]
                const hasError = characterHasError(id)
                const initial = (character.name || id).charAt(0).toUpperCase()
                return (
                  <li key={id} className={[id === selectedId ? 'is-selected' : '', hasError ? 'is-invalid' : ''].filter(Boolean).join(' ')}>
                    <button
                      type="button"
                      className="builder-characters-listItem"
                      aria-current={id === selectedId || undefined}
                      onClick={() => selectCharacter(id)}
                    >
                      <span className="builder-characters-avatar" aria-hidden="true">
                        {initial}
                      </span>
                      <span className="builder-characters-listItemText">
                        <span className="builder-characters-listItemName">{character.name || id}</span>
                        <span className="builder-characters-listItemRole">{character.role}</span>
                      </span>
                      {character.power_tier !== null ? (
                        <span className="builder-starts-badge">{t('builder.characters.tierBadge', { tier: character.power_tier })}</span>
                      ) : null}
                      {hasError ? <span className="visually-hidden">{t('builder.starts.itemInvalid')}</span> : null}
                    </button>
                    <button
                      type="button"
                      aria-label={t('builder.characters.delete.title', { name: character.name || id })}
                      onClick={() => openDelete(id)}
                    >
                      {t('builder.characters.delete')}
                    </button>
                  </li>
                )
              })}
            </ul>
            <button type="button" ref={createTriggerRef} onClick={openCreate}>
              {t('builder.characters.create')}
            </button>
          </div>
        )}

        {selectedCharacter ? (
          <div className="builder-characters-detail">
            <div className="builder-field">
              <label htmlFor={`builder-field-characters.${selectedId}.name`}>{t('builder.characters.name')}</label>
              <input
                id={`builder-field-characters.${selectedId}.name`}
                ref={nameFieldRef}
                value={selectedCharacter.name}
                onChange={(e) => updateCharacter(selectedId, { name: e.target.value })}
                onBlur={(e) => updateCharacter(selectedId, { name: e.target.value.trim() })}
                aria-invalid={fieldError(`characters.${selectedId}.name`) ? 'true' : undefined}
                aria-describedby={fieldError(`characters.${selectedId}.name`) ? `builder-field-characters.${selectedId}.name-error` : undefined}
              />
              {fieldError(`characters.${selectedId}.name`) ? (
                <p role="alert" id={`builder-field-characters.${selectedId}.name-error`} className="field-error">
                  {fieldError(`characters.${selectedId}.name`)}
                </p>
              ) : null}
            </div>

            <div className="builder-field">
              <label htmlFor={`builder-field-characters.${selectedId}.role`}>{t('builder.characters.role')}</label>
              <input
                id={`builder-field-characters.${selectedId}.role`}
                value={selectedCharacter.role}
                onChange={(e) => updateCharacter(selectedId, { role: e.target.value })}
                aria-invalid={fieldError(`characters.${selectedId}.role`) ? 'true' : undefined}
                aria-describedby={
                  [
                    fieldError(`characters.${selectedId}.role`) ? `builder-field-characters.${selectedId}.role-error` : null,
                    `builder-field-characters.${selectedId}.role-hint`,
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
              />
              <p className="field-hint" id={`builder-field-characters.${selectedId}.role-hint`}>
                {t('builder.characters.role.hint')}
              </p>
              {fieldError(`characters.${selectedId}.role`) ? (
                <p role="alert" id={`builder-field-characters.${selectedId}.role-error`} className="field-error">
                  {fieldError(`characters.${selectedId}.role`)}
                </p>
              ) : null}
            </div>

            <div className="builder-field">
              <label htmlFor={`builder-field-characters.${selectedId}.appearance`}>{t('builder.characters.appearance')}</label>
              <textarea
                id={`builder-field-characters.${selectedId}.appearance`}
                className="builder-field-textarea"
                rows={4}
                value={selectedCharacter.appearance}
                onChange={(e) => updateCharacter(selectedId, { appearance: e.target.value })}
                aria-invalid={fieldError(`characters.${selectedId}.appearance`) ? 'true' : undefined}
                aria-describedby={
                  [
                    fieldError(`characters.${selectedId}.appearance`) ? `builder-field-characters.${selectedId}.appearance-error` : null,
                    `builder-field-characters.${selectedId}.appearance-hint`,
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
              />
              <p className="field-hint" id={`builder-field-characters.${selectedId}.appearance-hint`}>
                {t('builder.characters.appearance.hint')}
              </p>
              {fieldError(`characters.${selectedId}.appearance`) ? (
                <p role="alert" id={`builder-field-characters.${selectedId}.appearance-error`} className="field-error">
                  {fieldError(`characters.${selectedId}.appearance`)}
                </p>
              ) : null}
            </div>

            <div className="builder-field">
              <label htmlFor={`builder-field-characters.${selectedId}.personality`}>{t('builder.characters.personality')}</label>
              <textarea
                id={`builder-field-characters.${selectedId}.personality`}
                className="builder-field-textarea"
                rows={4}
                value={selectedCharacter.personality}
                onChange={(e) => updateCharacter(selectedId, { personality: e.target.value })}
                aria-invalid={fieldError(`characters.${selectedId}.personality`) ? 'true' : undefined}
                aria-describedby={
                  fieldError(`characters.${selectedId}.personality`) ? `builder-field-characters.${selectedId}.personality-error` : undefined
                }
              />
              {fieldError(`characters.${selectedId}.personality`) ? (
                <p role="alert" id={`builder-field-characters.${selectedId}.personality-error`} className="field-error">
                  {fieldError(`characters.${selectedId}.personality`)}
                </p>
              ) : null}
            </div>

            <div className="builder-field">
              <label htmlFor={`builder-field-characters.${selectedId}.voice`}>{t('builder.characters.voice')}</label>
              <textarea
                id={`builder-field-characters.${selectedId}.voice`}
                className="builder-field-textarea"
                rows={3}
                value={selectedCharacter.voice}
                onChange={(e) => updateCharacter(selectedId, { voice: e.target.value })}
                aria-invalid={fieldError(`characters.${selectedId}.voice`) ? 'true' : undefined}
                aria-describedby={
                  [
                    fieldError(`characters.${selectedId}.voice`) ? `builder-field-characters.${selectedId}.voice-error` : null,
                    `builder-field-characters.${selectedId}.voice-hint`,
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
              />
              <p className="field-hint" id={`builder-field-characters.${selectedId}.voice-hint`}>
                {t('builder.characters.voice.hint')}
              </p>
              {fieldError(`characters.${selectedId}.voice`) ? (
                <p role="alert" id={`builder-field-characters.${selectedId}.voice-error`} className="field-error">
                  {fieldError(`characters.${selectedId}.voice`)}
                </p>
              ) : null}
            </div>

            <fieldset className="builder-field builder-characters-mind">
              <legend>{t('builder.characters.mind.legend')}</legend>
              <p className="field-hint">{t('builder.characters.mind.hint')}</p>

              <div className="builder-field">
                <label htmlFor={`builder-field-characters.${selectedId}.mind.feeling`}>{t('builder.characters.mind.feeling')}</label>
                <textarea
                  id={`builder-field-characters.${selectedId}.mind.feeling`}
                  className="builder-field-textarea"
                  rows={2}
                  value={selectedCharacter.mind.feeling}
                  onChange={(e) => updateMind(selectedId, { feeling: e.target.value })}
                  aria-invalid={fieldError(`characters.${selectedId}.mind.feeling`) ? 'true' : undefined}
                  aria-describedby={
                    fieldError(`characters.${selectedId}.mind.feeling`) ? `builder-field-characters.${selectedId}.mind.feeling-error` : undefined
                  }
                />
                {fieldError(`characters.${selectedId}.mind.feeling`) ? (
                  <p role="alert" id={`builder-field-characters.${selectedId}.mind.feeling-error`} className="field-error">
                    {fieldError(`characters.${selectedId}.mind.feeling`)}
                  </p>
                ) : null}
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-characters.${selectedId}.mind.goal`}>{t('builder.characters.mind.goal')}</label>
                <textarea
                  id={`builder-field-characters.${selectedId}.mind.goal`}
                  className="builder-field-textarea"
                  rows={2}
                  value={selectedCharacter.mind.goal}
                  onChange={(e) => updateMind(selectedId, { goal: e.target.value })}
                  aria-invalid={fieldError(`characters.${selectedId}.mind.goal`) ? 'true' : undefined}
                  aria-describedby={
                    fieldError(`characters.${selectedId}.mind.goal`) ? `builder-field-characters.${selectedId}.mind.goal-error` : undefined
                  }
                />
                {fieldError(`characters.${selectedId}.mind.goal`) ? (
                  <p role="alert" id={`builder-field-characters.${selectedId}.mind.goal-error`} className="field-error">
                    {fieldError(`characters.${selectedId}.mind.goal`)}
                  </p>
                ) : null}
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-characters.${selectedId}.mind.opinion_of_player`}>
                  {t('builder.characters.mind.opinion')} <span className="field-hint">({t('common.optional')})</span>
                </label>
                <textarea
                  id={`builder-field-characters.${selectedId}.mind.opinion_of_player`}
                  className="builder-field-textarea"
                  rows={2}
                  value={selectedCharacter.mind.opinion_of_player ?? ''}
                  onChange={(e) => updateMind(selectedId, { opinion_of_player: e.target.value.trim() === '' ? null : e.target.value })}
                />
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-characters.${selectedId}.mind.secret_plan`}>
                  {t('builder.characters.mind.secretPlan')} <span className="field-hint">({t('common.optional')})</span>
                </label>
                <textarea
                  id={`builder-field-characters.${selectedId}.mind.secret_plan`}
                  className="builder-field-textarea"
                  rows={2}
                  value={selectedCharacter.mind.secret_plan ?? ''}
                  onChange={(e) => updateMind(selectedId, { secret_plan: e.target.value.trim() === '' ? null : e.target.value })}
                />
              </div>
            </fieldset>

            <div className="builder-field">
              <label htmlFor={`builder-field-characters.${selectedId}.sprite`}>
                {t('builder.characters.sprite')} <span className="field-hint">({t('common.optional')})</span>
              </label>
              <input
                id={`builder-field-characters.${selectedId}.sprite`}
                value={selectedCharacter.sprite ?? ''}
                placeholder={selectedId}
                onChange={(e) => updateCharacter(selectedId, { sprite: e.target.value.trim() === '' ? null : e.target.value.trim() })}
                aria-invalid={fieldError(`characters.${selectedId}.sprite`) ? 'true' : undefined}
                aria-describedby={
                  [
                    fieldError(`characters.${selectedId}.sprite`) ? `builder-field-characters.${selectedId}.sprite-error` : null,
                    `builder-field-characters.${selectedId}.sprite-hint`,
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
              />
              <p className="field-hint" id={`builder-field-characters.${selectedId}.sprite-hint`}>
                {t('builder.characters.sprite.hint')}
              </p>
              {fieldError(`characters.${selectedId}.sprite`) ? (
                <p role="alert" id={`builder-field-characters.${selectedId}.sprite-error`} className="field-error">
                  {fieldError(`characters.${selectedId}.sprite`)}
                </p>
              ) : null}
            </div>

            <div className="builder-field">
              <label htmlFor={`builder-field-characters.${selectedId}.power_tier`}>
                {t('builder.characters.tier')} <span className="field-hint">({t('common.optional')})</span>
              </label>
              <select
                id={`builder-field-characters.${selectedId}.power_tier`}
                value={selectedCharacter.power_tier ?? ''}
                onChange={(e) =>
                  updateCharacter(selectedId, { power_tier: e.target.value === '' ? null : Number(e.target.value) })
                }
                aria-describedby={`builder-field-characters.${selectedId}.power_tier-hint`}
              >
                <option value="">{t('builder.characters.tier.none')}</option>
                {Array.from({ length: tierCount + 1 }, (_, i) => i + 1).map((tier) => (
                  <option key={tier} value={tier}>
                    {t('builder.characters.powerTiers.tier', { tier })}
                  </option>
                ))}
              </select>
              <p className="field-hint" id={`builder-field-characters.${selectedId}.power_tier-hint`}>
                {t('builder.characters.tier.hint')}
              </p>
            </div>

            <fieldset className="builder-field builder-characters-emotions">
              <legend>{t('builder.characters.emotions.legend')}</legend>
              <p className="field-hint">{t('builder.characters.emotions.hint')}</p>

              <div role="list" className="builder-tags-list">
                {selectedCharacter.emotions.map((emotion) => (
                  <span
                    role="listitem"
                    key={emotion}
                    className="builder-tag-chip"
                    title={emotion === 'default' ? t('builder.characters.emotions.defaultLocked') : undefined}
                  >
                    {emotion}
                    {emotion !== 'default' ? (
                      <button
                        type="button"
                        aria-label={t('builder.characters.emotions.remove', { emotion })}
                        onClick={() => removeEmotion(selectedId, emotion)}
                      >
                        ×
                      </button>
                    ) : null}
                  </span>
                ))}
              </div>

              <p role="status" aria-live="polite" className="field-hint">
                {emotionNotice}
              </p>

              <div className="builder-field">
                <label htmlFor={`builder-field-characters.${selectedId}.emotions.add`}>{t('builder.characters.emotions.add')}</label>
                <input
                  id={`builder-field-characters.${selectedId}.emotions.add`}
                  value={emotionInput}
                  onChange={(e) => {
                    setEmotionInput(e.target.value)
                    setEmotionError(null)
                  }}
                  onKeyDown={handleEmotionKeyDown}
                  aria-invalid={emotionError ? 'true' : undefined}
                />
                <button type="button" onClick={() => addEmotion(selectedId, emotionInput)}>
                  {t('builder.characters.emotions.add')}
                </button>
                {emotionError ? (
                  <p role="alert" className="field-error">
                    {emotionError}
                  </p>
                ) : null}
              </div>

              {suggestedEmotions.length > 0 ? (
                <div role="group" aria-label={t('builder.characters.emotions.suggest')} className="builder-characters-emotionSuggestions">
                  {suggestedEmotions.map((emotion) => (
                    <button type="button" key={emotion} onClick={() => addEmotion(selectedId, emotion)}>
                      {emotion}
                    </button>
                  ))}
                </div>
              ) : null}
            </fieldset>
          </div>
        ) : null}
      </div>
      )}

      {characterIds.length > 0 ? (
        <fieldset className="builder-field builder-powerTiers">
          <legend>{t('builder.characters.powerTiers.legend')}</legend>
          <p className="field-hint">{t('builder.characters.powerTiers.hint')}</p>

          <div
            className="builder-powerTiers-row builder-powerTiers-unranked"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => handleTierDrop(e, null)}
          >
            <span className="builder-powerTiers-rowLabel">{t('builder.characters.powerTiers.unranked')}</span>
            <div role="list" className="builder-tags-list">
              {characterIds.filter((id) => draft.characters[id].power_tier === null).map(tierChip)}
            </div>
          </div>

          {Array.from({ length: tierCount }, (_, i) => i + 1).map((tier) => (
            <div
              key={tier}
              className="builder-powerTiers-row"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => handleTierDrop(e, tier)}
            >
              <span className="builder-powerTiers-rowLabel">{t('builder.characters.powerTiers.tier', { tier })}</span>
              <div role="list" className="builder-tags-list">
                {characterIds.filter((id) => draft.characters[id].power_tier === tier).map(tierChip)}
              </div>
            </div>
          ))}

          <button type="button" onClick={() => setTierFloor(tierCount + 1)}>
            {t('builder.characters.powerTiers.add')}
          </button>
        </fieldset>
      ) : null}

      <dialog
        ref={createDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-characters-create-title"
        onClose={() => setCreateOpen(false)}
        onCancel={(event) => {
          event.preventDefault()
          closeCreate()
        }}
      >
        <h2 id="builder-characters-create-title">{t('builder.characters.create.title')}</h2>
        <form onSubmit={handleCreateSubmit}>
          <div className="builder-field">
            <label htmlFor="builder-characters-create-id">{t('builder.characters.create.idLabel')}</label>
            <input
              id="builder-characters-create-id"
              ref={createIdRef}
              value={createId}
              onChange={(e) => setCreateId(e.target.value)}
              aria-invalid={createError ? 'true' : undefined}
              aria-describedby="builder-characters-create-id-hint"
            />
            <p className="field-hint" id="builder-characters-create-id-hint">
              {t('builder.characters.create.idHint')}
            </p>
          </div>
          <div className="builder-field">
            <label htmlFor="builder-characters-create-name">{t('builder.characters.name')}</label>
            <input id="builder-characters-create-name" value={createName} onChange={(e) => setCreateName(e.target.value)} />
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
            <button type="submit">{t('builder.characters.create.submit')}</button>
          </div>
        </form>
      </dialog>

      <dialog
        ref={deleteDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-characters-delete-title"
        onClose={() => setDeleteTarget(null)}
        onCancel={(event) => {
          event.preventDefault()
          closeDelete()
        }}
      >
        <h2 id="builder-characters-delete-title">{t('builder.characters.delete.title', { name: deleteTargetName })}</h2>
        <p>{t('builder.characters.delete.body', { id: deleteTarget ?? '', sprite: deleteTargetSprite })}</p>
        <div className="builder-editor-dialog-actions">
          <button type="button" ref={deleteCancelRef} onClick={closeDelete}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={handleDeleteConfirm}>
            {t('builder.characters.delete')}
          </button>
        </div>
      </dialog>
    </div>
  )
}
