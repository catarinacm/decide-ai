import { useState } from 'react'
import { ErrorBox, Section, Spinner } from '../components/ui'
import { api } from '../services/api'
import { usePolled } from '../services/hooks'

function Stat({ label, value, hint }) {
  return (
    <div className="card p-5">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-3xl font-extrabold">{value ?? '—'}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

export default function Metrics() {
  const [includeDemo, setIncludeDemo] = useState(false)
  const { data: m, error, loading, reload } = usePolled(() => api.metrics(includeDemo), [includeDemo], 15000)

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-extrabold">Métricas do funil</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Calculadas a partir dos eventos registrados de verdade a cada ação no app. São dados de uso deste protótipo
            (testes e demonstrações), <strong>não conversões reais</strong> nem resultado de negócio.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm font-medium">
          <input type="checkbox" className="h-4 w-4 accent-brand" checked={includeDemo} onChange={(e) => setIncludeDemo(e.target.checked)} />
          Incluir grupos de demonstração
        </label>
      </div>

      {loading && !m && <Spinner />}
      <ErrorBox error={error} onRetry={reload} />
      {m && (
        <>
          <div className="card flex flex-col gap-2 border-brand p-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-bold uppercase tracking-wide text-brand">Métrica principal</p>
              <p className="mt-1 text-lg font-semibold">{m.main_metric.label}</p>
              <p className="text-sm text-muted">{m.main_metric.numerator} de {m.main_metric.denominator} grupos</p>
            </div>
            <p className="text-5xl font-extrabold text-brand">
              {m.main_metric.value_pct == null ? '—' : `${m.main_metric.value_pct.toLocaleString('pt-BR')}%`}
            </p>
          </div>

          <Section title="Funil" subtitle="Grupos que chegaram a cada etapa (contagem de grupos distintos).">
            <div className="flex flex-col gap-3">
              {m.funnel.map((s) => (
                <div key={s.step}>
                  <div className="flex justify-between text-sm">
                    <span className="font-medium">{s.label}</span>
                    <span className="text-muted">
                      {s.groups} {s.pct_of_created != null && `· ${s.pct_of_created.toLocaleString('pt-BR')}%`}
                    </span>
                  </div>
                  <div className="mt-1 h-3 rounded-full bg-line">
                    <div className="h-3 rounded-full bg-brand" style={{ width: `${s.pct_of_created || 0}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </Section>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Tempo médio até a decisão" value={m.avg_minutes_to_decision != null ? `${m.avg_minutes_to_decision.toLocaleString('pt-BR')} min` : null}
              hint="Da criação do grupo até a escolha concluída." />
            <Stat label="Taxa de participação" value={m.participation_rate_pct != null ? `${m.participation_rate_pct.toLocaleString('pt-BR')}%` : null}
              hint={`${m.participants_answered} de ${m.participants_expected} pessoas esperadas responderam.`} />
            <Stat label="Explicações com IA" value={m.ai.calls ? `${m.ai.ia}/${m.ai.calls}` : null}
              hint={`${m.ai.fallback} chamada(s) caíram no fallback por regras.`} />
            <Stat label="Avaliação média" value={m.reviews.average != null ? `${m.reviews.average.toLocaleString('pt-BR')} ★` : null}
              hint={`${m.reviews.count} avaliação(ões); ${m.decisions_by_tiebreak} decisão(ões) por desempate; ${m.rounds_invalidated} rodada(s) invalidada(s).`} />
          </div>
          <p className="text-xs text-muted">{m.notice}</p>
        </>
      )}
    </div>
  )
}
