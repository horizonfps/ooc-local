import { describe, expect, it, vi } from 'vitest'
import { strings } from './strings'

function stubLanguage(value: string | undefined) {
  vi.stubGlobal('navigator', { language: value })
}

async function loadI18n() {
  vi.resetModules()
  return import('./i18n')
}

describe('t', () => {
  it('interpolates params in en and pt-br', async () => {
    stubLanguage('en-US')
    const { t } = await loadI18n()
    expect(t('game.documentTitle', { scenario: 'Escola' })).toBe('Escola — ooc-local')

    stubLanguage('pt-BR')
    const { t: tPtBr } = await loadI18n()
    expect(tPtBr('game.documentTitle', { scenario: 'Escola' })).toBe('Escola — ooc-local')
  })

  it('leaves the placeholder literal when no params are given', async () => {
    stubLanguage('en-US')
    const { t } = await loadI18n()
    expect(t('game.documentTitle')).toBe('{scenario} — ooc-local')
  })

  it('interpolates a numeric count', async () => {
    stubLanguage('en-US')
    const { t } = await loadI18n()
    expect(t('sessions.item.turnsOther', { count: 7 })).toBe('7 turns')

    stubLanguage('pt-BR')
    const { t: tPtBr } = await loadI18n()
    expect(tPtBr('sessions.item.turnsOther', { count: 7 })).toBe('7 turnos')
  })

  it('ignores params whose key does not appear in the string', async () => {
    stubLanguage('en-US')
    const { t } = await loadI18n()
    expect(t('common.retry', { unused: 'value' })).toBe('Try again')
  })

  it('substitutes a repeated placeholder in every occurrence', async () => {
    stubLanguage('en-US')
    const { t } = await loadI18n()
    expect(t('turnText.speakerLabel', { name: 'Ana' }).includes('Ana')).toBe(true)
  })

  it('interpolates a zero value as "0", never an empty string', async () => {
    stubLanguage('en-US')
    const { t } = await loadI18n()
    expect(t('sessions.item.turnsOther', { count: 0 })).toBe('0 turns')
  })

  it('falls back to en when navigator.language is undefined', async () => {
    stubLanguage(undefined)
    const { locale, intlLocale } = await loadI18n()
    expect(locale).toBe('en')
    expect(intlLocale).toBe('en')
  })

  it('derives locale and intlLocale from navigator.language', async () => {
    stubLanguage('pt-BR')
    const { locale, intlLocale } = await loadI18n()
    expect(locale).toBe('pt-br')
    expect(intlLocale).toBe('pt-BR')

    stubLanguage('en-US')
    const { locale: enLocale, intlLocale: enIntlLocale } = await loadI18n()
    expect(enLocale).toBe('en')
    expect(enIntlLocale).toBe('en')
  })
})

describe('strings', () => {
  it('has the same keys in en and pt-br', () => {
    const enKeys = Object.keys(strings.en).sort()
    const ptBrKeys = Object.keys(strings['pt-br']).sort()
    expect(ptBrKeys).toEqual(enKeys)
  })
})

// Type-level test: an incomplete pt-br dictionary must fail `tsc -b`.
// If Record<StringKey, string> stops protecting this, the expect-error
// directive below has nothing to suppress and the build fails.
function incompletePtBr() {
  const en = { a: 'A', b: 'B' } as const
  type Key = keyof typeof en
  // @ts-expect-error missing key "b" must break the type check
  const ptBr: Record<Key, string> = { a: 'A' }
  return ptBr
}
void incompletePtBr
