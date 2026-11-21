import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import { brl, dateLabel, localISO, nextSaturdayISO } from '../services/format'
import { useMeta } from '../services/hooks'
import { lastPreferences, saveIdentity } from '../services/session'
import { CopyButton, ErrorBox, Section } from '../components/ui'

export default function CreateGroup() {
  const meta = useMeta()
  const navigate = useNavigate()
  const reuse = lastPreferences()
  const [form, setForm] = useState({
    name: 'Jantar da turma',
    event_date: nextSaturdayISO(),
    event_time: '20:00',
    budget_per_person: 100,
    party_size: 4,
    neighborhood: reuse?.origin_neighborhood || 'Pinheiros',
    occasion: 'jantar_amigos',
    organizer_nickname: reuse?.nickname || '',
    vote_deadline: '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [created, setCreated] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const body = {
        ...form,
        budget_per_person: Number(form.budget_per_person),
        party_size: Number(form.party_size),
        occasion: form.occasion || null,
        vote_deadline: form.vote_deadline ? new Date(form.vote_deadline).toISOString() : null,
      }
      const out = await api.createGroup(body)
      saveIdentity(out.group.id, out.identity, { organizerToken: out.organizer_token })
      setCreated(out.group)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  if (created) {
    const link = `${window.location.origin}/entrar/${created.invite_code}`
    const msg = `Bora decidir onde comer? Entra no "${created.name}" pelo iFood Match e conta o que você prefere: ${link}`
    return (
      <div className="mx-auto flex max-w-xl flex-col gap-5">
        <Section title="Encontro criado!" subtitle="Mande o link no grupo. Cada pessoa entra com um apelido e diz o que prefere.">
          <div className="rounded-2xl bg-brand-soft p-4 text-center">
            <p className="text-xs font-bold uppercase tracking-wide text-brand-dark">Código de convite</p>
            <p className="mt-1 font-mono text-3xl font-extrabold tracking-[0.25em] text-brand">{created.invite_code}</p>
          </div>
          <label className="label mt-4" htmlFor="invite">Link de convite</label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input id="invite" className="input font-mono text-sm" readOnly value={link} onFocus={(e) => e.target.select()} />
            <CopyButton text={link} label="Copiar link" />
          </div>
          <a
            className="btn mt-3 w-full bg-[#25D366] text-white hover:brightness-95"
            href={`https://wa.me/?text=${encodeURIComponent(msg)}`}
            target="_blank"
            rel="noreferrer"
          >
            Compartilhar no WhatsApp
          </a>
          <p className="mt-4 text-sm text-muted">
            {dateLabel(created.event_date)} · {created.event_time} · {created.neighborhood} · até {brl(created.budget_per_person)} por pessoa
          </p>
        </Section>
        <button className="btn-primary" onClick={() => navigate(`/g/${created.id}/preferencias`)}>
          Preencher minhas preferências
        </button>
        <p className="text-center text-sm text-muted">
          Testando sozinho? Dentro do encontro, use <strong>Simular participante</strong> para entrar como outra pessoa.
        </p>
      </div>
    )
  }

  const today = localISO(new Date())
  return (
    <form onSubmit={submit} className="mx-auto flex max-w-xl flex-col gap-5">
      <div>
        <h1 className="text-2xl font-extrabold">Criar encontro</h1>
        <p className="mt-1 text-muted">Leva menos de um minuto. Você será quem organiza.</p>
      </div>
      <Section>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="label" htmlFor="name">Nome do encontro</label>
            <input id="name" className="input" value={form.name} onChange={set('name')} required minLength={2} maxLength={80} />
          </div>
          <div>
            <label className="label" htmlFor="nick">Seu apelido</label>
            <input id="nick" className="input" value={form.organizer_nickname} onChange={set('organizer_nickname')}
              required minLength={2} maxLength={30} placeholder="Ex.: Ana" autoComplete="off" />
          </div>
          <div>
            <label className="label" htmlFor="occasion">Ocasião</label>
            <select id="occasion" className="input" value={form.occasion} onChange={set('occasion')}>
              <option value="">Sem ocasião específica</option>
              {meta?.occasions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="date">Data</label>
            <input id="date" type="date" className="input" min={today} value={form.event_date} onChange={set('event_date')} required />
          </div>
          <div>
            <label className="label" htmlFor="time">Horário</label>
            <input id="time" type="time" className="input" value={form.event_time} onChange={set('event_time')} required />
          </div>
          <div>
            <label className="label" htmlFor="budget">Orçamento por pessoa (R$)</label>
            <input id="budget" type="number" className="input" min={20} max={1000} step={5} value={form.budget_per_person}
              onChange={set('budget_per_person')} required />
          </div>
          <div>
            <label className="label" htmlFor="size">Quantas pessoas</label>
            <input id="size" type="number" className="input" min={2} max={20} value={form.party_size} onChange={set('party_size')} required />
          </div>
          <div className="sm:col-span-2">
            <label className="label" htmlFor="hood">Região (bairro de referência)</label>
            <select id="hood" className="input" value={form.neighborhood} onChange={set('neighborhood')}>
              {(meta?.neighborhoods || [form.neighborhood]).map((n) => <option key={n}>{n}</option>)}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="label" htmlFor="deadline">Prazo da votação (opcional)</label>
            <input id="deadline" type="datetime-local" className="input" value={form.vote_deadline} onChange={set('vote_deadline')} />
            <p className="mt-1 text-xs text-muted">Se ninguém encerrar antes, a votação fecha sozinha nesse horário.</p>
          </div>
        </div>
      </Section>
      <ErrorBox error={error} />
      <button className="btn-primary text-base" disabled={busy}>{busy ? 'Criando...' : 'Criar e gerar convite'}</button>
      <Link to="/" className="text-center text-sm text-muted underline">Voltar</Link>
    </form>
  )
}
