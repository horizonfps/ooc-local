import { useEffect, useRef, useState } from 'react'
import type { TabProps } from '../../screens/BuilderEditorScreen'
import { t } from '../../i18n'
import { parseGuidedWorld, serializeGuidedWorld, type GuidedWorld } from '../../builder/worldMarkdown'
import '../../screens/builderEditor.css'

const EMPTY_GUIDED: GuidedWorld = { universe: '', tone: '', rules: '', conflict: '', mission: '' }

const KNOWN_VARIABLES = ['player', 'start', 'scenario'] as const

const GUIDED_FIELDS: readonly { key: keyof GuidedWorld; labelKey: 'builder.world.universe' | 'builder.world.tone' | 'builder.world.rules' | 'builder.world.conflict' | 'builder.world.mission'; hintKey: 'builder.world.universe.hint' | 'builder.world.tone.hint' | 'builder.world.rules.hint' | 'builder.world.conflict.hint' | 'builder.world.mission.hint'; required: boolean }[] = [
  { key: 'universe', labelKey: 'builder.world.universe', hintKey: 'builder.world.universe.hint', required: true },
  { key: 'tone', labelKey: 'builder.world.tone', hintKey: 'builder.world.tone.hint', required: false },
  { key: 'rules', labelKey: 'builder.world.rules', hintKey: 'builder.world.rules.hint', required: false },
  { key: 'conflict', labelKey: 'builder.world.conflict', hintKey: 'builder.world.conflict.hint', required: false },
  { key: 'mission', labelKey: 'builder.world.mission', hintKey: 'builder.world.mission.hint', required: false },
]

function extractVariableNames(text: string): string[] {
  return Array.from(new Set(Array.from(text.matchAll(/\{\{(\w+)\}\}/g), (m) => m[1])))
}

export function WorldTab(props: TabProps) {
  const { draft, onChange, errors } = props
  const meta = draft.meta

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [switchedNotice, setSwitchedNotice] = useState(false)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)

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

  function updateMeta(patch: Partial<typeof meta>) {
    onChange({ ...draft, meta: { ...meta, ...patch } })
  }

  function updateGuidedField(field: keyof GuidedWorld, value: string) {
    const next = { ...guidedFields, [field]: value }
    onChange({ ...draft, world: serializeGuidedWorld(next) })
  }

  function updateCustomText(value: string) {
    onChange({ ...draft, world: value })
  }

  function handleSelectCustom() {
    if (mode === 'custom') return
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

  const worldError = fieldError('world')
  const universeError = fieldError('universe')
  const unknownVariables = extractVariableNames(draft.world).filter(
    (name) => !(KNOWN_VARIABLES as readonly string[]).includes(name),
  )

  return (
    <div className="builder-world-tab">
      <h2>{t('builder.world.heading')}</h2>

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
