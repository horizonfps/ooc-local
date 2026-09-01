import { useState } from 'react'
import { ApiError, deleteMedia, uploadMedia, type MediaTarget, type ScenarioMeta } from '../../api'
import type { TabProps } from '../../screens/BuilderEditorScreen'
import { describeError } from '../../errors'
import { t } from '../../i18n'
import { ErrorState } from '../ErrorState'
import '../../screens/builderEditor.css'

const COVER_EXTENSIONS = ['png', 'jpg', 'webp'] as const
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const MAX_COVER_BYTES = 8 * 1024 * 1024
const COVER_TARGET: MediaTarget = { kind: 'cover', key: 'cover' }

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

function IdentityCover(props: { scenarioId: string; scenarioName: string }) {
  const { scenarioId, scenarioName } = props
  const [extIndex, setExtIndex] = useState(0)
  const [overrideUrl, setOverrideUrl] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<{ message: string; retry: () => void } | null>(null)

  const hasImage = overrideUrl !== null || extIndex < COVER_EXTENSIONS.length
  const src = overrideUrl ?? (extIndex < COVER_EXTENSIONS.length ? `/api/scenarios/${scenarioId}/media/cover.${COVER_EXTENSIONS[extIndex]}` : null)

  function handleImgError() {
    if (overrideUrl !== null) {
      setOverrideUrl(null)
      setExtIndex(COVER_EXTENSIONS.length)
      return
    }
    setExtIndex((i) => i + 1)
  }

  async function submit(file: File) {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError({ message: t('builder.media.error.type'), retry: () => submit(file) })
      return
    }
    if (file.size > MAX_COVER_BYTES) {
      setError({ message: t('builder.media.error.size', { max: 8 }), retry: () => submit(file) })
      return
    }
    setUploading(true)
    setError(null)
    try {
      const result = await uploadMedia(scenarioId, COVER_TARGET, file)
      setOverrideUrl(`${result.url}?t=${Date.now()}`)
    } catch (err) {
      setError({ message: uploadErrorMessage(err), retry: () => submit(file) })
    } finally {
      setUploading(false)
    }
  }

  async function handleRemove() {
    setUploading(true)
    setError(null)
    try {
      await deleteMedia(scenarioId, COVER_TARGET)
      setOverrideUrl(null)
      setExtIndex(COVER_EXTENSIONS.length)
    } catch (err) {
      setError({ message: removeErrorMessage(err), retry: handleRemove })
    } finally {
      setUploading(false)
    }
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) void submit(file)
  }

  return (
    <fieldset className="builder-field builder-identity-cover" aria-busy={uploading || undefined}>
      <legend>{t('builder.identity.cover.legend')}</legend>
      <p className="field-hint" id="identity-cover-hint">
        {t('builder.identity.cover.hint')}
      </p>
      {hasImage && src ? (
        <img
          className="builder-identity-cover-image"
          src={src}
          alt={t('builder.identity.cover.alt', { scenario: scenarioName })}
          onError={handleImgError}
        />
      ) : (
        <div className="builder-identity-cover-placeholder">{t('builder.identity.cover.empty')}</div>
      )}
      {uploading ? (
        <p role="status" aria-live="polite" className="visually-hidden">
          {t('builder.identity.cover.uploading')}
        </p>
      ) : null}
      <div className="builder-identity-cover-actions">
        <label className="builder-identity-cover-uploadButton">
          {hasImage ? t('builder.identity.cover.replace') : t('builder.identity.cover.upload')}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="visually-hidden"
            disabled={uploading}
            onChange={handleFileChange}
          />
        </label>
        {hasImage ? (
          <button type="button" onClick={handleRemove} disabled={uploading}>
            {t('builder.identity.cover.remove')}
          </button>
        ) : null}
      </div>
      {error ? (
        <ErrorState title={t('builder.identity.cover.error')} body={error.message} onRetry={error.retry} />
      ) : null}
    </fieldset>
  )
}

export function IdentityTab(props: TabProps) {
  const { scenarioId, draft, onChange, errors } = props
  const meta = draft.meta

  const [touched, setTouched] = useState({ name: false, tagline: false, description: false })
  const [tagInput, setTagInput] = useState('')
  const [tagNotice, setTagNotice] = useState('')

  function updateMeta(patch: Partial<ScenarioMeta>) {
    onChange({ ...draft, meta: { ...meta, ...patch } })
  }

  function hasError(field: string): boolean {
    return errors.some((e) => e.tab === 'identity' && e.field === field)
  }

  function nameErrorText(): string | null {
    if (!meta.name.trim()) return t('builder.field.required')
    if (meta.name.length > 80) return t('builder.field.tooLong', { max: 80 })
    return null
  }

  function taglineErrorText(): string | null {
    if (meta.tagline !== null && meta.tagline.length > 120) return t('builder.field.tooLong', { max: 120 })
    return null
  }

  function descriptionErrorText(): string | null {
    if (meta.description !== null && meta.description.length > 4000) return t('builder.field.tooLong', { max: 4000 })
    return null
  }

  const nameInvalid = touched.name && hasError('name')
  const taglineInvalid = touched.tagline && hasError('tagline')
  const descriptionInvalid = touched.description && hasError('description')

  function commitTag() {
    const raw = tagInput.trim()
    setTagInput('')
    if (!raw) return
    if (meta.tags.includes(raw)) {
      setTagNotice(t('builder.identity.tags.duplicate', { tag: raw }))
      return
    }
    if (meta.tags.length >= 12) {
      setTagNotice(t('builder.identity.tags.max'))
      return
    }
    setTagNotice('')
    updateMeta({ tags: [...meta.tags, raw] })
  }

  function handleTagKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      commitTag()
    } else if (event.key === 'Backspace' && tagInput === '' && meta.tags.length > 0) {
      updateMeta({ tags: meta.tags.slice(0, -1) })
    }
  }

  function removeTag(tag: string) {
    updateMeta({ tags: meta.tags.filter((existing) => existing !== tag) })
  }

  return (
    <div className="builder-identity-tab">
      <h2>{t('builder.identity.heading')}</h2>

      <div className="builder-field">
        <label htmlFor="builder-field-name">{t('builder.identity.name')}</label>
        <input
          id="builder-field-name"
          value={meta.name}
          onChange={(e) => updateMeta({ name: e.target.value })}
          onBlur={() => setTouched((prev) => ({ ...prev, name: true }))}
          aria-invalid={nameInvalid ? 'true' : undefined}
          aria-describedby={nameInvalid ? 'builder-field-name-error' : undefined}
        />
        {nameInvalid ? (
          <p role="alert" id="builder-field-name-error" className="field-error">
            {nameErrorText()}
          </p>
        ) : null}
      </div>

      <div className="builder-field">
        <label htmlFor="builder-field-tagline">{t('builder.identity.tagline')}</label>
        <input
          id="builder-field-tagline"
          value={meta.tagline ?? ''}
          onChange={(e) => updateMeta({ tagline: e.target.value === '' ? null : e.target.value })}
          onBlur={() => setTouched((prev) => ({ ...prev, tagline: true }))}
          aria-invalid={taglineInvalid ? 'true' : undefined}
          aria-describedby={
            [taglineInvalid ? 'builder-field-tagline-error' : null, 'builder-field-tagline-hint'].filter(Boolean).join(' ') ||
            undefined
          }
        />
        <p className="field-hint" id="builder-field-tagline-hint">
          {t('builder.identity.tagline.hint')}
        </p>
        {meta.tagline !== null && meta.tagline.length >= 100 ? (
          <p aria-live="polite" className="field-counter">
            {t('builder.field.counter', { count: meta.tagline.length, max: 120 })}
          </p>
        ) : null}
        {taglineInvalid ? (
          <p role="alert" id="builder-field-tagline-error" className="field-error">
            {taglineErrorText()}
          </p>
        ) : null}
      </div>

      <div className="builder-field">
        <label htmlFor="builder-field-description">{t('builder.identity.description')}</label>
        <textarea
          id="builder-field-description"
          className="builder-field-textarea"
          value={meta.description ?? ''}
          onChange={(e) => updateMeta({ description: e.target.value === '' ? null : e.target.value })}
          onBlur={() => setTouched((prev) => ({ ...prev, description: true }))}
          aria-invalid={descriptionInvalid ? 'true' : undefined}
          aria-describedby={
            [descriptionInvalid ? 'builder-field-description-error' : null, 'builder-field-description-hint']
              .filter(Boolean)
              .join(' ') || undefined
          }
        />
        <p className="field-hint" id="builder-field-description-hint">
          {t('builder.identity.description.hint')}
        </p>
        {descriptionInvalid ? (
          <p role="alert" id="builder-field-description-error" className="field-error">
            {descriptionErrorText()}
          </p>
        ) : null}
      </div>

      <div className="builder-field builder-identity-tags">
        <label htmlFor="builder-field-tags">{t('builder.identity.tags')}</label>
        <div role="list" className="builder-tags-list">
          {meta.tags.map((tag) => (
            <span role="listitem" key={tag} className="builder-tag-chip">
              {tag}
              <button type="button" aria-label={t('builder.identity.tags.remove', { tag })} onClick={() => removeTag(tag)}>
                ×
              </button>
            </span>
          ))}
          <input
            id="builder-field-tags"
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={handleTagKeyDown}
            aria-describedby="builder-field-tags-hint"
          />
        </div>
        <p className="field-hint" id="builder-field-tags-hint">
          {meta.tags.length === 0 ? t('builder.identity.tags.empty') : t('builder.identity.tags.hint')}
        </p>
        <p role="status" aria-live="polite" className="field-hint">
          {tagNotice}
        </p>
      </div>

      <div className="builder-field">
        <label htmlFor="builder-field-locale">{t('builder.identity.locale')}</label>
        <select
          id="builder-field-locale"
          value={meta.locale}
          onChange={(e) => updateMeta({ locale: e.target.value as ScenarioMeta['locale'] })}
          aria-describedby="builder-field-locale-hint"
        >
          <option value="en">English</option>
          <option value="pt-br">Português (Brasil)</option>
        </select>
        <p className="field-hint" id="builder-field-locale-hint">
          {t('builder.identity.locale.hint')}
        </p>
      </div>

      <IdentityCover scenarioId={scenarioId} scenarioName={meta.name} />
    </div>
  )
}
