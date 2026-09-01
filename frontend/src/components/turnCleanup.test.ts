import { describe, expect, it } from 'vitest'
import { isEngineEchoLine } from './turnCleanup'

describe('isEngineEchoLine', () => {
  it.each([
    '# Turno 3',
    '**HUD**',
    'Local: pátio',
    '- **Hora:** 07:52',
    '**Você** | vou até a Chloe',
    '**You** | I walk',
  ])('returns true for %s', (line) => {
    expect(isEngineEchoLine(line)).toBe(true)
  })

  it.each([
    '**Chloe** | Local: aqui não',
    'Ela caminha pela vila.',
    '    Ele espera.',
    '',
  ])('returns false for %j', (line) => {
    expect(isEngineEchoLine(line)).toBe(false)
  })
})
