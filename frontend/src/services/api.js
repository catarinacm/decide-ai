// Cliente da API. O frontend fala só com o backend; nenhuma chave passa por aqui.
import { authHeaders } from './session'

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

// --- aviso de "acordando o servidor" (plano gratuito do Render hiberna) -----------------
const listeners = new Set()
let pending = 0
let waking = false

function setWaking(v) {
  if (v !== waking) {
    waking = v
    listeners.forEach((fn) => fn(v))
  }
}

export function onWaking(fn) {
  listeners.add(fn)
  fn(waking)
  return () => listeners.delete(fn)
}

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

// Só leituras são repetidas automaticamente; repetir um POST poderia, por exemplo, criar dois grupos.
async function request(method, path, { body, groupId, headers = {}, retries = method === 'GET' ? 1 : 0 } = {}) {
  pending += 1
  const slow = setTimeout(() => setWaking(true), 2500)
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 75000)
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(groupId ? authHeaders(groupId) : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
    const data = res.status === 204 ? null : await res.json().catch(() => null)
    if (!res.ok) {
      const err = data?.error || {}
      throw new ApiError(res.status, err.code || 'erro', err.message || 'Algo deu errado. Tente de novo.', err.details)
    }
    return data
  } catch (e) {
    if (e instanceof ApiError) throw e
    // Falha de rede: o servidor pode estar acordando. Tenta mais uma vez antes de desistir.
    if (retries > 0) {
      await new Promise((r) => setTimeout(r, 3000))
      return request(method, path, { body, groupId, headers, retries: retries - 1 })
    }
    throw new ApiError(0, 'sem_conexao', 'Não conseguimos falar com o servidor. Verifique a conexão e tente de novo.')
  } finally {
    clearTimeout(slow)
    clearTimeout(timeout)
    pending -= 1
    if (pending === 0) setWaking(false)
  }
}

export const api = {
  health: () => request('GET', '/health'),
  meta: () => request('GET', '/meta'),
  createGroup: (body) => request('POST', '/groups', { body }),
  preview: (code) => request('GET', `/groups/by-code/${encodeURIComponent(code)}`),
  join: (body) => request('POST', '/groups/join', { body }),
  group: (id) => request('GET', `/groups/${id}`, { groupId: id }),
  updateGroup: (id, body) => request('PATCH', `/groups/${id}`, { body, groupId: id }),
  savePreferences: (groupId, participantId, body) =>
    request('PUT', `/participants/${participantId}/preferences`, { body, groupId }),
  parsePreferences: (groupId, text) => request('POST', '/ai/parse-preferences', { body: { text }, groupId }),
  match: (id, force = false) => request('POST', `/groups/${id}/match`, { body: { force }, groupId: id }),
  recommendations: (id) => request('GET', `/groups/${id}/recommendations`, { groupId: id }),
  vote: (id, recommendationId) =>
    request('POST', `/groups/${id}/votes`, { body: { recommendation_id: recommendationId }, groupId: id }),
  results: (id) => request('GET', `/groups/${id}/results`, { groupId: id }),
  closeVoting: (id) => request('POST', `/groups/${id}/close-voting`, { groupId: id }),
  reserve: (id) => request('POST', `/groups/${id}/reservations`, { groupId: id }),
  review: (groupId, reservationId, body) =>
    request('POST', `/reservations/${reservationId}/reviews`, { body, groupId }),
  demo: () => request('POST', '/demo'),
  metrics: (includeDemo) => request('GET', `/metrics?include_demo=${includeDemo ? 'true' : 'false'}`),
}
