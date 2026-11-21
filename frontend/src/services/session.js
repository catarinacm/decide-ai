// Credenciais locais. Cada navegador guarda os tokens das pessoas que entraram nele (localStorage).
// Assim, recarregar a página recupera tudo, e "simular participante" troca de pessoa na mesma aba.

const KEY = 'ifoodmatch:groups'
const PREFS_KEY = 'ifoodmatch:lastPreferences'

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {}
  } catch {
    return {}
  }
}

function write(data) {
  try {
    localStorage.setItem(KEY, JSON.stringify(data))
  } catch {
    /* modo privado ou armazenamento cheio: segue sem persistir */
  }
}

export function getGroupSession(groupId) {
  return read()[groupId] || { identities: [], active: null, organizerToken: null }
}

export function saveIdentity(groupId, identity, { organizerToken, makeActive = true } = {}) {
  const all = read()
  const s = all[groupId] || { identities: [], active: null, organizerToken: null }
  const idx = s.identities.findIndex((i) => i.participant_id === identity.participant_id)
  s.identities = idx >= 0 ? s.identities.map((i, k) => (k === idx ? identity : i)) : [...s.identities, identity]
  if (makeActive) s.active = identity.participant_id
  if (organizerToken) s.organizerToken = organizerToken
  all[groupId] = { ...s, updatedAt: Date.now() }
  write(all)
}

export function setActive(groupId, participantId) {
  const all = read()
  if (!all[groupId]) return
  all[groupId].active = participantId
  write(all)
}

export function activeIdentity(groupId) {
  const s = getGroupSession(groupId)
  return s.identities.find((i) => i.participant_id === s.active) || s.identities[0] || null
}

export function authHeaders(groupId) {
  const s = getGroupSession(groupId)
  const me = activeIdentity(groupId)
  const h = {}
  if (me) h['X-Participant-Token'] = me.token
  if (s.organizerToken) h['X-Organizer-Token'] = s.organizerToken
  return h
}

export function recentGroups() {
  return Object.entries(read())
    .map(([id, s]) => ({ id, ...s }))
    .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
}

export function rememberPreferences(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
  } catch {
    /* sem persistência */
  }
}

export function lastPreferences() {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY))
  } catch {
    return null
  }
}
