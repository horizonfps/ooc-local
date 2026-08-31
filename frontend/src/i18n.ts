import { strings } from './strings'
import type { StringKey } from './strings'

export type { StringKey } from './strings'
export type Locale = keyof typeof strings

export const locale: Locale = (navigator.language ?? '').toLowerCase().startsWith('pt') ? 'pt-br' : 'en'
export const intlLocale: string = locale === 'pt-br' ? 'pt-BR' : 'en'

export function t(key: StringKey, params?: Record<string, string | number>): string {
  const raw = strings[locale][key]
  if (!params) return raw
  return raw.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match))
}
