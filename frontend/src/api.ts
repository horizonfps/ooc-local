export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
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
    throw new ApiError(response.status, `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function fetchScenarios(): Promise<ScenarioSummary[]> {
  return request('/api/scenarios')
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
    throw new ApiError(response.status, `HTTP ${response.status}`)
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
