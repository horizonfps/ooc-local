import { t } from './i18n'

export type ErrorDescription = { title: string; body: string; cause: string }

function causeOf(err: unknown): string {
  if (err instanceof Error) return err.message
  return ''
}

export function describeError(err: unknown): ErrorDescription {
  const cause = causeOf(err)

  if (err instanceof TypeError) {
    return { title: t('error.offline.title'), body: t('error.offline.body'), cause }
  }

  if (typeof err === 'object' && err !== null && 'status' in err && (err as { status: unknown }).status === 503) {
    return { title: t('error.chatDisabled.title'), body: t('error.chatDisabled.body'), cause }
  }

  return { title: t('error.unexpected.title'), body: t('error.unexpected.body'), cause }
}
