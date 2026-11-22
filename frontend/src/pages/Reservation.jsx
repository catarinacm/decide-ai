import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import GroupShell, { useGroup } from '../components/GroupShell'
import { Badge, ErrorBox, Section } from '../components/ui'
import { api } from '../services/api'
import { brl, dateLabel } from '../services/format'
import { rememberPreferences } from '../services/session'

function Stars({ value, onChange }) {
  return (
    <div className="flex gap-1" role="radiogroup" aria-label="Nota de 1 a 5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} estrela(s)`}
          className={`text-3xl leading-none ${n <= value ? 'text-brand' : 'text-line'}`} onClick={() => onChange(n)}>
          ★
        </button>
      ))}
    </div>
  )
}

function Review({ reservation }) {
  const { group, reload } = useGroup()
  const mine = reservation.my_review
  const [rating, setRating] = useState(mine?.rating || 0)
  const [comment, setComment] = useState(mine?.comment || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.review(group.id, reservation.id, { rating, comment: comment || null })
      setDone(true)
      await reload()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section title="Como foi?" subtitle="Depois da visita (simulada), cada um avalia o encontro. Isso ajuda as próximas recomendações.">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Stars value={rating} onChange={setRating} />
        <textarea className="input min-h-20" maxLength={500} placeholder="Comentário (opcional)" value={comment}
          onChange={(e) => setComment(e.target.value)} />
        <ErrorBox error={error} />
        <button className="btn-primary" disabled={busy || rating === 0 || !group.me}>
          {busy ? 'Enviando...' : mine ? 'Atualizar avaliação' : 'Enviar avaliação'}
        </button>
        {done && <p className="text-sm text-green-700">Obrigado! Avaliação registrada.</p>}
        {reservation.reviews.count > 0 && (
          <p className="text-sm text-muted">
            Média do grupo: <strong>{reservation.reviews.average}</strong> ★ ({reservation.reviews.count} avaliação(ões))
          </p>
        )}
      </form>
    </Section>
  )
}

function Body() {
  const { group, reload } = useGroup()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const res = group.reservation
  const winner = group.winner

  const reserve = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.reserve(group.id)
      await reload()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const reuse = () => {
    const p = group.me?.preferences
    if (p) rememberPreferences({ ...p, nickname: group.me.nickname })
    navigate('/criar')
  }

  if (!winner) {
    return (
      <Section title="A reserva abre depois da escolha" subtitle="Primeiro o grupo vota e o organizador encerra a votação.">
        <Link to={`/g/${group.id}/votacao`} className="btn-primary">Ir para a votação</Link>
      </Section>
    )
  }

  const r = winner.restaurant
  return (
    <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
      <div className="flex flex-col gap-5">
        {res ? (
          <section className="card overflow-hidden">
            <div className="bg-brand p-5 text-white">
              <span className="inline-block rounded-full border-2 border-white px-3 py-1 text-xs font-extrabold uppercase tracking-widest">
                Reserva simulada
              </span>
              <h2 className="mt-3 text-2xl font-extrabold">{res.restaurant.name}</h2>
              <p className="mt-1 text-sm opacity-90">
                {dateLabel(res.booking_time.slice(0, 10))} · {res.booking_time.slice(11, 16)} · {res.party_size} pessoas
              </p>
            </div>
            <div className="p-5 text-sm">
              <p>Código: <span className="font-mono font-bold">{res.confirmation_code}</span></p>
              <p className="mt-2 text-muted">Reserva simulada: nenhum restaurante foi contatado.</p>
              {!res.restaurant.accepts_reservation && (
                <p className="mt-2 text-muted">Este restaurante não costuma aceitar reservas; registramos a ida do grupo.</p>
              )}
            </div>
          </section>
        ) : (
          <Section title={`Vencedor: ${r.name}`} subtitle={group.decision_note}>
            <p className="text-sm text-muted">{r.cuisine_label} · {r.neighborhood} · {brl(r.avg_price)} por pessoa</p>
            {group.is_organizer ? (
              <button className="btn-primary mt-4 w-full" onClick={reserve} disabled={busy}>
                {busy ? 'Confirmando...' : 'Confirmar reserva simulada'}
              </button>
            ) : (
              <p className="mt-4 rounded-xl bg-canvas p-3 text-sm">Aguardando quem organiza confirmar a reserva (simulada).</p>
            )}
            <ErrorBox error={error} />
          </Section>
        )}
        {res && <Review key={group.me?.participant_id} reservation={res} />}
      </div>

      <div className="flex flex-col gap-5">
        <Section title="Resumo do encontro">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted">Quando</dt><dd>{dateLabel(group.event_date)}, {group.event_time}</dd>
            <dt className="text-muted">Onde</dt><dd>{r.name} ({r.neighborhood})</dd>
            <dt className="text-muted">Preço médio</dt><dd>{brl(r.avg_price)} por pessoa</dd>
            <dt className="text-muted">Quem vai</dt><dd>{group.participants.map((p) => p.nickname).join(', ')}</dd>
            <dt className="text-muted">Decisão</dt><dd>{group.decision_note}</dd>
            {r.simulated_benefit && (<><dt className="text-muted">Benefício</dt><dd>{r.simulated_benefit.replace(' (simulado)', '')}</dd></>)}
          </dl>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {r.dietary_labels.map((d) => <Badge key={d} tone="green">{d}</Badge>)}
          </div>
          <p className="mt-3 text-xs text-muted">{group.dietary_disclaimer}</p>
        </Section>
        <Section title="Bora de novo?" subtitle="Leve suas preferências para o próximo encontro, sem preencher tudo outra vez.">
          <button className="btn-secondary w-full" onClick={reuse}>Novo encontro com minhas preferências</button>
        </Section>
      </div>
    </div>
  )
}

export default function Reservation() {
  return (
    <GroupShell poll={6000}>
      <Body />
    </GroupShell>
  )
}
