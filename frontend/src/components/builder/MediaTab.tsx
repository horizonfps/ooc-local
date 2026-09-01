import { useEffect, useRef, useState } from 'react'
import { ApiError, deleteMedia, fetchMediaIndex, uploadMedia, type CharacterDoc, type MediaIndex } from '../../api'
import type { BuilderDraft, TabProps } from '../../screens/BuilderEditorScreen'
import { describeError } from '../../errors'
import { t } from '../../i18n'
import { slugify } from '../../screens/BuilderListScreen'
import { EmptyState } from '../EmptyState'
import { ErrorState } from '../ErrorState'
import { Loading } from '../Loading'
import './media.css'

const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const MAX_BYTES = 8 * 1024 * 1024
const SLUG_RE = /^[a-z0-9-]+$/

type CellStatus = { kind: 'uploading' } | { kind: 'removing' } | { kind: 'error'; message: string; retry: () => void }

type LoadState = { status: 'loading' } | { status: 'error'; error: unknown } | { status: 'ready'; index: MediaIndex }

type RemoveTarget =
  | { kind: 'sprite'; folder: string; characterName: string; emotion: string; path: string }
  | { kind: 'background'; slug: string; path: string }

function cellKey(folder: string, emotion: string): string {
  return `${folder}::${emotion}`
}

function bgCellKey(slug: string): string {
  return `bg::${slug}`
}

function basename(path: string): string {
  return path.split('/').pop() ?? path
}

function relativePathFromUrl(scenarioId: string, url: string): string {
  const prefix = `/api/scenarios/${scenarioId}/media/`
  const withoutQuery = url.split('?')[0]
  return withoutQuery.startsWith(prefix) ? withoutQuery.slice(prefix.length) : withoutQuery
}

function uploadErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 415) return t('builder.media.error.type')
    if (err.status === 413) return t('builder.media.error.size', { max: 8 })
    if (err.status === 422) return t('builder.media.error.invalidKey')
    if (err.status === 503) return t('builder.media.error.disabled')
    if (err.status === 500) return t('builder.media.error.write')
  }
  return describeError(err).body
}

function removeErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 503) return t('builder.media.error.disabled')
  if (err instanceof ApiError) return t('builder.media.error.removeFailed')
  return describeError(err).body
}

function orderedEmotions(character: CharacterDoc): string[] {
  const rest = character.emotions.filter((emotion) => emotion !== 'default')
  return character.emotions.includes('default') ? ['default', ...rest] : [...character.emotions]
}

export function countSpriteSlots(characters: Record<string, CharacterDoc>, index: MediaIndex): { filled: number; total: number } {
  const seen = new Set<string>()
  let filled = 0
  let total = 0
  for (const [id, character] of Object.entries(characters)) {
    const folder = character.sprite || id
    for (const emotion of character.emotions) {
      const key = cellKey(folder, emotion)
      if (seen.has(key)) continue
      seen.add(key)
      total += 1
      if (index.sprites[folder]?.[emotion]) filled += 1
    }
  }
  return { filled, total }
}

type BackgroundSlot = { slug: string; fromStart: string | null }

export function backgroundSlots(draft: BuilderDraft, index: MediaIndex, extra: readonly string[]): BackgroundSlot[] {
  const map = new Map<string, string | null>()
  for (const start of Object.values(draft.starts)) {
    const slug = slugify(start.hud.location)
    if (!slug || map.has(slug)) continue
    map.set(slug, start.name || start.id)
  }
  for (const slug of Object.keys(index.backgrounds)) {
    if (!map.has(slug)) map.set(slug, null)
  }
  for (const slug of extra) {
    if (!map.has(slug)) map.set(slug, null)
  }
  return Array.from(map.entries()).map(([slug, fromStart]) => ({ slug, fromStart }))
}

function countBackgroundSlots(slots: readonly BackgroundSlot[], index: MediaIndex): { filled: number; total: number } {
  let filled = 0
  for (const slot of slots) {
    if (index.backgrounds[slot.slug]) filled += 1
  }
  return { filled, total: slots.length }
}

function orphanEmotions(folder: string, character: CharacterDoc, index: MediaIndex): string[] {
  const declared = new Set(character.emotions)
  return Object.keys(index.sprites[folder] ?? {}).filter((emotion) => !declared.has(emotion))
}

function characterFolders(characters: Record<string, CharacterDoc>): Set<string> {
  return new Set(Object.entries(characters).map(([id, character]) => character.sprite || id))
}

function MediaCell(props: {
  testId: string
  belowLabel: string
  placeholder: string
  alt: string
  uploadLabel: string
  removeLabel: string
  url: string | undefined
  status: CellStatus | undefined
  onFile: (file: File) => void
  onOpenRemove: () => void
}) {
  const { testId, belowLabel, placeholder, alt, uploadLabel, removeLabel, url, status, onFile, onOpenRemove } = props
  const [dragOver, setDragOver] = useState(false)
  const uploading = status?.kind === 'uploading'
  const removing = status?.kind === 'removing'
  const busy = uploading || removing

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) onFile(file)
  }

  function handleDragOver(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragOver(true)
  }

  function handleDragLeave() {
    setDragOver(false)
  }

  function handleDrop(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragOver(false)
    const file = event.dataTransfer.files?.[0]
    if (file) onFile(file)
  }

  const className = [
    'builder-media-cell',
    url ? 'is-filled' : 'is-empty',
    uploading ? 'is-uploading' : '',
    removing ? 'is-removing' : '',
    dragOver ? 'is-dragOver' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <li className={className} aria-busy={busy || undefined} data-testid={testId}>
      <label
        className="builder-media-cell-label"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {url ? (
          <img
            className="builder-media-cell-thumb"
            src={url}
            alt={alt}
            title={basename(url.split('?')[0])}
            style={busy ? { opacity: 0.5 } : undefined}
          />
        ) : (
          <span className="builder-media-cell-placeholder">{placeholder}</span>
        )}
        {uploading ? <span className="visually-hidden">{t('builder.media.cell.uploading')}</span> : null}
        {removing ? <span className="visually-hidden">{t('builder.media.cell.removing')}</span> : null}
        <span className="builder-media-cell-action">{url ? t('builder.media.cell.replace') : t('builder.media.cell.upload')}</span>
        <span className="builder-media-cell-emotion">{belowLabel}</span>
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="visually-hidden"
          aria-label={uploadLabel}
          disabled={busy}
          onChange={handleChange}
        />
      </label>
      {url ? (
        <button
          type="button"
          className="builder-media-cell-remove"
          aria-label={removeLabel}
          onClick={onOpenRemove}
          disabled={busy}
        >
          {t('common.remove')}
        </button>
      ) : null}
      {status?.kind === 'error' ? (
        <div role="alert" className="builder-media-cell-error">
          <p>{status.message}</p>
          <button type="button" onClick={status.retry}>
            {t('common.retry')}
          </button>
        </div>
      ) : null}
    </li>
  )
}

function MediaSpriteCell(props: {
  folder: string
  characterName: string
  emotion: string
  url: string | undefined
  status: CellStatus | undefined
  onFile: (file: File) => void
  onOpenRemove: () => void
}) {
  const { folder, characterName, emotion, url, status, onFile, onOpenRemove } = props
  return (
    <MediaCell
      testId={`media-cell-${folder}-${emotion}`}
      belowLabel={emotion}
      placeholder={emotion === 'default' ? t('builder.media.cell.emptyDefault') : t('builder.media.cell.empty')}
      alt={t('builder.media.sprite.alt', { character: characterName, emotion })}
      uploadLabel={t('builder.media.sprite.upload', { character: characterName, emotion })}
      removeLabel={t('builder.media.sprite.remove', { character: characterName, emotion })}
      url={url}
      status={status}
      onFile={onFile}
      onOpenRemove={onOpenRemove}
    />
  )
}

function MediaBackgroundCell(props: {
  slot: BackgroundSlot
  url: string | undefined
  status: CellStatus | undefined
  onFile: (file: File) => void
  onOpenRemove: () => void
}) {
  const { slot, url, status, onFile, onOpenRemove } = props
  const placeholder = !url && slot.fromStart ? t('builder.media.bg.fromStart', { start: slot.fromStart }) : t('builder.media.cell.empty')
  return (
    <MediaCell
      testId={`media-bg-cell-${slot.slug}`}
      belowLabel={slot.slug}
      placeholder={placeholder}
      alt={t('builder.media.bg.alt', { location: slot.slug })}
      uploadLabel={t('builder.media.bg.upload', { location: slot.slug })}
      removeLabel={t('builder.media.bg.remove', { location: slot.slug })}
      url={url}
      status={status}
      onFile={onFile}
      onOpenRemove={onOpenRemove}
    />
  )
}

export function MediaTab(props: TabProps) {
  const { scenarioId, draft, onChange, goToTab } = props
  const characterIds = Object.keys(draft.characters)

  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [cellStatus, setCellStatus] = useState<Record<string, CellStatus>>({})
  const [announcement, setAnnouncement] = useState('')
  const [removeTarget, setRemoveTarget] = useState<RemoveTarget | null>(null)
  const [extraSlots, setExtraSlots] = useState<string[]>([])
  const [addOpen, setAddOpen] = useState(false)
  const [addValue, setAddValue] = useState('')
  const [addError, setAddError] = useState<string | null>(null)

  const removeDialogRef = useRef<HTMLDialogElement>(null)
  const removeCancelRef = useRef<HTMLButtonElement>(null)

  function load() {
    setState({ status: 'loading' })
    let cancelled = false
    fetchMediaIndex(scenarioId)
      .then((index) => {
        if (!cancelled) setState({ status: 'ready', index })
      })
      .catch((error) => {
        if (!cancelled) setState({ status: 'error', error })
      })
    return () => {
      cancelled = true
    }
  }

  useEffect(load, [scenarioId])

  useEffect(() => {
    if (removeTarget) {
      removeDialogRef.current?.showModal()
      removeCancelRef.current?.focus()
    } else {
      removeDialogRef.current?.close()
    }
  }, [removeTarget])

  function submitUpload(folder: string, emotion: string, file: File) {
    const key = cellKey(folder, emotion)
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setCellStatus((prev) => ({
        ...prev,
        [key]: { kind: 'error', message: t('builder.media.error.type'), retry: () => submitUpload(folder, emotion, file) },
      }))
      return
    }
    if (file.size > MAX_BYTES) {
      setCellStatus((prev) => ({
        ...prev,
        [key]: { kind: 'error', message: t('builder.media.error.size', { max: 8 }), retry: () => submitUpload(folder, emotion, file) },
      }))
      return
    }

    const wasFilled = state.status === 'ready' && Boolean(state.index.sprites[folder]?.[emotion])
    setCellStatus((prev) => ({ ...prev, [key]: { kind: 'uploading' } }))
    uploadMedia(scenarioId, { kind: 'sprite', key: emotion, character: folder }, file)
      .then((result) => {
        setState((prev) => {
          if (prev.status !== 'ready') return prev
          const nextFolder = { ...(prev.index.sprites[folder] ?? {}), [emotion]: `${result.url}?t=${Date.now()}` }
          return { ...prev, index: { ...prev.index, sprites: { ...prev.index.sprites, [folder]: nextFolder } } }
        })
        setCellStatus((prev) => {
          const next = { ...prev }
          delete next[key]
          return next
        })
        setAnnouncement(
          wasFilled
            ? t('builder.media.replaced', { name: basename(result.path) })
            : t('builder.media.uploaded', { name: basename(result.path) }),
        )
      })
      .catch((err) => {
        setCellStatus((prev) => ({
          ...prev,
          [key]: { kind: 'error', message: uploadErrorMessage(err), retry: () => submitUpload(folder, emotion, file) },
        }))
      })
  }

  function openRemove(folder: string, characterName: string, emotion: string) {
    if (state.status !== 'ready') return
    const url = state.index.sprites[folder]?.[emotion]
    if (!url) return
    setRemoveTarget({ kind: 'sprite', folder, characterName, emotion, path: relativePathFromUrl(scenarioId, url) })
  }

  function openBgRemove(slug: string) {
    if (state.status !== 'ready') return
    const url = state.index.backgrounds[slug]
    if (!url) return
    setRemoveTarget({ kind: 'background', slug, path: relativePathFromUrl(scenarioId, url) })
  }

  function closeRemove() {
    setRemoveTarget(null)
  }

  function confirmRemove() {
    if (!removeTarget) return
    if (removeTarget.kind === 'sprite') {
      const { folder, emotion, path, characterName } = removeTarget
      const key = cellKey(folder, emotion)
      setRemoveTarget(null)
      setCellStatus((prev) => ({ ...prev, [key]: { kind: 'removing' } }))
      deleteMedia(scenarioId, { kind: 'sprite', key: emotion, character: folder })
        .then(() => {
          setState((prev) => {
            if (prev.status !== 'ready') return prev
            const nextFolder = { ...prev.index.sprites[folder] }
            delete nextFolder[emotion]
            return { ...prev, index: { ...prev.index, sprites: { ...prev.index.sprites, [folder]: nextFolder } } }
          })
          setCellStatus((prev) => {
            const next = { ...prev }
            delete next[key]
            return next
          })
          setAnnouncement(t('builder.media.removed', { name: basename(path) }))
        })
        .catch((err) => {
          setCellStatus((prev) => ({
            ...prev,
            [key]: { kind: 'error', message: removeErrorMessage(err), retry: () => openRemove(folder, characterName, emotion) },
          }))
        })
      return
    }

    const { slug, path } = removeTarget
    const key = bgCellKey(slug)
    setRemoveTarget(null)
    setCellStatus((prev) => ({ ...prev, [key]: { kind: 'removing' } }))
    deleteMedia(scenarioId, { kind: 'background', key: slug })
      .then(() => {
        setState((prev) => {
          if (prev.status !== 'ready') return prev
          const nextBackgrounds = { ...prev.index.backgrounds }
          delete nextBackgrounds[slug]
          return { ...prev, index: { ...prev.index, backgrounds: nextBackgrounds } }
        })
        setCellStatus((prev) => {
          const next = { ...prev }
          delete next[key]
          return next
        })
        setAnnouncement(t('builder.media.removed', { name: basename(path) }))
      })
      .catch((err) => {
        setCellStatus((prev) => ({
          ...prev,
          [key]: { kind: 'error', message: removeErrorMessage(err), retry: () => openBgRemove(slug) },
        }))
      })
  }

  function submitBgUpload(slug: string, file: File) {
    const key = bgCellKey(slug)
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setCellStatus((prev) => ({
        ...prev,
        [key]: { kind: 'error', message: t('builder.media.error.type'), retry: () => submitBgUpload(slug, file) },
      }))
      return
    }
    if (file.size > MAX_BYTES) {
      setCellStatus((prev) => ({
        ...prev,
        [key]: { kind: 'error', message: t('builder.media.error.size', { max: 8 }), retry: () => submitBgUpload(slug, file) },
      }))
      return
    }

    const wasFilled = state.status === 'ready' && Boolean(state.index.backgrounds[slug])
    setCellStatus((prev) => ({ ...prev, [key]: { kind: 'uploading' } }))
    uploadMedia(scenarioId, { kind: 'background', key: slug }, file)
      .then((result) => {
        setState((prev) => {
          if (prev.status !== 'ready') return prev
          return { ...prev, index: { ...prev.index, backgrounds: { ...prev.index.backgrounds, [slug]: `${result.url}?t=${Date.now()}` } } }
        })
        setCellStatus((prev) => {
          const next = { ...prev }
          delete next[key]
          return next
        })
        setAnnouncement(
          wasFilled
            ? t('builder.media.replaced', { name: basename(result.path) })
            : t('builder.media.uploaded', { name: basename(result.path) }),
        )
      })
      .catch((err) => {
        setCellStatus((prev) => ({
          ...prev,
          [key]: { kind: 'error', message: uploadErrorMessage(err), retry: () => submitBgUpload(slug, file) },
        }))
      })
  }

  function addLocation() {
    const value = addValue.trim()
    if (!value || !SLUG_RE.test(value)) {
      setAddError(t('builder.field.slugInvalid'))
      return
    }
    if (slots.some((slot) => slot.slug === value)) {
      setAddError(t('builder.field.slugTaken', { slug: value }))
      return
    }
    setAddError(null)
    setExtraSlots((prev) => [...prev, value])
    setAddValue('')
    setAddOpen(false)
  }

  function removeSlot(slug: string) {
    setExtraSlots((prev) => prev.filter((s) => s !== slug))
  }

  function declareOrphan(id: string, emotion: string) {
    const character = draft.characters[id]
    if (!character || character.emotions.includes(emotion)) return
    onChange({ ...draft, characters: { ...draft.characters, [id]: { ...character, emotions: [...character.emotions, emotion] } } })
  }

  const described = state.status === 'error' ? describeError(state.error) : null
  const spriteCount =
    state.status === 'ready' ? countSpriteSlots(draft.characters, state.index) : { filled: 0, total: 0 }
  const slots = state.status === 'ready' ? backgroundSlots(draft, state.index, extraSlots) : []
  const bgCount = state.status === 'ready' ? countBackgroundSlots(slots, state.index) : { filled: 0, total: 0 }
  const filled = spriteCount.filled + bgCount.filled
  const total = spriteCount.total + bgCount.total
  const usedFolders = characterFolders(draft.characters)
  const orphanFolders =
    state.status === 'ready' ? Object.keys(state.index.sprites).filter((folder) => !usedFolders.has(folder)) : []

  function preventStrayDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault()
  }

  return (
    <div className="builder-media-tab" onDragOver={preventStrayDrop} onDrop={preventStrayDrop}>
      <h2>{t('builder.media.heading')}</h2>
      <p className="field-hint">{t('builder.media.hint')}</p>

      <div role="status" aria-live="polite" className="visually-hidden">
        {announcement}
      </div>

      {state.status === 'ready' ? (
        <p role="status" aria-live="polite" className="builder-media-summary">
          {t('builder.media.summary', { filled, total })}
        </p>
      ) : null}

      <dialog
        ref={removeDialogRef}
        className="builder-editor-dialog"
        aria-labelledby="builder-media-remove-title"
        onClose={closeRemove}
        onCancel={(event) => {
          event.preventDefault()
          closeRemove()
        }}
      >
        <h2 id="builder-media-remove-title">{t('builder.media.remove.title')}</h2>
        <p>{t('builder.media.remove.body', { path: removeTarget?.path ?? '' })}</p>
        <div className="builder-editor-dialog-actions">
          <button type="button" ref={removeCancelRef} onClick={closeRemove}>
            {t('common.cancel')}
          </button>
          <button type="button" onClick={confirmRemove}>
            {t('common.remove')}
          </button>
        </div>
      </dialog>

      {state.status === 'loading' ? <Loading label={t('builder.editor.loading')} /> : null}

      {described ? <ErrorState title={described.title} body={described.body} cause={described.cause} onRetry={load} /> : null}

      {state.status === 'ready' ? (
        characterIds.length === 0 ? (
          <EmptyState
            title={t('builder.media.sprites.empty.title')}
            body={t('builder.media.sprites.empty.body')}
            action={
              <button type="button" onClick={() => goToTab('characters')}>
                {t('builder.editor.tab.characters')}
              </button>
            }
          />
        ) : (
          <>
            {filled === 0 && !state.index.cover ? (
              <EmptyState title={t('builder.media.empty.title')} body={t('builder.media.empty.body')} />
            ) : null}

            <h3>{t('builder.media.sprites.heading')}</h3>
            {characterIds.map((id) => {
              const character = draft.characters[id]
              const folder = character.sprite || id
              const characterName = character.name || id
              const onlyDefault = character.emotions.length === 1 && character.emotions[0] === 'default'
              const orphans = orphanEmotions(folder, character, state.index)
              return (
                <section key={id} aria-labelledby={`builder-media-character-${id}`} className="builder-media-character">
                  <h3 id={`builder-media-character-${id}`}>{characterName}</h3>
                  <p className="field-hint builder-media-folder">{t('builder.media.sprites.folder', { folder })}</p>
                  <ul role="list" className="builder-media-grid">
                    {orderedEmotions(character).map((emotion) => (
                      <MediaSpriteCell
                        key={emotion}
                        folder={folder}
                        characterName={characterName}
                        emotion={emotion}
                        url={state.index.sprites[folder]?.[emotion]}
                        status={cellStatus[cellKey(folder, emotion)]}
                        onFile={(file) => submitUpload(folder, emotion, file)}
                        onOpenRemove={() => openRemove(folder, characterName, emotion)}
                      />
                    ))}
                  </ul>
                  {onlyDefault ? (
                    <p className="field-hint">
                      {t('builder.media.sprites.addEmotions')}{' '}
                      <button type="button" onClick={() => goToTab('characters')}>
                        {t('builder.editor.tab.characters')}
                      </button>
                    </p>
                  ) : null}
                  {orphans.length > 0 ? (
                    <div className="builder-media-orphans" data-testid={`media-orphans-${folder}`}>
                      <h4>{t('builder.media.sprites.orphans.title')}</h4>
                      <p className="field-hint">{t('builder.media.sprites.orphans.body')}</p>
                      <ul role="list" className="builder-media-orphans-list">
                        {orphans.map((emotion) => {
                          const url = state.index.sprites[folder]?.[emotion]
                          return (
                            <li key={emotion} className="builder-media-orphan">
                              {url ? (
                                <img
                                  className="builder-media-orphan-thumb"
                                  src={url}
                                  alt={t('builder.media.sprite.alt', { character: characterName, emotion })}
                                />
                              ) : null}
                              <span className="builder-media-orphan-name">{url ? basename(url.split('?')[0]) : emotion}</span>
                              <button type="button" onClick={() => declareOrphan(id, emotion)}>
                                {t('builder.media.sprites.orphans.declare', { emotion })}
                              </button>
                              <button type="button" onClick={() => openRemove(folder, characterName, emotion)}>
                                {t('common.remove')}
                              </button>
                            </li>
                          )
                        })}
                      </ul>
                    </div>
                  ) : null}
                </section>
              )
            })}

            {orphanFolders.length > 0 ? (
              <div className="builder-media-orphans" data-testid="media-orphan-folders">
                <h3>{t('builder.media.sprites.orphans.folderTitle')}</h3>
                <p className="field-hint">{t('builder.media.sprites.orphans.body')}</p>
                {orphanFolders.map((folder) => (
                  <ul key={folder} role="list" className="builder-media-orphans-list">
                    {Object.keys(state.index.sprites[folder] ?? {}).map((emotion) => {
                      const url = state.index.sprites[folder]?.[emotion]
                      return (
                        <li key={emotion} className="builder-media-orphan">
                          {url ? (
                            <img className="builder-media-orphan-thumb" src={url} alt={t('builder.media.sprite.alt', { character: folder, emotion })} />
                          ) : null}
                          <span className="builder-media-orphan-name">{url ? basename(url.split('?')[0]) : emotion}</span>
                          <button type="button" onClick={() => openRemove(folder, folder, emotion)}>
                            {t('common.remove')}
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                ))}
              </div>
            ) : null}

            <h3>{t('builder.media.backgrounds.heading')}</h3>
            <ul role="list" className="builder-media-grid builder-media-bg-grid">
              {slots.map((slot) => (
                <MediaBackgroundCell
                  key={slot.slug}
                  slot={slot}
                  url={state.index.backgrounds[slot.slug]}
                  status={cellStatus[bgCellKey(slot.slug)]}
                  onFile={(file) => submitBgUpload(slot.slug, file)}
                  onOpenRemove={() => openBgRemove(slot.slug)}
                />
              ))}
            </ul>
            <ul className="builder-media-bg-slots">
              {slots
                .filter((slot) => !slot.fromStart && !state.index.backgrounds[slot.slug])
                .map((slot) => (
                  <li key={slot.slug}>
                    <button type="button" onClick={() => removeSlot(slot.slug)}>
                      {t('builder.media.backgrounds.removeSlot', { location: slot.slug })}
                    </button>
                  </li>
                ))}
            </ul>

            {addOpen ? (
              <div className="builder-field">
                <label htmlFor="builder-media-backgrounds-add-input">{t('builder.media.backgrounds.addLabel')}</label>
                <input
                  id="builder-media-backgrounds-add-input"
                  value={addValue}
                  onChange={(e) => {
                    setAddValue(e.target.value)
                    setAddError(null)
                  }}
                  aria-invalid={addError ? 'true' : undefined}
                />
                <p className="field-hint">{t('builder.media.backgrounds.addHint')}</p>
                <button type="button" onClick={addLocation}>
                  {t('builder.media.backgrounds.add')}
                </button>
                {addError ? (
                  <p role="alert" className="field-error">
                    {addError}
                  </p>
                ) : null}
              </div>
            ) : (
              <button type="button" onClick={() => setAddOpen(true)}>
                {t('builder.media.backgrounds.add')}
              </button>
            )}
          </>
        )
      ) : null}
    </div>
  )
}
