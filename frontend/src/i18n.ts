const strings = {
  en: {
    title: 'ooc-local',
    placeholder: 'Say something...',
    send: 'Send',
    error: 'Error',
  },
  'pt-br': {
    title: 'ooc-local',
    placeholder: 'Diga algo...',
    send: 'Enviar',
    error: 'Erro',
  },
} as const

export type Locale = keyof typeof strings
export type StringKey = keyof (typeof strings)['en']

const locale: Locale = navigator.language.toLowerCase().startsWith('pt') ? 'pt-br' : 'en'

export const t = (key: StringKey): string => strings[locale][key]
