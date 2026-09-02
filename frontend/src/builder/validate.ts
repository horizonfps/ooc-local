import { t } from '../i18n'
import type { BuilderDraft, BuilderTab, ValidationError } from '../screens/BuilderEditorScreen'
import { parseGuidedWorld } from './worldMarkdown'

const ID_RE = /^[a-z0-9-]+$/
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/
const WEATHER_CODES = ['clear', 'cloudy', 'rain', 'storm', 'snow', 'fog', 'night']

// Mirrors backend/app/scenario.py Character.emotions cap (20 total, default forced in).
export const MAX_EMOTIONS = 20

// Public contract, consumed by TCK-070 and TCK-073.
export const STAT_ID_RE = /^[a-z0-9_-]+$/
export const STAT_COLOR_RE = /^#[0-9a-fA-F]{6}$/
export const MAX_STAT_NAME = 40
export const MAX_STAT_ICON = 4
export const MAX_STAT_DESCRIPTION = 200

function hasUnbalancedVariable(text: string): boolean {
  return text.split('\n').some((line) => {
    let open = false
    for (let i = 0; i < line.length; i += 1) {
      if (line.startsWith('{{', i)) {
        if (open) return true
        open = true
        i += 1
      } else if (line.startsWith('}}', i)) {
        if (!open) return true
        open = false
        i += 1
      }
    }
    return open
  })
}

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
    const start = draft.starts[startId]
    const startLabel = start.name.trim() || startId
    const withStart = (label: string) => `${startLabel} — ${label}`

    if (!ID_RE.test(startId)) {
      errors.push(error('starts', `starts.${startId}`, withStart(t('builder.field.label.startId')), t('builder.field.slugInvalid')))
    }

    if (!start.name.trim()) {
      errors.push(error('starts', `starts.${startId}.name`, withStart(t('builder.starts.name')), t('builder.field.required')))
    } else if (start.name.length > 80) {
      errors.push(error('starts', `starts.${startId}.name`, withStart(t('builder.starts.name')), t('builder.field.tooLong', { max: 80 })))
    }

    if (!start.prologue.trim()) {
      errors.push(error('starts', `starts.${startId}.prologue`, withStart(t('builder.starts.prologue')), t('builder.field.required')))
    }

    if (!start.opening_scene.trim()) {
      errors.push(
        error('starts', `starts.${startId}.opening_scene`, withStart(t('builder.starts.openingScene')), t('builder.field.required')),
      )
    }

    if (!start.hud.location.trim()) {
      errors.push(
        error('starts', `starts.${startId}.hud.location`, withStart(t('builder.starts.hud.location')), t('builder.field.required')),
      )
    }

    if (!TIME_RE.test(start.hud.time)) {
      errors.push(
        error('starts', `starts.${startId}.hud.time`, withStart(t('builder.starts.hud.time')), t('builder.field.time.invalid')),
      )
    }

    if (!WEATHER_CODES.includes(start.hud.weather)) {
      errors.push(
        error('starts', `starts.${startId}.hud.weather`, withStart(t('builder.starts.hud.weather')), t('builder.field.weather.invalid')),
      )
    }

    start.suggestions.forEach((suggestion, index) => {
      if (suggestion.length > 120) {
        errors.push(
          error(
            'starts',
            `starts.${startId}.suggestions.${index}`,
            withStart(t('builder.starts.suggestions.item', { index: index + 1 })),
            t('builder.field.tooLong', { max: 120 }),
          ),
        )
      }
    })

    const characters = start.characters ?? []
    for (const charId of characters) {
      if (!(charId in draft.characters)) {
        errors.push(
          error(
            'starts',
            `starts.${startId}.characters`,
            withStart(t('builder.field.label.startCharacters')),
            t('builder.validate.startUnknownCharacter', { start: startId, character: charId }),
          ),
        )
      }
    }
  }

  const characterIds = Object.keys(draft.characters)

  for (const charId of characterIds) {
    const character = draft.characters[charId]
    const charLabel = character.name.trim() || charId
    const withChar = (label: string) => `${charLabel} — ${label}`

    if (!ID_RE.test(charId)) {
      errors.push(
        error('characters', `characters.${charId}`, withChar(t('builder.field.label.characterId')), t('builder.field.slugInvalid')),
      )
    }

    if (!character.name.trim()) {
      errors.push(error('characters', `characters.${charId}.name`, withChar(t('builder.characters.name')), t('builder.field.required')))
    } else if (character.name.length > 80) {
      errors.push(
        error('characters', `characters.${charId}.name`, withChar(t('builder.characters.name')), t('builder.field.tooLong', { max: 80 })),
      )
    }

    if (character.role.length > 140) {
      errors.push(
        error('characters', `characters.${charId}.role`, withChar(t('builder.characters.role')), t('builder.field.tooLong', { max: 140 })),
      )
    }

    if (character.sprite !== null && !ID_RE.test(character.sprite)) {
      errors.push(
        error('characters', `characters.${charId}.sprite`, withChar(t('builder.characters.sprite')), t('builder.field.slugInvalid')),
      )
    }

    character.emotions.forEach((emotion, index) => {
      if (!ID_RE.test(emotion)) {
        errors.push(
          error(
            'characters',
            `characters.${charId}.emotions.${index}`,
            withChar(t('builder.characters.emotions.legend')),
            t('builder.field.slugInvalid'),
          ),
        )
      }
    })

    if (character.emotions.length > MAX_EMOTIONS) {
      errors.push(
        error(
          'characters',
          `characters.${charId}.emotions`,
          withChar(t('builder.characters.emotions.legend')),
          t('builder.characters.emotions.max', { max: MAX_EMOTIONS - 1 }),
        ),
      )
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

  if (!draft.world.trim()) {
    errors.push(error('world', 'world', t('builder.world.custom.label'), t('builder.field.required')))
  } else if (draft.meta.world_mode === 'guided') {
    const guided = parseGuidedWorld(draft.world)
    if (guided) {
      if (!guided.universe.trim()) {
        errors.push(error('world', 'universe', t('builder.world.universe'), t('builder.field.required')))
      }

      const seenTitles = new Set<string>()
      guided.lore.forEach((block, index) => {
        const label = t('builder.world.lore.titleLabel', { index: index + 1 })
        const title = block.title.trim()
        if (!title) {
          errors.push(error('world', `world.lore.${index}.title`, label, t('builder.world.lore.title.required')))
          return
        }
        const key = title.toLowerCase()
        if (seenTitles.has(key)) {
          errors.push(error('world', `world.lore.${index}.title`, label, t('builder.world.lore.title.duplicate')))
        } else {
          seenTitles.add(key)
        }
      })
    }
  }

  if (hasUnbalancedVariable(draft.world)) {
    errors.push(error('world', 'world', t('builder.world.custom.label'), t('builder.world.variables.unbalanced')))
  }

  const seenStatIds = new Set<string>()
  draft.stats.forEach((stat, i) => {
    const statLabel = stat.name.trim() || stat.id || t('builder.stats.unnamed')
    const withStat = (label: string) => `${statLabel} — ${label}`

    if (!stat.id.trim()) {
      errors.push(error('stats', `stats.${i}.id`, withStat(t('builder.field.label.statId')), t('builder.field.required')))
    } else if (!STAT_ID_RE.test(stat.id)) {
      errors.push(
        error('stats', `stats.${i}.id`, withStat(t('builder.field.label.statId')), t('builder.field.slugUnderscoreInvalid')),
      )
    }

    if (stat.id.trim() !== '') {
      if (seenStatIds.has(stat.id)) {
        errors.push(
          error('stats', `stats.${i}.id`, withStat(t('builder.field.label.statId')), t('builder.field.slugTaken', { slug: stat.id })),
        )
      } else {
        seenStatIds.add(stat.id)
      }
    }

    if (!stat.name.trim()) {
      errors.push(error('stats', `stats.${i}.name`, withStat(t('builder.stats.name')), t('builder.field.required')))
    } else if (stat.name.length > MAX_STAT_NAME) {
      errors.push(
        error('stats', `stats.${i}.name`, withStat(t('builder.stats.name')), t('builder.field.tooLong', { max: MAX_STAT_NAME })),
      )
    }

    if (stat.icon !== null && stat.icon.length > MAX_STAT_ICON) {
      errors.push(
        error('stats', `stats.${i}.icon`, withStat(t('builder.stats.icon')), t('builder.field.tooLong', { max: MAX_STAT_ICON })),
      )
    }

    if (stat.color !== null && !STAT_COLOR_RE.test(stat.color)) {
      errors.push(error('stats', `stats.${i}.color`, withStat(t('builder.stats.color')), t('builder.validate.colorInvalid')))
    }

    const rangeOk = stat.max > stat.min
    if (!rangeOk) {
      errors.push(error('stats', `stats.${i}.max`, withStat(t('builder.stats.max')), t('builder.validate.statMaxAboveMin')))
    } else if (stat.default < stat.min || stat.default > stat.max) {
      errors.push(
        error(
          'stats',
          `stats.${i}.default`,
          withStat(t('builder.stats.default')),
          t('builder.validate.statDefaultRange', { min: stat.min, max: stat.max }),
        ),
      )
    }

    if (stat.description !== null && stat.description.length > MAX_STAT_DESCRIPTION) {
      errors.push(
        error(
          'stats',
          `stats.${i}.description`,
          withStat(t('builder.stats.description')),
          t('builder.field.tooLong', { max: MAX_STAT_DESCRIPTION }),
        ),
      )
    }

    let previousFrom: number | null = null
    stat.levels.forEach((level, j) => {
      if (rangeOk && (level.from < stat.min || level.from > stat.max)) {
        errors.push(
          error(
            'stats',
            `stats.${i}.levels.${j}.from`,
            withStat(t('builder.stats.levels.from', { index: j + 1 })),
            t('builder.validate.levelFromRange', { min: stat.min, max: stat.max }),
          ),
        )
      }
      if (j > 0 && previousFrom !== null && level.from <= previousFrom) {
        errors.push(
          error(
            'stats',
            `stats.${i}.levels.${j}.from`,
            withStat(t('builder.stats.levels.from', { index: j + 1 })),
            t('builder.validate.levelFromOrder'),
          ),
        )
      }
      previousFrom = level.from

      if (!level.text.trim()) {
        errors.push(
          error(
            'stats',
            `stats.${i}.levels.${j}.text`,
            withStat(t('builder.stats.levels.text', { index: j + 1 })),
            t('builder.field.required'),
          ),
        )
      }
    })
  })

  return errors
}
