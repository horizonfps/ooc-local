import { useEffect, useRef, useState } from 'react'
import { ApiError, deleteMedia, fetchMediaIndex, uploadMedia, type CharacterDoc, type MediaIndex } from '../../api'
import type { TabProps } from '../../screens/BuilderEditorScreen'
import { describeError } from '../../errors'
import { t } from '../../i18n'
import { EmptyState } from '../EmptyState'
import { ErrorState } from '../ErrorState'
import { Loading } from '../Loading'
import './media.css'

const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const MAX_BYTES = 8 * 1024 * 1024

type CellStatus = { kind: 'uploading' } | { kind: 'error'; message: string; retry: () => void }

type LoadState = { status: 'loading' } | { status: 'error'; error: unknown } | { status: 'ready'; index: MediaIndex }

type RemoveTarget = { folder: string; characterName: string; emotion: string; path: string }

function cellKey(folder: string, emotion: string): string {
  return `${folder}::${emotion}`
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
  let filled = 0
  let total = 0
  for (const [id, character] of Object.entries(characters)) {
    const folder = character.sprite || id
    for (const emotion of character.emotions) {
      total += 1
      if (index.sprites[folder]?.[emotion]) filled += 1
    }
  }
  return { filled, total }
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
  const [dragOver, setDragOver] = useState(false)
  const uploading = status?.kind === 'uploading'

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
    dragOver ? 'is-dragOver' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <li className={className} aria-busy={uploading || undefined} data-testid={`media-cell-${folder}-${emotion}`}>
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
            alt={t('builder.media.sprite.alt', { character: characterName, emotion })}
            title={basename(url.split('?')[0])}
            style={uploading ? { opacity: 0.5 } : undefined}
          />
        ) : (
          <span className="builder-media-cell-placeholder">
            {emotion === 'default' ? t('builder.media.cell.emptyDefault') : t('builder.media.cell.empty')}
          </span>
        )}
        {uploading ? <span className="visually-hidden">{t('builder.media.cell.uploading')}</span> : null}
        <span className="builder-media-cell-action">{url ? t('builder.media.cell.replace') : t('builder.media.cell.upload')}</span>
        <span className="builder-media-cell-emotion">{emotion}</span>
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="visually-hidden"
          aria-label={t('builder.media.sprite.upload', { character: characterName, emotion })}
          disabled={uploading}
          onChange={handleChange}
        />
      </label>
      {url ? (
        <button
          type="button"
          className="builder-media-cell-remove"
          aria-label={t('builder.media.sprite.remove', { character: characterName, emotion })}
          onClick={onOpenRemove}
          disabled={uploading}
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

export function MediaTab(props: TabProps) {
  const { scenarioId, draft, goToTab } = props
  const characterIds = Object.keys(draft.characters)

  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [cellStatus, setCellStatus] = useState<Record<string, CellStatus>>({})
  const [announcement, setAnnouncement] = useState('')
  const [removeTarget, setRemoveTarget] = useState<RemoveTarget | null>(null)

  const removeDialogRef = useRef<HTMLDialogElement>(null)
  const removeCancelRef = useRef<HTMLButtonElement>(null)

  function load() {
    setState({ status: 'loading' })
    fetchMediaIndex(scenarioId)
      .then((index) => setState({ status: 'ready', index }))
      .catch((error) => setState({ status: 'error', error }))
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
    setRemoveTarget({ folder, characterName, emotion, path: relativePathFromUrl(scenarioId, url) })
  }

  function closeRemove() {
    setRemoveTarget(null)
  }

  function confirmRemove() {
    if (!removeTarget) return
    const { folder, emotion, path, characterName } = removeTarget
    const key = cellKey(folder, emotion)
    setRemoveTarget(null)
    setCellStatus((prev) => ({ ...prev, [key]: { kind: 'uploading' } }))
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
  }

  const described = state.status === 'error' ? describeError(state.error) : null
  const { filled, total } =
    state.status === 'ready' ? countSpriteSlots(draft.characters, state.index) : { filled: 0, total: 0 }

  return (
    <div className="builder-media-tab">
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
            {filled === 0 ? <EmptyState title={t('builder.media.empty.title')} body={t('builder.media.empty.body')} /> : null}

            <h3>{t('builder.media.sprites.heading')}</h3>
            {characterIds.map((id) => {
              const character = draft.characters[id]
              const folder = character.sprite || id
              const characterName = character.name || id
              const onlyDefault = character.emotions.length === 1 && character.emotions[0] === 'default'
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
                </section>
              )
            })}
          </>
        )
      ) : null}
    </div>
  )
}
