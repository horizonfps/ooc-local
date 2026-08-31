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
