import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useUnsavedGuard } from './useUnsavedGuard'

function setHash(hash: string) {
  location.hash = hash
}

function fireHashChange() {
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

function isDialogOpen(): boolean {
  const dialog = document.querySelector('.unsaved-guard-dialog')
  return dialog !== null && dialog.hasAttribute('open')
}

beforeEach(() => {
  location.hash = '#/builder/school/identity'
})

afterEach(() => {
  location.hash = ''
})

describe('useUnsavedGuard', () => {
  it('restores the hash and opens the leave dialog when dirty and navigating away by hash', () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const onDiscard = vi.fn()
    renderHook(() => useUnsavedGuard(true, { scenarioId: 'school', onSave, onDiscard }))

    act(() => {
      setHash('#/builder')
      fireHashChange()
    })

    expect(location.hash).toBe('#/builder/school/identity')
    expect(isDialogOpen()).toBe(true)
  })

  it('lets navigation to another tab of the same scenario go through without opening the dialog', () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const onDiscard = vi.fn()
    renderHook(() => useUnsavedGuard(true, { scenarioId: 'school', onSave, onDiscard }))

    act(() => {
      setHash('#/builder/school/world')
      fireHashChange()
    })

    expect(location.hash).toBe('#/builder/school/world')
    expect(isDialogOpen()).toBe(false)
  })

  it('does not intercept anything when dirty is false', () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const onDiscard = vi.fn()
    renderHook(() => useUnsavedGuard(false, { scenarioId: 'school', onSave, onDiscard }))

    act(() => {
      setHash('#/builder')
      fireHashChange()
    })

    expect(location.hash).toBe('#/builder')
    expect(isDialogOpen()).toBe(false)
  })

  it('only calls preventDefault on beforeunload when dirty', () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const onDiscard = vi.fn()
    const { rerender } = renderHook(({ dirty }) => useUnsavedGuard(dirty, { scenarioId: 'school', onSave, onDiscard }), {
      initialProps: { dirty: false },
    })

    const cleanEvent = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(cleanEvent)
    expect(cleanEvent.defaultPrevented).toBe(false)

    rerender({ dirty: true })

    const dirtyEvent = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirtyEvent)
    expect(dirtyEvent.defaultPrevented).toBe(true)
  })

  it('removes its listeners and dialog on unmount', () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const onDiscard = vi.fn()
    const { unmount } = renderHook(() => useUnsavedGuard(true, { scenarioId: 'school', onSave, onDiscard }))

    expect(document.querySelector('.unsaved-guard-dialog')).not.toBeNull()
    unmount()
    expect(document.querySelector('.unsaved-guard-dialog')).toBeNull()

    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)

    act(() => {
      setHash('#/builder')
      fireHashChange()
    })
    expect(location.hash).toBe('#/builder')
  })
})
