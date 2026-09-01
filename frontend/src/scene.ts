import { TAG_RE } from './components/TurnText'
import type { SessionAssets } from './api'

export type SceneState = {
  background: string | null
  sprites: { character: string; emotion: string }[]
}

export const MAX_SPRITES = 3

export const EMPTY_SCENE: SceneState = { background: null, sprites: [] }

export function reduceScene(state: SceneState, text: string): SceneState {
  let background = state.background
  let sprites = state.sprites

  TAG_RE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = TAG_RE.exec(text)) !== null) {
    const kind = match[1]
    const args = match[2]

    if (kind === 'BG') {
      const location = args.trim().toLowerCase()
      if (location === '') continue
      background = location
    } else if (kind === 'SPRITE') {
      const parts = args.split(':')
      if (parts.length !== 2) continue
      const character = parts[0].trim().toLowerCase()
      const emotion = parts[1].trim().toLowerCase()
      if (character === '' || emotion === '') continue

      const next = sprites.filter((s) => s.character !== character)
      next.push({ character, emotion })
      sprites = next.length > MAX_SPRITES ? next.slice(next.length - MAX_SPRITES) : next
    }
  }

  if (background === state.background && sprites === state.sprites) return state
  return { background, sprites }
}

export function resolveSprite(assets: SessionAssets, character: string, emotion: string): string | null {
  const perCharacter = assets.sprites[character]
  if (!perCharacter) return null
  return perCharacter[emotion] ?? perCharacter['default'] ?? null
}

export function resolveBackground(assets: SessionAssets, location: string): string | null {
  return assets.backgrounds[location] ?? null
}
