export const brl = (v) =>
  `R$ ${Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`

export const km = (v) => `${Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} km`

export function dateLabel(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  const s = dt.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' })
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function nextSaturdayISO() {
  const d = new Date()
  const add = (6 - d.getDay() + 7) % 7 || 7
  d.setDate(d.getDate() + add)
  return localISO(d)
}

export function localISO(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export const STEPS = [
  { status: 'coletando_preferencias', label: 'Preferências' },
  { status: 'match_disponivel', label: 'Match' },
  { status: 'votacao_aberta', label: 'Votação' },
  { status: 'escolha_concluida', label: 'Escolha' },
  { status: 'reserva_simulada', label: 'Reserva' },
  { status: 'avaliado', label: 'Avaliação' },
]

export const stepIndex = (status) => STEPS.findIndex((s) => s.status === status)

// Para qual tela do grupo cada status leva.
export function screenFor(status) {
  if (status === 'coletando_preferencias' || status === 'match_disponivel') return 'preferencias'
  if (status === 'votacao_aberta') return 'match'
  return 'reserva'
}
