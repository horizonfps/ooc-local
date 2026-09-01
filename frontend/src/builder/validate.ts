import { t } from '../i18n'
import type { BuilderDraft, BuilderTab, ValidationError } from '../screens/BuilderEditorScreen'

const ID_RE = /^[a-z0-9-]+$/

export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false
    return a.every((item, i) => deepEqual(item, b[i]))
  }
  if (typeof a === 'object' && a !== null && typeof b === 'object' && b !== null) {
    const aKeys = Object.keys(a)
    const bKeys = Object.keys(b)
    if (aKeys.length !== bKeys.length) return false
    return aKeys.every(
      (key) =>
        Object.prototype.hasOwnProperty.call(b, key) &&
        deepEqual((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key]),
    )
  }
  return false
}

function error(tab: BuilderTab, field: string, label: string, message: string): ValidationError {
  return { tab, field, label, message }
}

export function validateDraft(draft: BuilderDraft): ValidationError[] {
  const errors: ValidationError[] = []
  const startIds = Object.keys(draft.starts)

  if (startIds.length === 0) {
    errors.push(error('starts', 'starts', t('builder.field.label.starts'), t('builder.validate.startsRequired')))
  }

  if (!(draft.meta.default_start in draft.starts)) {
    errors.push(
      error(
        'starts',
        'default_start',
        t('builder.field.label.defaultStart'),
        t('builder.validate.defaultStartMissing', { id: draft.meta.default_start }),
      ),
    )
  }

  for (const startId of startIds) {
    if (!ID_RE.test(startId)) {
      errors.push(error('starts', `starts.${startId}`, t('builder.field.label.startId'), t('builder.field.slugInvalid')))
    }
    const characters = draft.starts[startId].characters ?? []
    for (const charId of characters) {
      if (!(charId in draft.characters)) {
        errors.push(
          error(
            'starts',
            `starts.${startId}.characters`,
            t('builder.field.label.startCharacters'),
            t('builder.validate.startUnknownCharacter', { start: startId, character: charId }),
          ),
        )
      }
    }
  }

  for (const charId of Object.keys(draft.characters)) {
    if (!ID_RE.test(charId)) {
      errors.push(error('characters', `characters.${charId}`, t('builder.field.label.characterId'), t('builder.field.slugInvalid')))
    }
  }

  if (!draft.meta.name.trim()) {
    errors.push(error('identity', 'name', t('builder.identity.name'), t('builder.field.required')))
  } else if (draft.meta.name.length > 80) {
    errors.push(error('identity', 'name', t('builder.identity.name'), t('builder.field.tooLong', { max: 80 })))
  }

  if (draft.meta.tagline !== null && draft.meta.tagline.length > 120) {
    errors.push(error('identity', 'tagline', t('builder.identity.tagline'), t('builder.field.tooLong', { max: 120 })))
  }

  if (draft.meta.description !== null && draft.meta.description.length > 4000) {
    errors.push(error('identity', 'description', t('builder.identity.description'), t('builder.field.tooLong', { max: 4000 })))
  }

  for (const tag of draft.meta.tags) {
    if (tag.length > 24) {
      errors.push(error('identity', 'tags', t('builder.identity.tags'), t('builder.field.tooLong', { max: 24 })))
    }
  }
  if (draft.meta.tags.length > 12) {
    errors.push(error('identity', 'tags', t('builder.identity.tags'), t('builder.identity.tags.max')))
  }

  return errors
}
