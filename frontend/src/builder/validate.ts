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
    errors.push(error('starts', 'starts', 'Starts', 'At least one start is required.'))
  }

  if (!(draft.meta.default_start in draft.starts)) {
    errors.push(
      error(
        'starts',
        'default_start',
        'Default start',
        `Default start "${draft.meta.default_start}" was not found among the starts.`,
      ),
    )
  }

  for (const startId of startIds) {
    if (!ID_RE.test(startId)) {
      errors.push(error('starts', `starts.${startId}`, 'Start id', `Start id "${startId}" must match [a-z0-9-]+.`))
    }
    const characters = draft.starts[startId].characters ?? []
    for (const charId of characters) {
      if (!(charId in draft.characters)) {
        errors.push(
          error(
            'starts',
            `starts.${startId}.characters`,
            'Start characters',
            `Start "${startId}" references unknown character "${charId}".`,
          ),
        )
      }
    }
  }

  for (const charId of Object.keys(draft.characters)) {
    if (!ID_RE.test(charId)) {
      errors.push(error('characters', `characters.${charId}`, 'Character id', `Character id "${charId}" must match [a-z0-9-]+.`))
    }
  }

  if (!draft.meta.name.trim()) {
    errors.push(error('identity', 'name', 'Name', 'Name is required.'))
  } else if (draft.meta.name.length > 80) {
    errors.push(error('identity', 'name', 'Name', 'Name must be 80 characters or fewer.'))
  }

  if (draft.meta.tagline !== null && draft.meta.tagline.length > 120) {
    errors.push(error('identity', 'tagline', 'Tagline', 'Tagline must be 120 characters or fewer.'))
  }

  if (draft.meta.description !== null && draft.meta.description.length > 4000) {
    errors.push(error('identity', 'description', 'Description', 'Description must be 4000 characters or fewer.'))
  }

  for (const tag of draft.meta.tags) {
    if (tag.length > 24) {
      errors.push(error('identity', 'tags', 'Tags', `Tag "${tag}" is longer than 24 characters.`))
    }
  }
  if (draft.meta.tags.length > 12) {
    errors.push(error('identity', 'tags', 'Tags', 'Scenario has more than 12 tags.'))
  }

  return errors
}
