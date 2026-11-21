import { useState } from 'react'
import { Link } from 'react-router-dom'
import GroupShell, { useGroup } from '../components/GroupShell'
import { Badge, ErrorBox, Section, Spinner } from '../components/ui'
import { api } from '../services/api'
import { brl } from '../services/format'
import { usePolled } from '../services/hooks'

function Body() {
  const { group, reload: reloadGroup } = useGroup()
  const { data, error, loading, reload, setData } = usePolled(() => api.results(group.id), [group.id, group.status, group.me?.participant_id], 3000)
  const [busy, setBusy] = useState(null)
  const [actionError, setActionError] = useState(null)

  if (loading && !data) return <Spinner label="Carregando o placar..." />
  if (error) return <ErrorBox error={error} onRetry={reload} />

  const open = data.status === 'votacao_aberta'
  const total = data.total_votes
  const winnerId = data.winner_recommendation_id

  const vote = async (rid) => {
    setBusy(rid)
    setActionError(null)
    try {
      setData(await api.vote(group.id, rid))
      reloadGroup()
    } catch (e) {
      setActionError(e)
      reloadGroup()
    } finally {
      setBusy(null)
    }
  }

  const close = async () => {
    if (!window.confirm('Encerrar a votação agora? O restaurante com mais votos vence; em empate, vence o maior score coletivo.')) return
    setBusy('close')
    try {
      setData(await api.closeVoting(group.id))
      await reloadGroup()
    } catch (e) {
      setActionError(e)
    } finally {
      setBusy(null)
    }
  }

  if (!data.options.length) {
    return (
      <Section title="A votação abre depois do Match">
        <Link className="btn-primary" to={`/g/${group.id}/preferencias`}>Ir para preferências</Link>
      </Section>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      {winnerId && (
        <div className="card border-brand p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-brand">Escolha concluída</p>
          <h2 className="mt-1 text-2xl font-extrabold">
            {data.options.find((o) => o.recommendation_id === winnerId)?.restaurant.name}
          </h2>
          <p className="mt-2 text-sm">{data.decision_note}</p>
          <Link to={`/g/${group.id}/reserva`} className="btn-primary mt-4">Ir para a reserva</Link>
        </div>
      )}

      <Section
        title={open ? 'Vote no seu favorito' : 'Resultado da votação'}
        subtitle={open ? `Um voto por pessoa. Você pode trocar seu voto até a votação fechar. ${data.tie_rule}` : data.tie_rule}
        right={<Badge tone="brand">{total} de {data.participants} votaram</Badge>}
      >
        <ul className="flex flex-col gap-3">
          {data.options.map((o) => {
            const mine = data.my_vote === o.recommendation_id
            const pct = total ? Math.round((100 * o.votes) / total) : 0
            const leader = open && total > 0 && data.current_leader_id === o.recommendation_id
            return (
              <li key={o.recommendation_id}
                className={`rounded-2xl border p-4 ${o.recommendation_id === winnerId ? 'border-brand bg-brand-soft' : mine ? 'border-brand' : 'border-line'}`}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="font-bold">
                      {o.rank}. {o.restaurant.name} {leader && <Badge tone="brand">liderando</Badge>}
                    </p>
                    <p className="text-sm text-muted">
                      {o.restaurant.cuisine_label} · {brl(o.restaurant.avg_price)} · score coletivo {Math.round(o.score)}
                    </p>
                  </div>
                  {open && (
                    <button className={mine ? 'btn-primary py-2' : 'btn-secondary py-2'} disabled={!!busy || !group.me}
                      onClick={() => vote(o.recommendation_id)}>
                      {busy === o.recommendation_id ? 'Votando...' : mine ? '✓ Seu voto' : 'Votar aqui'}
                    </button>
                  )}
                </div>
                <div className="mt-3 h-2.5 rounded-full bg-line" aria-hidden>
                  <div className="h-2.5 rounded-full bg-brand transition-all" style={{ width: `${pct}%` }} />
                </div>
                <p className="mt-1.5 text-xs text-muted">
                  {o.votes} voto(s){o.voters.length ? `: ${o.voters.join(', ')}` : ''}
                </p>
              </li>
            )
          })}
        </ul>
        {open && data.pending_voters.length > 0 && (
          <p className="mt-4 text-sm text-muted">Ainda não votaram: {data.pending_voters.join(', ')}.</p>
        )}
        {open && data.vote_deadline && (
          <p className="mt-1 text-sm text-muted">A votação fecha sozinha em {new Date(data.vote_deadline).toLocaleString('pt-BR')}.</p>
        )}
        <p className="mt-2 text-xs text-muted">Placar atualizado automaticamente a cada 3 segundos.</p>
        <ErrorBox error={actionError} />
        {open && (group.is_organizer ? (
          <button className="btn-primary mt-4 w-full" onClick={close} disabled={!!busy}>
            {busy === 'close' ? 'Encerrando...' : 'Encerrar votação e definir o restaurante'}
          </button>
        ) : (
          <p className="mt-4 text-sm text-muted">Quem organiza encerra a votação.</p>
        ))}
      </Section>
    </div>
  )
}

export default function Voting() {
  return (
    <GroupShell>
      <Body />
    </GroupShell>
  )
}
