import { useEffect, useRef, useState } from 'react'
import type { TabProps } from '../../screens/BuilderEditorScreen'
import type { LoreEntryDoc } from '../../api'
import { parseGuidedWorld, serializeGuidedWorld, type LoreBlock } from '../../builder/worldMarkdown'
import { slugify } from '../../screens/BuilderListScreen'
import { t } from '../../i18n'
import { EmptyState } from '../EmptyState'
import '../../screens/builderEditor.css'

const ID_RE = /^[a-z0-9-]+$/

function normalizeKeyword(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
}

function newEntry(title: string): LoreEntryDoc {
  return { title, keywords: [], body: '', scope: 'keyword', priority: 0, enabled: true }
}

function dedupeId(base: string, used: Set<string>): string {
  if (!used.has(base)) return base
  let n = 2
  while (used.has(`${base}-${n}`)) n += 1
  return `${base}-${n}`
}

export function LorebookTab(props: TabProps) {
  const { draft, onChange, errors, goToTab } = props
  const entryIds = Object.keys(draft.lorebook)

  const [selectedId, setSelectedId] = useState<string>(() => {
    const withError = entryIds.find((id) =>
      errors.some((e) => e.tab === 'lorebook' && (e.field === `lorebook.${id}` || e.field.startsWith(`lorebook.${id}.`))),
    )
    return withError ?? entryIds[0] ?? ''
  })
  const [announcement, setAnnouncement] = useState('')

  const [createOpen, setCreateOpen] = useState(false)
  const [createId, setCreateId] = useState('')
  const [createTitle, setCreateTitle] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const [splitConfirmOpen, setSplitConfirmOpen] = useState(false)

  const [keywordInput, setKeywordInput] = useState('')
  const [keywordDuplicate, setKeywordDuplicate] = useState<string | null>(null)

  const titleFieldRef = useRef<HTMLInputElement>(null)
  const createDialogRef = useRef<HTMLDialogElement>(null)
  const createIdRef = useRef<HTMLInputElement>(null)
  const createTriggerRef = useRef<HTMLButtonElement>(null)
  const deleteDialogRef = useRef<HTMLDialogElement>(null)
  const deleteCancelRef = useRef<HTMLButtonElement>(null)
  const splitDialogRef = useRef<HTMLDialogElement>(null)
  const splitCancelRef = useRef<HTMLButtonElement>(null)
  const splitTriggerRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!(selectedId in draft.lorebook)) {
      setSelectedId(entryIds[0] ?? '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.lorebook])

  useEffect(() => {
    setKeywordInput('')
    setKeywordDuplicate(null)
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

  useEffect(() => {
    if (splitConfirmOpen) {
      splitDialogRef.current?.showModal()
      splitCancelRef.current?.focus()
    } else {
      splitDialogRef.current?.close()
    }
  }, [splitConfirmOpen])

  function fieldError(field: string): string | null {
    return errors.find((e) => e.tab === 'lorebook' && e.field === field)?.message ?? null
  }

  function entryHasError(id: string): boolean {
    return errors.some((e) => e.tab === 'lorebook' && (e.field === `lorebook.${id}` || e.field.startsWith(`lorebook.${id}.`)))
  }

  function entryLabelOf(entry: LoreEntryDoc, id: string): string {
    return entry.title.trim() || id
  }

  function updateEntry(id: string, patch: Partial<LoreEntryDoc>) {
    onChange({ ...draft, lorebook: { ...draft.lorebook, [id]: { ...draft.lorebook[id], ...patch } } })
  }

  function selectEntry(id: string) {
    if (id === selectedId) return
    setSelectedId(id)
    setAnnouncement(t('builder.detail.selected', { name: entryLabelOf(draft.lorebook[id], id) }))
    requestAnimationFrame(() => titleFieldRef.current?.focus())
  }

  function commitKeyword() {
    const raw = keywordInput.trim()
    setKeywordInput('')
    if (!raw) return
    const entry = draft.lorebook[selectedId]
    const normalized = normalizeKeyword(raw)
    if (entry.keywords.some((k) => normalizeKeyword(k) === normalized)) {
      setKeywordDuplicate(t('builder.identity.tags.duplicate', { tag: raw }))
      return
    }
    setKeywordDuplicate(null)
    updateEntry(selectedId, { keywords: [...entry.keywords, raw] })
  }

  function handleKeywordKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      commitKeyword()
    } else if (event.key === 'Backspace' && keywordInput === '' && draft.lorebook[selectedId].keywords.length > 0) {
      updateEntry(selectedId, { keywords: draft.lorebook[selectedId].keywords.slice(0, -1) })
    }
  }

  function removeKeyword(id: string, keyword: string) {
    updateEntry(id, { keywords: draft.lorebook[id].keywords.filter((k) => k !== keyword) })
  }

  function openCreate() {
    setCreateId('')
    setCreateTitle('')
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
    if (id in draft.lorebook) {
      setCreateError(t('builder.field.slugTaken', { slug: id }))
      return
    }
    onChange({ ...draft, lorebook: { ...draft.lorebook, [id]: newEntry(createTitle.trim()) } })
    setCreateOpen(false)
    setSelectedId(id)
    requestAnimationFrame(() => {
      document.getElementById(`builder-field-lorebook.${id}.title`)?.focus()
    })
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
    const index = entryIds.indexOf(id)
    const nextLorebook = { ...draft.lorebook }
    delete nextLorebook[id]
    const nextIds = Object.keys(nextLorebook)
    onChange({ ...draft, lorebook: nextLorebook })
    setDeleteTarget(null)
    if (nextIds.length === 0) {
      setSelectedId('')
      requestAnimationFrame(() => createTriggerRef.current?.focus())
      return
    }
    const focusIndex = index < nextIds.length ? index : nextIds.length - 1
    const nextSelected = nextIds[focusIndex]
    // Deleting another entry keeps the current selection.
    if (id === selectedId) setSelectedId(nextSelected)
    requestAnimationFrame(() => {
      document.getElementById(`builder-lorebook-listItem-${nextSelected}`)?.focus()
    })
  }

  const guided = draft.meta.world_mode === 'guided' ? parseGuidedWorld(draft.world) : null
  const splittableCount = guided === null ? 0 : guided.lore.filter((block) => block.title.trim() !== '').length
  const splitState: 'unavailable' | 'empty' | 'available' =
    guided === null ? 'unavailable' : splittableCount === 0 ? 'empty' : 'available'

  function openSplitConfirm() {
    setSplitConfirmOpen(true)
  }

  function closeSplitConfirm() {
    setSplitConfirmOpen(false)
    splitTriggerRef.current?.focus()
  }

  function applySplit() {
    if (!guided) return
    const usedIds = new Set(entryIds)
    const newEntries: Record<string, LoreEntryDoc> = {}
    const createdIds: string[] = []
    const remainingLore: LoreBlock[] = []
    let skippedCount = 0

    for (const block of guided.lore) {
      const title = block.title.trim()
      if (title === '') {
        remainingLore.push(block)
        skippedCount += 1
        continue
      }
      let base = slugify(title)
      if (base === '') base = 'lore'
      const id = dedupeId(base, usedIds)
      usedIds.add(id)
      newEntries[id] = { title, keywords: [title], body: block.body, scope: 'keyword', priority: 0, enabled: true }
      createdIds.push(id)
    }

    const nextWorld = serializeGuidedWorld({ ...guided, lore: remainingLore })
    onChange({ ...draft, lorebook: { ...draft.lorebook, ...newEntries }, world: nextWorld })
    setSplitConfirmOpen(false)

    const doneMsg = t('builder.lorebook.split.done', { count: createdIds.length })
    const skippedMsg = skippedCount > 0 ? ` ${t('builder.lorebook.split.skipped', { count: skippedCount })}` : ''
    setAnnouncement(doneMsg + skippedMsg)

    if (createdIds.length > 0) {
      const firstId = createdIds[0]
      setSelectedId(firstId)
      requestAnimationFrame(() => {
        document.getElementById(`builder-field-lorebook.${firstId}.title`)?.focus()
      })
    } else {
      splitTriggerRef.current?.focus()
    }
  }

  const selectedEntry: LoreEntryDoc | undefined = draft.lorebook[selectedId]
  const deleteTargetName = deleteTarget !== null ? entryLabelOf(draft.lorebook[deleteTarget], deleteTarget) : ''
  const keywordsFieldError = selectedEntry ? fieldError(`lorebook.${selectedId}.keywords`) : null
  const keywordsHintId = `builder-field-lorebook.${selectedId}.keywords-hint`
  const keywordsErrorId = `builder-field-lorebook.${selectedId}.keywords-error`

  return (
    <div className="builder-lorebook-tab">
      <h2>{t('builder.lorebook.heading')}</h2>

      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>

      <div className="builder-lorebook-split">
        <p className="builder-lorebook-split-title">{t('builder.lorebook.split')}</p>
        {splitState === 'unavailable' ? (
          <>
            <p className="field-hint">{t('builder.lorebook.split.unavailable')}</p>
            <button type="button" className="builder-linkButton" onClick={() => goToTab('world')}>
              {t('builder.lorebook.split.goToWorld')}
            </button>
          </>
        ) : splitState === 'empty' ? (
          <>
            <p className="field-hint">{t('builder.lorebook.split.empty')}</p>
            <button type="button" className="builder-linkButton" onClick={() => goToTab('world')}>
              {t('builder.lorebook.split.goToWorld')}
            </button>
          </>
        ) : (
          <>
            <p className="field-hint">
              {guided && guided.lore.length === 1
                ? t('builder.lorebook.split.availableOne')
                : t('builder.lorebook.split.availableOther', { count: guided?.lore.length ?? 0 })}
            </p>
            <button type="button" ref={splitTriggerRef} onClick={openSplitConfirm}>
              {t('builder.lorebook.split')}
            </button>
          </>
        )}
      </div>

      {entryIds.length === 0 ? (
        <EmptyState
          title={t('builder.lorebook.empty.title')}
          body={t('builder.lorebook.empty.body')}
          action={
            <button type="button" ref={createTriggerRef} onClick={openCreate}>
              {t('builder.lorebook.create')}
            </button>
          }
        />
      ) : (
        <div className="builder-masterDetail">
          <div className="builder-lorebook-list">
            <p id="builder-lorebook-listLabel" className="builder-list-label">
              {t('builder.lorebook.listLabel')}
            </p>
            <ul className="builder-list" aria-labelledby="builder-lorebook-listLabel">
              {entryIds.map((id) => {
                const entry = draft.lorebook[id]
                const hasError = entryHasError(id)
                const keywordCount = entry.keywords.length
                return (
                  <li key={id} className={[id === selectedId ? 'is-selected' : '', hasError ? 'is-invalid' : ''].filter(Boolean).join(' ')}>
                    <button
                      type="button"
                      id={`builder-lorebook-listItem-${id}`}
                      className="builder-list-item"
                      aria-current={id === selectedId || undefined}
                      onClick={() => selectEntry(id)}
                    >
                      <span>{entryLabelOf(entry, id)}</span>
                      {entry.scope === 'always' ? (
                        <span className="builder-starts-badge">{t('builder.lorebook.alwaysBadge')}</span>
                      ) : null}
                      {!entry.enabled ? <span className="builder-starts-badge">{t('builder.lorebook.disabledBadge')}</span> : null}
                      <span className="field-hint">
                        {keywordCount === 0
                          ? t('builder.lorebook.keywordCountZero')
                          : keywordCount === 1
                            ? t('builder.lorebook.keywordCountOne')
                            : t('builder.lorebook.keywordCountOther', { count: keywordCount })}
                      </span>
                      {hasError ? <span className="visually-hidden">{t('builder.starts.itemInvalid')}</span> : null}
                    </button>
                    <button
                      type="button"
                      aria-label={t('builder.lorebook.delete.title', { title: entryLabelOf(entry, id) })}
                      onClick={() => openDelete(id)}
                    >
                      {t('builder.lorebook.delete')}
                    </button>
                  </li>
                )
              })}
            </ul>
            <button type="button" ref={createTriggerRef} onClick={openCreate}>
              {t('builder.lorebook.create')}
            </button>
          </div>

          {selectedEntry ? (
            <div className="builder-lorebook-detail">
              <div className="builder-field">
                <label htmlFor={`builder-field-lorebook.${selectedId}.title`}>{t('builder.lorebook.title')}</label>
                <input
                  id={`builder-field-lorebook.${selectedId}.title`}
                  ref={titleFieldRef}
                  value={selectedEntry.title}
                  onChange={(e) => updateEntry(selectedId, { title: e.target.value })}
                  onBlur={(e) => updateEntry(selectedId, { title: e.target.value.trim() })}
                  aria-invalid={fieldError(`lorebook.${selectedId}.title`) ? 'true' : undefined}
                  aria-describedby={
                    [
                      fieldError(`lorebook.${selectedId}.title`) ? `builder-field-lorebook.${selectedId}.title-error` : null,
                      `builder-field-lorebook.${selectedId}.title-hint`,
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                />
                <p className="field-hint" id={`builder-field-lorebook.${selectedId}.title-hint`}>
                  {t('builder.lorebook.title.hint')}
                </p>
                {fieldError(`lorebook.${selectedId}.title`) ? (
                  <p role="alert" id={`builder-field-lorebook.${selectedId}.title-error`} className="field-error">
                    {fieldError(`lorebook.${selectedId}.title`)}
                  </p>
                ) : null}
              </div>

              <div className="builder-field">
                <div
                  role="list"
                  className="builder-tags-list"
                  aria-describedby={
                    [keywordsFieldError ? keywordsErrorId : null, keywordsHintId].filter(Boolean).join(' ') || undefined
                  }
                >
                  {selectedEntry.keywords.map((keyword) => (
                    <span role="listitem" key={keyword} className="builder-tag-chip">
                      {keyword}
                      <button
                        type="button"
                        aria-label={t('builder.lorebook.keywords.remove', { keyword })}
                        onClick={() => removeKeyword(selectedId, keyword)}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                  <label htmlFor={`builder-field-lorebook.${selectedId}.keywords`} className="visually-hidden">
                    {t('builder.lorebook.keywords.add')}
                  </label>
                  <input
                    id={`builder-field-lorebook.${selectedId}.keywords`}
                    value={keywordInput}
                    onChange={(e) => {
                      setKeywordInput(e.target.value)
                      setKeywordDuplicate(null)
                    }}
                    onKeyDown={handleKeywordKeyDown}
                  />
                </div>
                <p className="field-hint" id={keywordsHintId}>
                  {selectedEntry.keywords.length === 0 ? t('builder.lorebook.keywords.empty') : t('builder.lorebook.keywords.hint')}
                </p>
                {keywordDuplicate ? (
                  <p role="alert" className="field-error">
                    {keywordDuplicate}
                  </p>
                ) : null}
                {keywordsFieldError ? (
                  <p role="alert" id={keywordsErrorId} className="field-error">
                    {keywordsFieldError}
                  </p>
                ) : null}
              </div>

              <div className="builder-field">
                <label htmlFor={`builder-field-lorebook.${selectedId}.body`}>{t('builder.lorebook.body')}</label>
                <textarea
                  id={`builder-field-lorebook.${selectedId}.body`}
                  className="builder-field-textarea"
                  rows={8}
                  value={selectedEntry.body}
                  onChange={(e) => updateEntry(selectedId, { body: e.target.value })}
                  aria-describedby={`builder-field-lorebook.${selectedId}.body-hint`}
                />
                <p className="field-hint" id={`builder-field-lorebook.${selectedId}.body-hint`}>
                  {t('builder.lorebook.body.hint')}
                </p>
              </div>

              <fieldset className="builder-field builder-lorebook-scope">
                <legend>{t('builder.lorebook.scope.legend')}</legend>
                <label>
                  <input
                    type="radio"
                    name="builder-lorebook-scope"
                    checked={selectedEntry.scope === 'keyword'}
                    onChange={() => updateEntry(selectedId, { scope: 'keyword' })}
                  />
                  {t('builder.lorebook.scope.keyword')}
                </label>
                <label>
                  <input
                    type="radio"
                    name="builder-lorebook-scope"
                    checked={selectedEntry.scope === 'always'}
                    onChange={() => updateEntry(selectedId, { scope: 'always' })}
                  />
                  {t('builder.lorebook.scope.always')}
                </label>
                <p className="field-hint">{t('builder.lorebook.scope.hint')}</p>
              </fieldset>

              <div className="builder-field">
                <label>
                  <input
                    id={`builder-field-lorebook.${selectedId}.enabled`}
                    type="checkbox"
                    checked={selectedEntry.enabled}
                    onChange={(e) => updateEntry(selectedId, { enabled: e.target.checked })}
                    aria-describedby={`builder-field-lorebook.${selectedId}.enabled-hint`}
                  />
                  {t('builder.lorebook.enabled')}
                </label>
                <p className="field-hint" id={`builder-field-lorebook.${selectedId}.enabled-hint`}>
                  {t('builder.lorebook.enabled.hint')}
                </p>
              </div>
            </div>
          ) : null}
        </div>
      )}

      <dialog
        ref={createDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-lorebook-create-title"
        onClose={() => setCreateOpen(false)}
        onCancel={(event) => {
          event.preventDefault()
          closeCreate()
        }}
      >
        <h2 id="builder-lorebook-create-title">{t('builder.lorebook.create.title')}</h2>
        <form onSubmit={handleCreateSubmit}>
          <div className="builder-field">
            <label htmlFor="builder-lorebook-create-id">{t('builder.lorebook.create.idLabel')}</label>
            <input
              id="builder-lorebook-create-id"
              ref={createIdRef}
              value={createId}
              onChange={(e) => setCreateId(e.target.value)}
              aria-invalid={createError ? 'true' : undefined}
              aria-describedby="builder-lorebook-create-id-hint"
            />
            <p className="field-hint" id="builder-lorebook-create-id-hint">
              {t('builder.lorebook.create.idHint')}
            </p>
          </div>
          <div className="builder-field">
            <label htmlFor="builder-lorebook-create-title-field">{t('builder.lorebook.title')}</label>
            <input
              id="builder-lorebook-create-title-field"
              value={createTitle}
              onChange={(e) => setCreateTitle(e.target.value)}
            />
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
            <button type="submit">{t('builder.lorebook.create.submit')}</button>
          </div>
        </form>
      </dialog>

      <dialog
        ref={deleteDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-lorebook-delete-title"
        onClose={() => setDeleteTarget(null)}
        onCancel={(event) => {
          event.preventDefault()
          closeDelete()
        }}
      >
        <h2 id="builder-lorebook-delete-title">{t('builder.lorebook.delete.title', { title: deleteTargetName })}</h2>
        <p>{t('builder.lorebook.delete.body', { id: deleteTarget ?? '' })}</p>
        <div className="builder-editor-dialog-actions">
          <button type="button" ref={deleteCancelRef} onClick={closeDelete}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={handleDeleteConfirm}>
            {t('builder.lorebook.delete')}
          </button>
        </div>
      </dialog>

      <dialog
        ref={splitDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-lorebook-split-title"
        onClose={() => setSplitConfirmOpen(false)}
        onCancel={(event) => {
          event.preventDefault()
          closeSplitConfirm()
        }}
      >
        <h2 id="builder-lorebook-split-title">{t('builder.lorebook.split.title')}</h2>
        <p>{t('builder.lorebook.split.body', { count: guided?.lore.length ?? 0 })}</p>
        <div className="builder-editor-dialog-actions">
          <button type="button" ref={splitCancelRef} onClick={closeSplitConfirm}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={applySplit}>
            {t('builder.lorebook.split.submit')}
          </button>
        </div>
      </dialog>
    </div>
  )
}
