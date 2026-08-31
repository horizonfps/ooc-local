import { describe, expect, it } from 'vitest'
import { classifyError, describeError } from './errors'
import { t } from './i18n'

describe('describeError', () => {
  it('classifies a network TypeError as offline', () => {
    const result = describeError(new TypeError('Failed to fetch'))
    expect(result.title).toBe(t('error.offline.title'))
    expect(result.body).toBe(t('error.offline.body'))
    expect(result.cause).toBe('Failed to fetch')
  })

  it('classifies an object with status 503 as chat disabled', () => {
    const result = describeError({ status: 503 })
    expect(result.title).toBe(t('error.chatDisabled.title'))
    expect(result.body).toBe(t('error.chatDisabled.body'))
    expect(result.cause).toBe('')
  })

  it('classifies a generic Error as unexpected', () => {
    const result = describeError(new Error('boom'))
    expect(result.title).toBe(t('error.unexpected.title'))
    expect(result.body).toBe(t('error.unexpected.body'))
    expect(result.cause).toBe('boom')
  })

  it('classifies undefined as unexpected without throwing', () => {
    expect(() => describeError(undefined)).not.toThrow()
    const result = describeError(undefined)
    expect(result.title).toBe(t('error.unexpected.title'))
    expect(result.cause).toBe('')
  })

  it('classifies null as unexpected without throwing', () => {
    expect(() => describeError(null)).not.toThrow()
    const result = describeError(null)
    expect(result.title).toBe(t('error.unexpected.title'))
  })
})

describe('classifyError', () => {
  it('classifies a network TypeError as offline', () => {
    const result = classifyError(new TypeError('Failed to fetch'))
    expect(result.kind).toBe('offline')
    expect(result.cause).toBe('Failed to fetch')
  })

  it('classifies status 503 as chatDisabled', () => {
    const result = classifyError({ status: 503 })
    expect(result.kind).toBe('chatDisabled')
    expect(result.cause).toBe('')
  })

  it('classifies status 404 as notFound', () => {
    const result = classifyError({ status: 404 })
    expect(result.kind).toBe('notFound')
    expect(result.title).toBe(t('game.notFound.title'))
    expect(result.body).toBe(t('game.notFound.body'))
  })

  it('classifies a generic Error as unexpected', () => {
    const result = classifyError(new Error('x'))
    expect(result.kind).toBe('unexpected')
    expect(result.cause).toBe('x')
  })

  it('classifies undefined as unexpected', () => {
    const result = classifyError(undefined)
    expect(result.kind).toBe('unexpected')
    expect(result.cause).toBe('')
  })

  it('classifies null as unexpected', () => {
    const result = classifyError(null)
    expect(result.kind).toBe('unexpected')
    expect(result.cause).toBe('')
  })
})
