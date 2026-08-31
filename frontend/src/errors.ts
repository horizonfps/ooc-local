import { t } from './i18n'

export type ErrorKind = 'offline' | 'chatDisabled' | 'notFound' | 'unexpected'
export type ErrorDescription = { title: string; body: string; cause: string }

function causeOf(err: unknown): string {
  if (err instanceof Error) return err.message
  return ''
}

function statusOf(err: unknown): number | undefined {
  if (typeof err === 'object' && err !== null && 'status' in err) {
    return (err as { status: unknown }).status as number | undefined
  }
  return undefined
}

export function classifyError(err: unknown): ErrorDescription & { kind: ErrorKind } {
  const cause = causeOf(err)

  if (err instanceof TypeError) {
    return { kind: 'offline', title: t('error.offline.title'), body: t('error.offline.body'), cause }
  }

  const status = statusOf(err)
  if (status === 503) {
    return { kind: 'chatDisabled', title: t('error.chatDisabled.title'), body: t('error.chatDisabled.body'), cause }
  }
  if (status === 404) {
    return { kind: 'notFound', title: t('game.notFound.title'), body: t('game.notFound.body'), cause }
  }

  return { kind: 'unexpected', title: t('error.unexpected.title'), body: t('error.unexpected.body'), cause }
}

export function describeError(err: unknown): ErrorDescription {
  const { title, body, cause } = classifyError(err)
  return { title, body, cause }
}
