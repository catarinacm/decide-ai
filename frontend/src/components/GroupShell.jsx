import { createContext, useContext, useState } from 'react'
import { Link, NavLink, useNavigate, useParams } from 'react-router-dom'
import { api } from '../services/api'
import { brl, dateLabel, stepIndex, STEPS } from '../services/format'
import { usePolled } from '../services/hooks'
import { activeIdentity, getGroupSession, saveIdentity, setActive } from '../services/session'
import { Badge, ErrorBox, Spinner } from './ui'

// Sugestões de apelido (só no placeholder) para quem entra pelo mesmo aparelho.
const NAMES = ['Lia', 'Theo', 'Nina', 'Rafa', 'Malu', 'Caio', 'Bia', 'Duda', 'Gabi', 'Léo', 'Juju', 'Pedro', 'Mari', 'Tomás']

const GroupCtx = createContext(null)
export const useGroup = () => useContext(GroupCtx)

function Stepper({ status }) {
  const current = stepIndex(status)
  return (
    <ol className="flex w-full items-center gap-1" aria-label="Etapas do encontro">
      {STEPS.map((s, i) => (
        <li key={s.status} className="flex flex-1 flex-col items-center gap-1">
          <span className={`h-1.5 w-full rounded-full ${i <= current ? 'bg-brand' : 'bg-line'}`} />
          <span className={`hidden text-[11px] font-semibold sm:block ${i === current ? 'text-brand' : 'text-muted'}`}>
            {s.label}
          </span>
        </li>
      ))}
    </ol>
  )
}

function IdentityBar({ group, onChanged }) {
  const navigate = useNavigate()
  const session = getGroupSession(group.id)
  const me = activeIdentity(group.id)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')

  const taken = new Set(group.participants.map((p) => p.nickname.toLowerCase()))
  const suggestion = NAMES.find((n) => !taken.has(n.toLowerCase())) || 'Amigo'

  const add = async (e) => {
    e.preventDefault()
    const nickname = name.trim()
    if (nickname.length < 2) {
      setError({ message: 'Digite um apelido com pelo menos 2 letras.' })
      return
    }
    setBusy(true)
    setError(null)
    try {
      const out = await api.join({ invite_code: group.invite_code, nickname, is_simulated: true })
      saveIdentity(group.id, out.identity)
      setAdding(false)
      setName('')
      await onChanged()
      navigate(`/g/${group.id}/preferencias`)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const switchTo = async (pid) => {
    setActive(group.id, pid)
    await onChanged()
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl bg-canvas p-3 sm:flex-row sm:items-center sm:justify-between">
      <label className="flex items-center gap-2 text-sm">
        <span className="text-muted">Você está como</span>
        <select
          className="rounded-lg border border-line bg-white px-2 py-1.5 font-semibold"
          value={me?.participant_id || ''}
          onChange={(e) => switchTo(e.target.value)}
          aria-label="Trocar de participante"
        >
          {session.identities.map((i) => (
            <option key={i.participant_id} value={i.participant_id}>
              {i.nickname}{i.is_organizer ? ' · organizador(a)' : ''}
            </option>
          ))}
        </select>
      </label>
      {group.accepting_changes && !adding && (
        <button type="button" className="btn-ghost justify-start text-sm text-brand sm:justify-center"
          onClick={() => { setAdding(true); setError(null) }}>
          + Adicionar pessoa neste aparelho
        </button>
      )}
      {adding && (
        <form onSubmit={add} className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
          <input
            className="input py-2 text-sm sm:w-44"
            value={name}
            onChange={(e) => { setName(e.target.value); setError(null) }}
            placeholder={`Apelido, ex.: ${suggestion}`}
            aria-label="Apelido da pessoa"
            maxLength={30}
            autoComplete="off"
            autoFocus
          />
          <div className="flex gap-2">
            <button className="btn-primary flex-1 py-2 text-sm" disabled={busy}>{busy ? 'Adicionando...' : 'Adicionar'}</button>
            <button type="button" className="btn-ghost text-sm" onClick={() => { setAdding(false); setName(''); setError(null) }}>
              Cancelar
            </button>
          </div>
        </form>
      )}
      <ErrorBox error={error} />
    </div>
  )
}

export default function GroupShell({ children, poll = 4000 }) {
  const { id } = useParams()
  const hasIdentity = getGroupSession(id).identities.length > 0
  const { data: group, error, loading, reload } = usePolled(() => api.group(id), [id], hasIdentity ? poll : 0)

  if (!hasIdentity || error?.status === 401) {
    return (
      <div className="card mx-auto max-w-md p-6 text-center">
        <h1 className="text-xl font-bold">Entre pelo convite</h1>
        <p className="mt-2 text-muted">
          Para ver este encontro, abra o link de convite que o organizador compartilhou e escolha um apelido.
        </p>
        <Link to="/" className="btn-primary mt-5">Voltar ao início</Link>
      </div>
    )
  }
  if (loading && !group) return <Spinner />
  if (!group) return <ErrorBox error={error} onRetry={reload} />

  const tabs = [
    { to: 'preferencias', label: 'Preferências', enabled: true },
    { to: 'match', label: 'Match', enabled: group.current_round > 0 || !!group.match_summary },
    { to: 'votacao', label: 'Votação', enabled: ['votacao_aberta', 'escolha_concluida', 'reserva_simulada', 'avaliado'].includes(group.status) },
    { to: 'reserva', label: 'Reserva', enabled: ['escolha_concluida', 'reserva_simulada', 'avaliado'].includes(group.status) },
  ]

  return (
    <GroupCtx.Provider value={{ group, reload }}>
      <div className="flex flex-col gap-5">
        <div className="card flex flex-col gap-4 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-extrabold sm:text-2xl">{group.name}</h1>
              </div>
              <p className="mt-1 text-sm text-muted">
                {dateLabel(group.event_date)} · {group.event_time} · {group.neighborhood}
              </p>
              <p className="text-sm text-muted">
                Até {brl(group.budget_per_person)} por pessoa · {group.party_size} pessoas
                {group.occasion_label ? ` · ${group.occasion_label}` : ''}
              </p>
            </div>
            <Badge tone="brand">{group.status_label}</Badge>
          </div>
          <Stepper status={group.status} />
          <IdentityBar group={group} onChanged={reload} />
        </div>

        <nav className="flex gap-1 overflow-x-auto rounded-2xl bg-white p-1 shadow-sm" aria-label="Telas do encontro">
          {tabs.map((t) =>
            t.enabled ? (
              <NavLink
                key={t.to}
                to={`/g/${id}/${t.to}`}
                className={({ isActive }) =>
                  `flex-1 whitespace-nowrap rounded-xl px-3 py-2 text-center text-sm font-semibold ${isActive ? 'bg-brand text-white' : 'text-ink hover:bg-canvas'}`}
              >
                {t.label}
              </NavLink>
            ) : (
              <span key={t.to} className="flex-1 whitespace-nowrap rounded-xl px-3 py-2 text-center text-sm font-semibold text-muted/50">
                {t.label}
              </span>
            ),
          )}
        </nav>

        {children}
      </div>
    </GroupCtx.Provider>
  )
}
