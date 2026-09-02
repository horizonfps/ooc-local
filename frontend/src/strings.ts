import { builderEn, builderPtBr } from './strings/builder'
import { commonEn, commonPtBr } from './strings/common'
import { gameEn, gamePtBr } from './strings/game'

const en = { ...commonEn, ...builderEn, ...gameEn } as const

export type StringKey = keyof typeof en

const ptBr: Record<StringKey, string> = { ...commonPtBr, ...builderPtBr, ...gamePtBr }

export const strings = { en, 'pt-br': ptBr }
