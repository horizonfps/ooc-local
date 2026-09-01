export class ApiError extends Error {
  status: number
  detail: string | null

  constructor(status: number, detail: string | null) {
    super(detail ? `HTTP ${status} — ${detail}` : `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function detailOf(response: Response): Promise<string | null> {
  try {
    const body = await response.json()
    if (body && typeof body === 'object' && typeof (body as { detail?: unknown }).detail === 'string') {
      return (body as { detail: string }).detail
    }
  } catch {
    // no JSON body, or not parseable
  }
  return null
}

export type ScenarioSummary = { id: string; name: string; tagline: string | null; locale: string }
export type HudState = { turn: number; location: string; time: string; weather: string }
export type TurnView = { index: number; role: 'player' | 'narrator'; text: string }
export type SessionSummary = {
  id: string
  scenarioId: string
  scenarioName: string
  turnCount: number
  updatedAt: string
  location: string
}
export type SessionDetail = {
  id: string
  scenarioId: string
  scenarioName: string
  prologue: string
  playGuide: string | null
  turns: TurnView[]
  hud: HudState
}

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response))
  }
  return response.json() as Promise<T>
}

export type BuilderScenarioItem = {
  id: string
  name: string
  tagline: string | null
  locale: string
  startCount: number
  characterCount: number
  hasCover: boolean
  updatedAt: string
  status: 'ok' | 'invalid'
  reason?: string
}

export function fetchScenarios(): Promise<ScenarioSummary[]> {
  return request('/api/scenarios')
}

export function fetchBuilderScenarios(): Promise<BuilderScenarioItem[]> {
  return request('/api/builder/scenarios')
}

export function fetchSessions(): Promise<SessionSummary[]> {
  return request('/api/sessions')
}

export function createSession(scenarioId: string): Promise<SessionDetail> {
  return request('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenarioId }),
  })
}

export function fetchSession(id: string): Promise<SessionDetail> {
  return request(`/api/sessions/${id}`)
}

export type TurnHandlers = {
  onDelta: (delta: string) => void
  onHud: (hud: HudState) => void
  onError: (err: unknown) => void
}

type TurnEvent = { delta?: string; hud?: HudState; error?: string }

export type TurnOptions = { signal?: AbortSignal }

export async function streamTurn(sessionId: string, message: string, h: TurnHandlers, options?: TurnOptions): Promise<void> {
  const signal = options?.signal
  let response: Response
  try {
    response = await fetch(`/api/sessions/${sessionId}/turn`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
      signal,
    })
  } catch (err) {
    if (signal?.aborted) return
    throw err
  }
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response))
  }
  if (!response.body) {
    throw new Error('missing response body')
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += value

      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''
      for (const part of parts) {
        const line = part.trim()
        if (!line.startsWith('data: ')) continue
        const data = line.slice('data: '.length)
        if (data === '[DONE]') return

        let parsed: TurnEvent
        try {
          parsed = JSON.parse(data)
        } catch {
          continue
        }
        if (parsed.error !== undefined) {
          h.onError(parsed.error)
        } else if (parsed.delta !== undefined) {
          h.onDelta(parsed.delta)
        } else if (parsed.hud !== undefined) {
          h.onHud(parsed.hud)
        }
      }
    }
  } catch (err) {
    if (signal?.aborted) {
      // cancel() on an errored stream rejects with the stored error;
      // an abort must resolve silently for every consumer
      await reader.cancel().catch(() => {})
      return
    }
    throw err
  }
}
