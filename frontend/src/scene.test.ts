import { describe, expect, it } from 'vitest'
import { EMPTY_SCENE, MAX_SPRITES, reduceScene, resolveBackground, resolveSprite } from './scene'
import type { SessionAssets } from './api'

describe('reduceScene', () => {
  it('applies BG and SPRITE tags from a turn sequence', () => {
    let scene = reduceScene(EMPTY_SCENE, 'You arrive. [BG:patio] The yard is quiet. [SPRITE:chloe:sad]')
    expect(scene.background).toBe('patio')
    expect(scene.sprites).toEqual([{ character: 'chloe', emotion: 'sad' }])

    scene = reduceScene(scene, '[SPRITE:mika:default] Mika waves.')
    expect(scene.sprites).toEqual([
      { character: 'chloe', emotion: 'sad' },
      { character: 'mika', emotion: 'default' },
    ])
  })

  it('pushes the oldest sprite out past MAX_SPRITES', () => {
    const scene = reduceScene(
      EMPTY_SCENE,
      '[SPRITE:a:default][SPRITE:b:default][SPRITE:c:default][SPRITE:d:default]',
    )
    expect(scene.sprites).toHaveLength(MAX_SPRITES)
    expect(scene.sprites.map((s) => s.character)).toEqual(['b', 'c', 'd'])
  })

  it('promotes an existing character to the end of the queue on a new emotion', () => {
    const scene = reduceScene(EMPTY_SCENE, '[SPRITE:a:default][SPRITE:b:default][SPRITE:a:angry]')
    expect(scene.sprites).toEqual([
      { character: 'b', emotion: 'default' },
      { character: 'a', emotion: 'angry' },
    ])
  })

  it('leaves the state unchanged when a turn has no tag', () => {
    const scene = reduceScene(EMPTY_SCENE, '[BG:patio][SPRITE:chloe:sad]')
    const next = reduceScene(scene, 'Just narration, no tags here.')
    expect(next).toEqual(scene)
  })

  it('ignores an unclosed [SPRIT at the end of partial streamed text', () => {
    const scene = reduceScene(EMPTY_SCENE, 'Chloe looks up. [SPRIT')
    expect(scene).toEqual(EMPTY_SCENE)
  })

  it('ignores SPRITE tags with an empty argument or three parts', () => {
    const scene = reduceScene(EMPTY_SCENE, '[SPRITE:chloe:][SPRITE:a:b:c]')
    expect(scene.sprites).toEqual([])
  })

  it('matches SPRITE tags case-insensitively and normalizes the keys', () => {
    const scene = reduceScene(EMPTY_SCENE, '[SPRITE:CHLOE:Sad]')
    expect(scene.sprites).toEqual([{ character: 'chloe', emotion: 'sad' }])
  })
})

const assets: SessionAssets = {
  sprites: { chloe: { default: '/media/chloe/default.png', sad: '/media/chloe/sad.png' } },
  backgrounds: { patio: '/media/backgrounds/patio.png' },
}

describe('resolveSprite', () => {
  it('falls back to the default emotion when the requested one has no file', () => {
    expect(resolveSprite(assets, 'chloe', 'angry')).toBe('/media/chloe/default.png')
  })

  it('returns null for an unknown character', () => {
    expect(resolveSprite(assets, 'mika', 'default')).toBeNull()
  })
})

describe('resolveBackground', () => {
  it('returns null for a location without an asset, letting the caller keep the previous one', () => {
    expect(resolveBackground(assets, 'hallway')).toBeNull()
  })

  it('resolves a known location', () => {
    expect(resolveBackground(assets, 'patio')).toBe('/media/backgrounds/patio.png')
  })
})
