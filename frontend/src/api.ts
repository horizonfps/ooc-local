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
export type SessionAssets = {
  sprites: Record<string, Record<string, string>>
  backgrounds: Record<string, string>
}
export type CastMember = { id: string; name: string }
export type SessionDetail = {
  id: string
  scenarioId: string
  scenarioName: string
  prologue: string
  playGuide: string | null
  turns: TurnView[]
  hud: HudState
  assets: SessionAssets
  cast: CastMember[]
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

export function createBuilderScenario(body: { folder: string; name: string; locale: string }): Promise<BuilderScenarioItem> {
  return request('/api/builder/scenarios', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function duplicateBuilderScenario(id: string, folder: string): Promise<BuilderScenarioItem> {
  return request(`/api/builder/scenarios/${id}/duplicate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder }),
  })
}

export async function deleteBuilderScenario(id: string): Promise<void> {
  const response = await fetch(`/api/builder/scenarios/${id}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response))
  }
}

export type ScenarioMeta = {
  name: string
  tagline: string | null
  description: string | null
  locale: 'en' | 'pt-br'
  tags: string[]
  default_start: string
  world_mode: 'guided' | 'custom'
}

export type HudDefaults = { location: string; time: string; weather: string }

export type StartDoc = {
  id: string
  name: string
  prologue: string
  opening_scene: string
  conflict: string | null
  mission: string | null
  play_guide: string | null
  suggestions: string[]
  hud: HudDefaults
  characters: string[] | null
}

export type CharacterMind = {
  feeling: string
  goal: string
  opinion_of_player: string | null
  secret_plan: string | null
}

export type CharacterDoc = {
  name: string
  role: string
  appearance: string
  personality: string
  voice: string
  mind: CharacterMind
  sprite: string | null
  power_tier: number | null
  emotions: string[]
}

export type ScenarioDocument = {
  revision: string
  meta: ScenarioMeta
  world: string
  starts: Record<string, StartDoc>
  characters: Record<string, CharacterDoc>
}

export function fetchScenarioDocument(id: string): Promise<ScenarioDocument> {
  return request(`/api/builder/scenarios/${id}`)
}

export async function saveScenarioDocument(
  id: string,
  doc: ScenarioDocument,
  force?: boolean,
): Promise<{ revision: string }> {
  const response = await fetch(`/api/builder/scenarios/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...doc, force: force ?? false }),
  })
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response))
  }
  return response.json() as Promise<{ revision: string }>
}

export type MediaIndex = { cover: string | null; sprites: Record<string, Record<string, string>>; backgrounds: Record<string, string> }

export function fetchMediaIndex(id: string): Promise<MediaIndex> {
  return request(`/api/builder/scenarios/${id}/media`)
}

export type MediaTarget = { kind: 'cover' | 'sprite' | 'background'; key: string; character?: string }

export async function uploadMedia(id: string, target: MediaTarget, file: File): Promise<{ path: string; url: string }> {
  const formData = new FormData()
  formData.append('kind', target.kind)
  formData.append('key', target.key)
  if (target.character !== undefined) formData.append('character', target.character)
  formData.append('file', file)
  const response = await fetch(`/api/builder/scenarios/${id}/media`, { method: 'POST', body: formData })
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response))
  }
  return response.json() as Promise<{ path: string; url: string }>
}

export async function deleteMedia(id: string, target: MediaTarget): Promise<void> {
  const params = new URLSearchParams({ kind: target.kind, key: target.key })
  if (target.character !== undefined) params.set('character', target.character)
  const response = await fetch(`/api/builder/scenarios/${id}/media?${params.toString()}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response))
  }
}

export function fetchSessions(): Promise<SessionSummary[]> {
  return request('/api/sessions')
}

export function createSession(scenarioId: string, opts?: { startId?: string; ephemeral?: boolean }): Promise<SessionDetail> {
  return request('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenarioId, ...(opts?.startId !== undefined ? { startId: opts.startId } : {}), ...(opts?.ephemeral !== undefined ? { ephemeral: opts.ephemeral } : {}) }),
  })
}

export function fetchSession(id: string): Promise<SessionDetail> {
  return request(`/api/sessions/${id}`)
}

export async function deleteSession(id: string, opts?: { keepalive?: boolean }): Promise<void> {
  const response = await fetch(`/api/sessions/${id}`, { method: 'DELETE', keepalive: opts?.keepalive })
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response))
  }
}

export type TurnHudPayload = HudState & { cast?: CastMember[] }

export type TurnHandlers = {
  onDelta: (delta: string) => void
  onHud: (hud: TurnHudPayload) => void
  onError: (err: unknown) => void
}

type TurnEvent = { delta?: string; hud?: TurnHudPayload; error?: string }

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
