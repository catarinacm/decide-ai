import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import GroupShell, { useGroup } from '../components/GroupShell'
import { Badge, ErrorBox, ScoreRing, Section, Spinner } from '../components/ui'
import { api } from '../services/api'
import { brl, km } from '../services/format'
import { useMeta, usePolled } from '../services/hooks'

const COMPONENTS = [
  ['G', 'Gastronomia', '40%'],
  ['P', 'Preço e custo-benefício', '25%'],
  ['L', 'Localização', '20%'],
  ['A', 'Ambiente', '15%'],
]

function WhyTable({ rec }) {
  return (
    <div className="mt-3 overflow-x-auto rounded-xl border border-line">
      <table className="w-full min-w-[460px] text-sm">
        <thead className="bg-canvas text-left text-xs text-muted">
          <tr>
            <th className="px-3 py-2">Participante</th>
            {COMPONENTS.map(([k, label, w]) => <th key={k} className="px-2 py-2" title={label}>{k} <span className="font-normal">({w})</span></th>)}
            <th className="px-2 py-2">Distância</th>
            <th className="px-3 py-2 text-right">Score</th>
          </tr>
        </thead>
        <tbody>
          {rec.breakdown.map((b) => (
            <tr key={b.participant_id} className="border-t border-line">
              <td className="px-3 py-2 font-medium">{b.nickname}</td>
              {COMPONENTS.map(([k]) => (
                <td key={k} className={`px-2 py-2 ${b[k] < 40 ? 'text-brand font-semibold' : ''}`}>{Math.round(b[k])}</td>
              ))}
              <td className="px-2 py-2">{km(b.distance_km)}</td>
              <td className={`px-3 py-2 text-right font-bold ${b.score < 50 ? 'text-brand' : ''}`}>{Math.round(b.score)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot className="border-t border-line bg-canvas text-xs">
          <tr>
            <td className="px-3 py-2" colSpan={7}>
              Média do grupo {rec.mean_score.toFixed(1)}
              {rec.penalty > 0 ? <> − penalização {rec.penalty.toFixed(1)} (alguém ficou abaixo de 50)</> : ' (ninguém abaixo de 50, sem penalização)'}
              {' '}= <strong>{rec.score.toFixed(1)}</strong>
            </td>
          </tr>
        </tfoot>
      </table>
      <p className="px-3 py-2 text-xs text-muted">
        Score individual = 0,40·G + 0,25·P + 0,20·L + 0,15·A, cada componente de 0 a 100. Valores em vermelho são os pontos fracos.
      </p>
    </div>
  )
}

function RecommendationCard({ rec, onVote }) {
  const [open, setOpen] = useState(false)
  const r = rec.restaurant
  return (
    <article className="card overflow-hidden">
      <div className="flex gap-4 p-5">
        <div className="flex flex-col items-center gap-1">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand text-sm font-bold text-white">{rec.rank}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-lg font-extrabold leading-tight">{r.name}</h3>
              <p className="mt-0.5 text-sm text-muted">
                {r.cuisine_label} · {r.neighborhood} · {brl(r.avg_price)}/pessoa · ★ {r.rating.toFixed(1)} (fictícia)
              </p>
            </div>
            <ScoreRing score={rec.score} />
          </div>
          <p className="mt-2 text-sm">{r.description}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {r.dietary_labels.map((d) => <Badge key={d} tone="green">{d}</Badge>)}
            {r.ambience_labels.map((a) => <Badge key={a}>{a}</Badge>)}
            <Badge>média de {km(rec.avg_distance_km)} do grupo</Badge>
          </div>
          {r.simulated_benefit && <p className="mt-2 text-xs font-semibold text-brand-dark">Benefício simulado: {r.simulated_benefit.replace(' (simulado)', '')}</p>}
        </div>
      </div>

      <div className="border-t border-line bg-canvas/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-sm font-bold">Por que o iFood Match recomendou este restaurante?</h4>
          <Badge tone={rec.explanation_source === 'ia' ? 'brand' : 'neutral'}>
            {rec.explanation_source === 'ia' ? 'Explicação gerada por IA' : 'Explicação automática (regras)'}
          </Badge>
        </div>
        <p className="mt-2 text-sm leading-relaxed">{rec.explanation}</p>
        <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
          <strong>Ponto de atenção:</strong> {rec.attention_point}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="btn-ghost text-sm text-brand" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? 'Esconder detalhes' : 'Ver por que (score por pessoa)'}
          </button>
          {onVote}
        </div>
        {open && <WhyTable rec={rec} />}
      </div>
    </article>
  )
}

function NoEligible({ summary }) {
  const { group, reload } = useGroup()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const labels = { orcamento: 'Preço acima do teto', restricoes: 'Restrição alimentar não atendida',
    capacidade: 'Não comporta o grupo', horario: 'Fechado ou sem mesa no horário' }

  const apply = async (s) => {
    const patch = { orcamento: { budget_per_person: s.value }, horario: { event_time: s.value }, data: { event_date: s.value },
      capacidade: { party_size: s.value } }[s.type]
    setBusy(true)
    setError(null)
    try {
      await api.updateGroup(group.id, patch)
      await api.match(group.id, group.status === 'coletando_preferencias')
      await reload()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const canApply = (s) => group.is_organizer && ['horario', 'data', 'capacidade'].includes(s.type)
    || (group.is_organizer && s.type === 'orcamento' && summary.budget_source === 'grupo')

  return (
    <Section title="Nenhum restaurante atende a todos os critérios" subtitle={summary.conflict_message}>
      <div className="flex flex-col gap-2">
        {Object.entries(summary.eliminated_by).map(([k, n]) => (
          <div key={k}>
            <div className="flex justify-between text-sm"><span>{labels[k]}</span><span className="font-semibold">{n}</span></div>
            <div className="mt-1 h-2 rounded-full bg-line">
              <div className="h-2 rounded-full bg-brand" style={{ width: `${(100 * n) / summary.total_restaurants}%` }} />
            </div>
          </div>
        ))}
      </div>
      <h3 className="mt-6 font-bold">Ajustes que fariam surgir opções</h3>
      {summary.suggestions.length === 0 && <p className="mt-2 text-sm text-muted">Nenhum ajuste simples resolve; revejam as preferências.</p>}
      <ul className="mt-2 flex flex-col gap-2">
        {summary.suggestions.map((s, i) => (
          <li key={i} className="flex flex-col gap-2 rounded-xl border border-line p-3 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-sm">{s.message}</span>
            {canApply(s) ? (
              <button className="btn-secondary shrink-0 py-2 text-sm" disabled={busy} onClick={() => apply(s)}>Aplicar e refazer</button>
            ) : s.type === 'orcamento' || s.type === 'restricoes' ? (
              <button className="btn-ghost shrink-0 text-sm text-brand" onClick={() => navigate(`/g/${group.id}/preferencias`)}>Rever preferências</button>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-muted">Restrições alimentares nunca são relaxadas automaticamente.</p>
      <ErrorBox error={error} />
    </Section>
  )
}

function Body() {
  const { group } = useGroup()
  const meta = useMeta()
  const dietLabel = (d) => meta?.dietary_options.find((o) => o.value === d)?.label.toLowerCase() || d
  const { data, error, loading, reload } = usePolled(() => api.recommendations(group.id), [group.id, group.current_round, group.status], 6000)
  if (loading && !data) return <Spinner label="Carregando o Match..." />
  if (error) return <ErrorBox error={error} onRetry={reload} />

  const s = data.summary
  if (!data.recommendations.length) {
    if (s && s.eligible_count === 0) return <NoEligible summary={s} />
    return (
      <Section title="Ainda não há Match nesta rodada" subtitle="Quando o grupo estiver completo, gere o Match na tela de preferências.">
        <Link to={`/g/${group.id}/preferencias`} className="btn-primary">Ir para preferências</Link>
      </Section>
    )
  }

  const voting = group.status === 'votacao_aberta'
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2 rounded-2xl bg-white p-4 text-sm shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <p>
          <strong>Rodada {data.round_number}:</strong> {s.eligible_count} de {s.total_restaurants} restaurantes passaram nos filtros obrigatórios
          (teto de {brl(s.effective_budget)}{s.budget_source !== 'grupo' ? `, limite de ${s.budget_source}` : ''}
          {s.required_diets.length ? `; restrições: ${s.required_diets.map(dietLabel).join(', ')}` : ''}).
        </p>
        {voting && <Link to={`/g/${group.id}/votacao`} className="btn-primary shrink-0 py-2">Ir para a votação</Link>}
      </div>
      {s.forced && (
        <div className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
          Match gerado pelo organizador com quem já respondeu ({s.participants_included.join(', ')}).
          {s.participants_missing.length > 0 && <> Ficaram de fora: <strong>{s.participants_missing.join(', ')}</strong>.</>}
        </div>
      )}
      {data.recommendations.map((rec) => (
        <RecommendationCard key={rec.recommendation_id} rec={rec}
          onVote={voting ? <Link to={`/g/${group.id}/votacao`} className="btn-primary py-2 text-sm">Votar</Link> : null} />
      ))}
      <p className="text-xs text-muted">{data.dietary_disclaimer}</p>
    </div>
  )
}

export default function MatchResults() {
  return (
    <GroupShell poll={6000}>
      <Body />
    </GroupShell>
  )
}
