import { useEffect, useRef, useState } from 'react'
import type { TabProps } from '../../screens/BuilderEditorScreen'
import { t } from '../../i18n'
import { parseGuidedWorld, serializeGuidedWorld, WORLD_HEADINGS, type GuidedWorld } from '../../builder/worldMarkdown'
import '../../screens/builderEditor.css'

const EMPTY_GUIDED: GuidedWorld = { universe: '', tone: '', rules: '', lore: [] }

const KNOWN_VARIABLES = ['player', 'start', 'scenario'] as const

// Mirrors backend/app/compact.py estimate_tokens (math.ceil(len(text) / 4)).
const WORLD_TOKEN_WARN = 2000

const GUIDED_FIELDS: readonly {
  key: 'universe' | 'tone' | 'rules'
  labelKey: 'builder.world.universe' | 'builder.world.tone' | 'builder.world.rules'
  hintKey: 'builder.world.universe.hint' | 'builder.world.tone.hint' | 'builder.world.rules.hint'
  required: boolean
}[] = [
  { key: 'universe', labelKey: 'builder.world.universe', hintKey: 'builder.world.universe.hint', required: true },
  { key: 'tone', labelKey: 'builder.world.tone', hintKey: 'builder.world.tone.hint', required: false },
  { key: 'rules', labelKey: 'builder.world.rules', hintKey: 'builder.world.rules.hint', required: false },
]

const RESERVED_TITLES = new Set<string>((WORLD_HEADINGS as readonly string[]).map((h) => h.toLowerCase()))

function isReservedTitle(title: string): boolean {
  return RESERVED_TITLES.has(title.trim().toLowerCase())
}

function shiftPendingTitlesAfterRemoval(pending: Record<number, string>, removedIndex: number): Record<number, string> {
  const next: Record<number, string> = {}
  for (const [key, value] of Object.entries(pending)) {
    const index = Number(key)
    if (index < removedIndex) next[index] = value
    else if (index > removedIndex) next[index - 1] = value
  }
  return next
}

function extractVariableNames(text: string): string[] {
  return Array.from(new Set(Array.from(text.matchAll(/\{\{\s*(\w+)\s*\}\}/g), (m) => m[1])))
}

export function WorldTab(props: TabProps) {
  const { draft, onChange, errors, goToTab } = props
  const meta = draft.meta

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const addLoreButtonRef = useRef<HTMLButtonElement>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [switchedNotice, setSwitchedNotice] = useState(false)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const [pendingTitles, setPendingTitles] = useState<Record<number, string>>({})
  const [announcement, setAnnouncement] = useState('')

  const parsedGuided = parseGuidedWorld(draft.world)
  const isFallback = meta.world_mode === 'guided' && parsedGuided === null
  const mode: 'guided' | 'custom' = meta.world_mode === 'guided' && !isFallback ? 'guided' : 'custom'
  const guidedFields = mode === 'guided' && parsedGuided ? parsedGuided : EMPTY_GUIDED

  useEffect(() => {
    if (confirmOpen) {
      dialogRef.current?.showModal()
      cancelRef.current?.focus()
    } else {
      dialogRef.current?.close()
    }
  }, [confirmOpen])

  function fieldError(field: string): string | null {
    return errors.find((e) => e.tab === 'world' && e.field === field)?.message ?? null
  }

  function loreTitleError(index: number, savedTitle: string): string | null {
    if (savedTitle === '' && index in pendingTitles) {
      return t('builder.world.lore.title.reserved', { title: pendingTitles[index].trim() })
    }
    return fieldError(`world.lore.${index}.title`)
  }

  function updateMeta(patch: Partial<typeof meta>) {
    onChange({ ...draft, meta: { ...meta, ...patch } })
  }

  function updateGuidedField(field: 'universe' | 'tone' | 'rules', value: string) {
    const next = { ...guidedFields, [field]: value }
    onChange({ ...draft, world: serializeGuidedWorld(next) })
  }

  function updateLoreTitle(index: number, value: string) {
    if (isReservedTitle(value)) {
      setPendingTitles((prev) => ({ ...prev, [index]: value }))
      const nextLore = guidedFields.lore.map((block, i) => (i === index ? { ...block, title: '' } : block))
      onChange({ ...draft, world: serializeGuidedWorld({ ...guidedFields, lore: nextLore }) })
      return
    }
    setPendingTitles((prev) => {
      if (!(index in prev)) return prev
      const next = { ...prev }
      delete next[index]
      return next
    })
    const nextLore = guidedFields.lore.map((block, i) => (i === index ? { ...block, title: value } : block))
    onChange({ ...draft, world: serializeGuidedWorld({ ...guidedFields, lore: nextLore }) })
  }

  function updateLoreBody(index: number, value: string) {
    const nextLore = guidedFields.lore.map((block, i) => (i === index ? { ...block, body: value } : block))
    onChange({ ...draft, world: serializeGuidedWorld({ ...guidedFields, lore: nextLore }) })
  }

  function addLore() {
    const nextLore = [...guidedFields.lore, { title: '', body: '' }]
    const newIndex = nextLore.length - 1
    onChange({ ...draft, world: serializeGuidedWorld({ ...guidedFields, lore: nextLore }) })
    setAnnouncement(t('builder.world.lore.added', { index: newIndex + 1 }))
    requestAnimationFrame(() => {
      document.getElementById(`builder-field-world.lore.${newIndex}.title`)?.focus()
    })
  }

  function removeLore(index: number) {
    const nextLore = guidedFields.lore.filter((_, i) => i !== index)
    onChange({ ...draft, world: serializeGuidedWorld({ ...guidedFields, lore: nextLore }) })
    setPendingTitles((prev) => shiftPendingTitlesAfterRemoval(prev, index))
    setAnnouncement(t('builder.world.lore.removed', { index: index + 1 }))
    requestAnimationFrame(() => {
      if (nextLore.length === 0) {
        addLoreButtonRef.current?.focus()
        return
      }
      const focusIndex = index < nextLore.length ? index : nextLore.length - 1
      document.getElementById(`builder-field-world.lore.${focusIndex}.title`)?.focus()
    })
  }

  function updateCustomText(value: string) {
    onChange({ ...draft, world: value })
  }

  function handleSelectCustom() {
    if (mode === 'custom') return
    setPendingTitles({})
    setSwitchedNotice(true)
    updateMeta({ world_mode: 'custom' })
  }

  function handleSelectGuided() {
    if (mode === 'guided') return
    setConfirmOpen(true)
  }

  function handleConfirmSwitchToGuided() {
    const parsed = parseGuidedWorld(draft.world)
    const fields = parsed ?? EMPTY_GUIDED
    setConfirmOpen(false)
    setSwitchedNotice(false)
    setPendingTitles({})
    onChange({ ...draft, world: serializeGuidedWorld(fields), meta: { ...meta, world_mode: 'guided' } })
  }

  function handleCancelSwitchToGuided() {
    setConfirmOpen(false)
  }

  function handleKeepCustom() {
    updateMeta({ world_mode: 'custom' })
  }

  function insertVariable(name: string) {
    const el = textareaRef.current
    const text = draft.world
    const start = el?.selectionStart ?? text.length
    const end = el?.selectionEnd ?? text.length
    const inserted = `{{${name}}}`
    const nextText = text.slice(0, start) + inserted + text.slice(end)
    updateCustomText(nextText)
    const nextPos = start + inserted.length
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(nextPos, nextPos)
    })
  }

  const worldTokens = Math.ceil(draft.world.length / 4)
  const worldError = fieldError('world')
  const universeError = fieldError('universe')
  const unknownVariables = extractVariableNames(draft.world).filter(
    (name) => !(KNOWN_VARIABLES as readonly string[]).includes(name),
  )

  return (
    <div className="builder-world-tab">
      <h2>{t('builder.world.heading')}</h2>

      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>

      <div className="builder-field">
        <p id="builder-world-mode-label">{t('builder.world.mode.label')}</p>
        <div role="radiogroup" aria-labelledby="builder-world-mode-label" className="builder-world-mode-toggle">
          <button type="button" role="radio" aria-checked={mode === 'guided'} onClick={handleSelectGuided}>
            {t('builder.world.mode.guided')}
          </button>
          <button type="button" role="radio" aria-checked={mode === 'custom'} onClick={handleSelectCustom}>
            {t('builder.world.mode.custom')}
          </button>
        </div>
      </div>

      {isFallback ? (
        <div className="builder-world-fallback">
          <p className="builder-world-fallback-title">{t('builder.world.mode.fallback.title')}</p>
          <p className="field-hint">{t('builder.world.mode.fallback.body')}</p>
          <button type="button" onClick={handleKeepCustom}>
            {t('builder.world.mode.fallback.keepCustom')}
          </button>
        </div>
      ) : null}

      <p className="field-hint">{t('builder.world.tokens', { count: worldTokens })}</p>
      <p className="field-hint">{t('builder.world.tokens.hint')}</p>
      <p role="status" aria-live="polite">
        {worldTokens > WORLD_TOKEN_WARN ? t('builder.world.tokens.over', { max: WORLD_TOKEN_WARN }) : ''}
      </p>

      {mode === 'guided' ? (
        <div className="builder-world-guided">
          {GUIDED_FIELDS.map((field) => {
            const value = guidedFields[field.key]
            const inputId = `builder-field-${field.key}`
            const hintId = `${inputId}-hint`
            const errorId = `${inputId}-error`
            const fieldErrorMessage = field.required ? universeError : null
            return (
              <div className="builder-field" key={field.key}>
                <label htmlFor={inputId}>{t(field.labelKey)}</label>
                <textarea
                  id={inputId}
                  className="builder-field-textarea"
                  value={value}
                  onChange={(e) => updateGuidedField(field.key, e.target.value)}
                  aria-invalid={fieldErrorMessage ? 'true' : undefined}
                  aria-describedby={[fieldErrorMessage ? errorId : null, hintId].filter(Boolean).join(' ') || undefined}
                />
                <p className="field-hint" id={hintId}>
                  {t(field.hintKey)}
                </p>
                {fieldErrorMessage ? (
                  <p role="alert" id={errorId} className="field-error">
                    {fieldErrorMessage}
                  </p>
                ) : null}
              </div>
            )
          })}

          <p className="field-hint">{t('builder.world.guided.movedHint')}</p>
          <button type="button" className="builder-linkButton" onClick={() => goToTab('starts')}>
            {t('builder.world.guided.goToStarts')}
          </button>

          <fieldset className="builder-world-lore">
            <legend>{t('builder.world.lore.legend')}</legend>
            <p className="field-hint">{t('builder.world.lore.hint')}</p>
            {guidedFields.lore.length === 0 ? (
              <p className="field-hint">{t('builder.world.lore.empty')}</p>
            ) : (
              guidedFields.lore.map((block, index) => {
                const titleId = `builder-field-world.lore.${index}.title`
                const titleHintId = `${titleId}-hint`
                const titleErrorId = `${titleId}-error`
                const bodyId = `builder-field-world.lore.${index}.body`
                const displayedTitle = block.title === '' ? (pendingTitles[index] ?? '') : block.title
                const titleErrorMessage = loreTitleError(index, block.title)
                return (
                  <div className="builder-world-lore-block" key={index}>
                    <div className="builder-field builder-world-lore-titleField">
                      <label htmlFor={titleId}>{t('builder.world.lore.titleLabel', { index: index + 1 })}</label>
                      <input
                        id={titleId}
                        type="text"
                        value={displayedTitle}
                        onChange={(e) => updateLoreTitle(index, e.target.value)}
                        aria-invalid={titleErrorMessage ? 'true' : undefined}
                        aria-describedby={[titleHintId, titleErrorMessage ? titleErrorId : null].filter(Boolean).join(' ')}
                      />
                      <p className="field-hint" id={titleHintId}>
                        {t('builder.world.lore.title.hint')}
                      </p>
                      {titleErrorMessage ? (
                        <p role="alert" id={titleErrorId} className="field-error">
                          {titleErrorMessage}
                        </p>
                      ) : null}
                    </div>
                    <div className="builder-field builder-world-lore-bodyField">
                      <label htmlFor={bodyId}>{t('builder.world.lore.bodyLabel', { index: index + 1 })}</label>
                      <textarea
                        id={bodyId}
                        className="builder-field-textarea"
                        rows={6}
                        value={block.body}
                        onChange={(e) => updateLoreBody(index, e.target.value)}
                      />
                    </div>
                    <button
                      type="button"
                      className="builder-world-lore-removeButton"
                      aria-label={t('builder.world.lore.remove', { index: index + 1 })}
                      onClick={() => removeLore(index)}
                    >
                      {t('common.remove')}
                    </button>
                  </div>
                )
              })
            )}
            <button type="button" ref={addLoreButtonRef} onClick={addLore}>
              {t('builder.world.lore.add')}
            </button>
          </fieldset>
        </div>
      ) : (
        <div className="builder-world-custom">
          {switchedNotice ? <p className="field-hint">{t('builder.world.mode.switchToCustom')}</p> : null}
          <div className="builder-field">
            <label htmlFor="builder-field-world">{t('builder.world.custom.label')}</label>
            <textarea
              id="builder-field-world"
              ref={textareaRef}
              className="builder-field-textarea builder-world-custom-textarea"
              rows={20}
              value={draft.world}
              onChange={(e) => updateCustomText(e.target.value)}
              aria-invalid={worldError ? 'true' : undefined}
              aria-describedby={
                [worldError ? 'builder-field-world-error' : null, 'builder-field-world-hint'].filter(Boolean).join(' ') ||
                undefined
              }
            />
            <p className="field-hint" id="builder-field-world-hint">
              {t('builder.world.custom.hint')}
            </p>
            {worldError ? (
              <p role="alert" id="builder-field-world-error" className="field-error">
                {worldError}
              </p>
            ) : null}
          </div>

          {unknownVariables.length > 0 ? (
            <div role="status" className="builder-world-variables-warning">
              {unknownVariables.map((name) => (
                <p key={name}>{t('builder.world.variables.unknown', { name: `{{${name}}}` })}</p>
              ))}
            </div>
          ) : null}

          <fieldset className="builder-world-variables">
            <legend>{t('builder.world.variables.title')}</legend>
            <ul>
              {KNOWN_VARIABLES.map((name) => (
                <li key={name}>
                  <span>{`{{${name}}}`}</span>
                  <span className="field-hint">{t(`builder.world.variables.${name}`)}</span>
                  <button type="button" onClick={() => insertVariable(name)}>
                    {t('builder.world.variables.insert', { name })}
                  </button>
                </li>
              ))}
            </ul>
          </fieldset>
        </div>
      )}

      <dialog
        ref={dialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-world-switchToGuided-title"
        onClose={() => setConfirmOpen(false)}
        onCancel={(event) => {
          event.preventDefault()
          setConfirmOpen(false)
        }}
      >
        <h2 id="builder-world-switchToGuided-title">{t('builder.world.mode.switchToGuidedTitle')}</h2>
        <p>{t('builder.world.mode.switchToGuidedBody')}</p>
        <div className="builder-editor-dialog-actions">
          <button type="button" ref={cancelRef} onClick={handleCancelSwitchToGuided}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={handleConfirmSwitchToGuided}>
            {t('builder.world.mode.switchToGuidedSubmit')}
          </button>
        </div>
      </dialog>
    </div>
  )
}
