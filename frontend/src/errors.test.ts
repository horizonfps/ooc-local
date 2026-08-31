import { describe, expect, it } from 'vitest'
import { describeError } from './errors'
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
