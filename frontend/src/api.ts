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
