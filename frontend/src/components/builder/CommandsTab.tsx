import { useEffect, useRef, useState } from 'react'
import type { TabProps } from '../../screens/BuilderEditorScreen'
import type { CommandDoc } from '../../api'
import { t } from '../../i18n'
import { EmptyState } from '../EmptyState'
import '../../screens/builderEditor.css'

function nextSuggestedCommandName(existing: readonly string[]): string {
  let n = 1
  while (existing.includes(`command-${n}`)) n += 1
  return `command-${n}`
}

function newCommand(name: string): CommandDoc {
  return { name, description: '', prompt: '' }
}

export function CommandsTab(props: TabProps) {
  const { draft, onChange, errors } = props

  const [selectedIndex, setSelectedIndex] = useState<number>(() => {
    const withError = draft.commands.findIndex((_, i) =>
      errors.some((e) => e.tab === 'commands' && e.field.startsWith(`commands.${i}.`)),
    )
    return withError >= 0 ? withError : 0
  })
  const [announcement, setAnnouncement] = useState('')

  const createTriggerRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (selectedIndex > draft.commands.length - 1) {
      setSelectedIndex(Math.max(0, draft.commands.length - 1))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.commands.length])

  function fieldError(field: string): string | null {
    return errors.find((e) => e.tab === 'commands' && e.field === field)?.message ?? null
  }

  function commandHasError(i: number): boolean {
    return errors.some((e) => e.tab === 'commands' && e.field.startsWith(`commands.${i}.`))
  }

  function commandLabelOf(command: CommandDoc): string {
    return command.name.trim() || t('builder.commands.unnamed')
  }

  function updateCommand(index: number, patch: Partial<CommandDoc>) {
    onChange({ ...draft, commands: draft.commands.map((command, i) => (i === index ? { ...command, ...patch } : command)) })
  }

  function selectCommand(index: number) {
    if (index === selectedIndex) return
    setSelectedIndex(index)
    setAnnouncement(t('builder.detail.selected', { name: commandLabelOf(draft.commands[index]) }))
    requestAnimationFrame(() => {
      document.getElementById(`builder-field-commands.${index}.name`)?.focus()
    })
  }

  function createCommand() {
    const name = nextSuggestedCommandName(draft.commands.map((c) => c.name))
    const newIndex = draft.commands.length
    onChange({ ...draft, commands: [...draft.commands, newCommand(name)] })
    setSelectedIndex(newIndex)
    setAnnouncement(t('builder.commands.added', { name }))
    requestAnimationFrame(() => {
      document.getElementById(`builder-field-commands.${newIndex}.name`)?.focus()
    })
  }

  function removeCommand(index: number) {
    const removedLabel = commandLabelOf(draft.commands[index])
    const nextCommands = draft.commands.filter((_, i) => i !== index)
    onChange({ ...draft, commands: nextCommands })
    setAnnouncement(t('builder.commands.removed', { name: removedLabel }))
    if (nextCommands.length === 0) {
      setSelectedIndex(0)
      requestAnimationFrame(() => createTriggerRef.current?.focus())
      return
    }
    const focusIndex = index < nextCommands.length ? index : nextCommands.length - 1
    setSelectedIndex(focusIndex)
    requestAnimationFrame(() => {
      document.getElementById(`builder-field-commands.${focusIndex}.name`)?.focus()
    })
  }

  const selectedCommand: CommandDoc | undefined = draft.commands[selectedIndex]

  return (
    <div className="builder-commands-tab">
      <h2>{t('builder.commands.heading')}</h2>

      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>

      <p className="field-hint">{t('builder.commands.playGuideHint')}</p>
      <p className="field-hint">{t('builder.commands.globalsHint')}</p>

      {draft.commands.length === 0 ? (
        <EmptyState
          title={t('builder.commands.empty.title')}
          body={t('builder.commands.empty.body')}
          action={
            <button type="button" ref={createTriggerRef} onClick={createCommand}>
              {t('builder.commands.create')}
            </button>
          }
        />
      ) : (
        <div className="builder-masterDetail">
          <div className="builder-commands-list">
            <p id="builder-commands-listLabel" className="builder-list-label">
              {t('builder.commands.listLabel')}
            </p>
            <ul className="builder-list" aria-labelledby="builder-commands-listLabel">
              {draft.commands.map((command, i) => {
                const hasError = commandHasError(i)
                const trimmedName = command.name.trim()
                return (
                  <li
                    key={i}
                    className={[i === selectedIndex ? 'is-selected' : '', hasError ? 'is-invalid' : ''].filter(Boolean).join(' ')}
                  >
                    <button
                      type="button"
                      id={`builder-commands-listItem-${i}`}
                      className="builder-list-item"
                      aria-current={i === selectedIndex || undefined}
                      onClick={() => selectCommand(i)}
                    >
                      <span className="builder-commands-listItemText">
                        {trimmedName ? (
                          <span className="builder-tag-chip builder-commands-invocation">
                            {t('builder.commands.invocation', { name: trimmedName })}
                          </span>
                        ) : (
                          <span>{t('builder.commands.unnamed')}</span>
                        )}
                        <span className="field-hint">{command.description}</span>
                      </span>
                      {hasError ? <span className="visually-hidden">{t('builder.starts.itemInvalid')}</span> : null}
                    </button>
                    <button
                      type="button"
                      aria-label={t('builder.commands.remove.title', { name: commandLabelOf(command) })}
                      onClick={() => removeCommand(i)}
                    >
                      {t('common.remove')}
                    </button>
                  </li>
                )
              })}
            </ul>
            <button type="button" ref={createTriggerRef} onClick={createCommand}>
              {t('builder.commands.create')}
            </button>
          </div>

          {selectedCommand ? (
            <div className="builder-commands-detail">
              <div className="builder-field">
                <label htmlFor={`builder-field-commands.${selectedIndex}.name`}>{t('builder.commands.name')}</label>
                <input
                  id={`builder-field-commands.${selectedIndex}.name`}
                  value={selectedCommand.name}
                  onChange={(e) => updateCommand(selectedIndex, { name: e.target.value })}
                  onBlur={(e) => updateCommand(selectedIndex, { name: e.target.value.trim() })}
                  aria-invalid={fieldError(`commands.${selectedIndex}.name`) ? 'true' : undefined}
                  aria-describedby={
                    [
                      fieldError(`commands.${selectedIndex}.name`) ? `builder-field-commands.${selectedIndex}.name-error` : null,
                      `builder-field-commands.${selectedIndex}.name-hint`,
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                />
                <p className="field-hint" id={`builder-field-commands.${selectedIndex}.name-hint`}>
                  {t('builder.commands.name.hint')}
                </p>
                {fieldError(`commands.${selectedIndex}.name`) ? (
                  <p role="alert" id={`builder-field-commands.${selectedIndex}.name-error`} className="field-error">
                    {fieldError(`commands.${selectedIndex}.name`)}
                  </p>
                ) : null}
              </div>

              <p className="builder-commands-invocation">
                {selectedCommand.name.trim() ? (
                  <span className="builder-tag-chip">{t('builder.commands.invocation', { name: selectedCommand.name.trim() })}</span>
                ) : (
                  t('builder.commands.invocation.empty')
                )}
              </p>

              <div className="builder-field">
                <label htmlFor={`builder-field-commands.${selectedIndex}.description`}>{t('builder.commands.description')}</label>
                <input
                  id={`builder-field-commands.${selectedIndex}.description`}
                  value={selectedCommand.description}
                  onChange={(e) => updateCommand(selectedIndex, { description: e.target.value })}
                  onBlur={(e) => updateCommand(selectedIndex, { description: e.target.value.trim() })}
                  aria-invalid={fieldError(`commands.${selectedIndex}.description`) ? 'true' : undefined}
                  aria-describedby={
                    [
                      fieldError(`commands.${selectedIndex}.description`)
                        ? `builder-field-commands.${selectedIndex}.description-error`
                        : null,
                      `builder-field-commands.${selectedIndex}.description-hint`,
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                />
                <p className="field-hint" id={`builder-field-commands.${selectedIndex}.description-hint`}>
                  {t('builder.commands.description.hint')}
                </p>
                {fieldError(`commands.${selectedIndex}.description`) ? (
                  <p role="alert" id={`builder-field-commands.${selectedIndex}.description-error`} className="field-error">
                    {fieldError(`commands.${selectedIndex}.description`)}
                  </p>
                ) : null}
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-commands.${selectedIndex}.prompt`}>{t('builder.commands.prompt')}</label>
                <textarea
                  id={`builder-field-commands.${selectedIndex}.prompt`}
                  className="builder-field-textarea"
                  rows={8}
                  value={selectedCommand.prompt}
                  onChange={(e) => updateCommand(selectedIndex, { prompt: e.target.value })}
                  aria-invalid={fieldError(`commands.${selectedIndex}.prompt`) ? 'true' : undefined}
                  aria-describedby={
                    [
                      fieldError(`commands.${selectedIndex}.prompt`) ? `builder-field-commands.${selectedIndex}.prompt-error` : null,
                      `builder-field-commands.${selectedIndex}.prompt-hint`,
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                />
                <p className="field-hint" id={`builder-field-commands.${selectedIndex}.prompt-hint`}>
                  {t('builder.commands.prompt.hint')}
                </p>
                {fieldError(`commands.${selectedIndex}.prompt`) ? (
                  <p role="alert" id={`builder-field-commands.${selectedIndex}.prompt-error`} className="field-error">
                    {fieldError(`commands.${selectedIndex}.prompt`)}
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
