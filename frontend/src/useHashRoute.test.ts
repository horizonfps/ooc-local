import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { navigate, useHashRoute } from './useHashRoute'

function setHash(hash: string) {
  location.hash = hash
}

beforeEach(() => {
  location.hash = ''
})

afterEach(() => {
  location.hash = ''
})

describe('useHashRoute', () => {
  it('resolves sessions for empty, root and unknown hash', () => {
    setHash('')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'sessions' })

    setHash('#/')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'sessions' })

    setHash('#/foo')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'sessions' })
  })

  it('resolves sessions for a session hash with no id', () => {
    setHash('#/session/')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'sessions' })
  })

  it('resolves builderList for #/builder and #/builder/', () => {
    setHash('#/builder')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'builderList' })

    setHash('#/builder/')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'builderList' })
  })

  it('does not normalize #/builder away', () => {
    setHash('#/builder')
    renderHook(() => useHashRoute())
    expect(location.hash).toBe('#/builder')
  })

  it('resolves game with the id from the hash', () => {
    setHash('#/session/abc')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'game', id: 'abc' })
  })

  it('normalizes an unknown hash to #/ without throwing', () => {
    setHash('#/whatever')
    renderHook(() => useHashRoute())
    expect(location.hash).toBe('#/')
  })

  it('updates on hashchange and removes the listener on unmount', () => {
    setHash('#/')
    const { result, unmount } = renderHook(() => useHashRoute())
    expect(result.current).toEqual({ name: 'sessions' })

    act(() => {
      location.hash = '#/session/abc'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    expect(result.current).toEqual({ name: 'game', id: 'abc' })

    unmount()
    act(() => {
      location.hash = '#/session/xyz'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    // No assertion possible on internal state after unmount; absence of an error is the assertion.
  })

  it('last hashchange wins when two fire in a row', () => {
    setHash('#/')
    const { result } = renderHook(() => useHashRoute())

    act(() => {
      location.hash = '#/session/first'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
      location.hash = '#/session/second'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })

    expect(result.current).toEqual({ name: 'game', id: 'second' })
  })

  it('resolves builderEditor for #/builder/{id}/{tab}', () => {
    setHash('#/builder/school/world')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'builderEditor', id: 'school', tab: 'world' })
  })

  it('resolves #/builder/school/stats', () => {
    setHash('#/builder/school/stats')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'builderEditor', id: 'school', tab: 'stats' })
  })

  it('resolves #/builder/school/lorebook', () => {
    setHash('#/builder/school/lorebook')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'builderEditor', id: 'school', tab: 'lorebook' })
  })

  it('resolves #/builder/school/commands', () => {
    setHash('#/builder/school/commands')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'builderEditor', id: 'school', tab: 'commands' })
  })

  it('falls back to identity for an unknown tab', () => {
    setHash('#/builder/school/nope')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'builderEditor', id: 'school', tab: 'identity' })
  })

  it('resolves builderEditor with identity and replaces the hash when the tab is missing', () => {
    setHash('#/builder/school')
    expect(renderHook(() => useHashRoute()).result.current).toEqual({ name: 'builderEditor', id: 'school', tab: 'identity' })
    expect(location.hash).toBe('#/builder/school/identity')
  })

  it('does not re-replace once the hash already carries a tab', () => {
    setHash('#/builder/school')
    renderHook(() => useHashRoute())
    expect(location.hash).toBe('#/builder/school/identity')

    // a second mount on the now-normalized hash must not trigger another replace
    const { result } = renderHook(() => useHashRoute())
    expect(result.current).toEqual({ name: 'builderEditor', id: 'school', tab: 'identity' })
    expect(location.hash).toBe('#/builder/school/identity')
  })

  it('navigates by setting location.hash', () => {
    setHash('#/')
    navigate('#/session/abc')
    expect(location.hash).toBe('#/session/abc')
  })

  it('normalizes a malformed hash passed to navigate without throwing', () => {
    setHash('#/')
    expect(() => navigate('session/abc')).not.toThrow()
    expect(location.hash).toBe('#/')
  })
})
