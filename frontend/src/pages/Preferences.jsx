import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import GroupShell, { useGroup } from '../components/GroupShell'
import { Badge, ChipGroup, ErrorBox, Section } from '../components/ui'
import { api } from '../services/api'
import { brl } from '../services/format'
import { useMeta } from '../services/hooks'
import { activeIdentity, lastPreferences, rememberPreferences } from '../services/session'

const EMPTY = { cuisines: [], dietary_restrictions: [], ambiences: [], origin_neighborhood: '', max_distance_km: 10,
  max_budget: '', additional_preferences: '', free_text: '' }

function fromSaved(p) {
  return { ...EMPTY, ...p, max_budget: p.max_budget ?? '', additional_preferences: p.additional_preferences || '',
    free_text: p.free_text || '' }
}

function PreferencesForm() {
  const { group, reload } = useGroup()
  const meta = useMeta()
  const me = group.me
  const reused = !me?.preferences && lastPreferences()
  const [form, setForm] = useState(() =>
    me?.preferences ? fromSaved(me.preferences)
      : reused ? { ...fromSaved(reused), free_text: '' }
        : { ...EMPTY, origin_neighborhood: group.neighborhood })
  const [parsedBy, setParsedBy] = useState(me?.preferences?.parsed_by || null)
  const [aiNote, setAiNote] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(null)

  // Trocar de participante na mesma aba recarrega o formulário da pessoa ativa.
  const pid = me?.participant_id
  useEffect(() => {
    setForm(me?.preferences ? fromSaved(me.preferences) : { ...EMPTY, origin_neighborhood: group.neighborhood })
    setParsedBy(me?.preferences?.parsed_by || null)
    setAiNote(null)
    setSaved(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid])

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }))
  const locked = !group.accepting_changes

  const interpret = async () => {
    setBusy('ia')
    setError(null)
    try {
      const out = await api.parsePreferences(group.id, form.free_text)
      const p = out.preferences
      setForm((f) => ({
        ...f,
        cuisines: p.cuisines.length ? p.cuisines : f.cuisines,
        dietary_restrictions: p.dietary_restrictions.length ? p.dietary_restrictions : f.dietary_restrictions,
        ambiences: p.ambiences.length ? p.ambiences : f.ambiences,
        origin_neighborhood: p.origin_neighborhood || f.origin_neighborhood,
        max_distance_km: p.max_distance_km || f.max_distance_km,
        max_budget: p.max_budget ?? f.max_budget,
        additional_preferences: [p.budget_hint, p.additional_preferences].filter(Boolean).join(' ').slice(0, 300),
      }))
      setParsedBy(out.source)
      setAiNote(out)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }

  const save = async (e) => {
    e.preventDefault()
    if (group.status === 'votacao_aberta' &&
      !window.confirm('O Match já foi gerado. Mudar suas preferências apaga o ranking e os votos atuais e abre uma nova rodada. Continuar?')) return
    setBusy('save')
    setError(null)
    try {
      const body = { ...form, max_budget: form.max_budget === '' ? null : Number(form.max_budget),
        max_distance_km: Number(form.max_distance_km), parsed_by: parsedBy,
        additional_preferences: form.additional_preferences || null, free_text: form.free_text || null }
      const out = await api.savePreferences(group.id, me.participant_id, body)
      rememberPreferences({ ...body, nickname: me.nickname })
      setSaved(out)
      await reload()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(null)
    }
  }

  if (!meta) return null
  return (
    <form onSubmit={save} className="flex flex-col gap-5">
      {reused && !me?.preferences && (
        <div className="rounded-xl bg-brand-soft p-3 text-sm text-brand-dark">
          Preenchemos com as preferências que você usou no último encontro. Confira e salve.
        </div>
      )}
      <Section
        title={`Preferências de ${me.nickname}`}
        subtitle="Escreva do seu jeito e deixe a IA preencher, ou marque direto nos campos abaixo."
        right={me.preferences ? <Badge tone="green">Salvas</Badge> : <Badge tone="amber">Pendente</Badge>}
      >
        <label className="label" htmlFor="free">Conte o que você quer (opcional)</label>
        <textarea id="free" className="input min-h-24" maxLength={500} disabled={locked}
          placeholder='Ex.: "quero um lugar tranquilo, não muito caro, sou vegetariana e saio de Pinheiros"'
          value={form.free_text} onChange={(e) => set('free_text')(e.target.value)} />
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <button type="button" className="btn-secondary py-2" onClick={interpret}
            disabled={locked || busy || form.free_text.trim().length < 3}>
            {busy === 'ia' ? 'Interpretando...' : 'Preencher com IA'}
          </button>
          {aiNote && (
            <span className="text-sm text-muted">
              {aiNote.message}
            </span>
          )}
        </div>
      </Section>

      <Section title="Confira e ajuste" subtitle="Estes campos são o que vale para o Match.">
        <div className="flex flex-col gap-5">
          <div>
            <p className="label">Culinárias que você curte</p>
            <ChipGroup options={meta.cuisines} value={form.cuisines} onChange={set('cuisines')} />
          </div>
          <div>
            <p className="label">Restrições alimentares</p>
            <ChipGroup options={meta.dietary_options} value={form.dietary_restrictions} onChange={set('dietary_restrictions')} />
            <p className="mt-1.5 text-xs text-muted">São obrigatórias: só aparecem restaurantes que oferecem essas opções no cadastro.</p>
          </div>
          <div>
            <p className="label">Ambiente</p>
            <ChipGroup options={meta.ambiences} value={form.ambiences} onChange={set('ambiences')} />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="label" htmlFor="origin">Bairro de saída</label>
              <select id="origin" className="input" value={form.origin_neighborhood} required disabled={locked}
                onChange={(e) => set('origin_neighborhood')(e.target.value)}>
                <option value="" disabled>Escolha</option>
                {meta.neighborhoods.map((n) => <option key={n}>{n}</option>)}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="dist">Distância máxima: {form.max_distance_km} km</label>
              <input id="dist" type="range" min={1} max={30} className="mt-3 w-full accent-brand" disabled={locked}
                value={form.max_distance_km} onChange={(e) => set('max_distance_km')(Number(e.target.value))} />
            </div>
            <div>
              <label className="label" htmlFor="mybudget">Meu limite (opcional)</label>
              <input id="mybudget" type="number" min={20} max={1000} step={5} className="input" disabled={locked}
                placeholder={`Grupo: ${brl(group.budget_per_person)}`} value={form.max_budget}
                onChange={(e) => set('max_budget')(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="label" htmlFor="extra">Observações</label>
            <input id="extra" className="input" maxLength={300} disabled={locked} value={form.additional_preferences}
              onChange={(e) => set('additional_preferences')(e.target.value)} placeholder="Ex.: prefiro sem música alta" />
            <p className="mt-1 text-xs text-muted">Só para o grupo ver; não entra no cálculo.</p>
          </div>
        </div>
      </Section>

      <ErrorBox error={error} />
      {saved?.round_invalidated && (
        <div className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
          Suas preferências mudaram depois do Match: o ranking e os votos anteriores foram invalidados. Gere o Match de novo.
        </div>
      )}
      {locked ? (
        <p className="text-sm text-muted">A escolha já foi concluída; as preferências estão travadas.</p>
      ) : (
        <button className="btn-primary text-base" disabled={busy}>
          {busy === 'save' ? 'Salvando...' : me.preferences ? 'Atualizar preferências' : 'Salvar preferências'}
        </button>
      )}
    </form>
  )
}

function GroupPanel() {
  const { group, reload } = useGroup()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const c = group.counts

  const run = async (force) => {
    setBusy(true)
    setError(null)
    try {
      await api.match(group.id, force)
      await reload()
      navigate(`/g/${group.id}/match`)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section title="Quem já respondeu" subtitle={`${c.answered} de ${Math.max(c.party_size, c.joined)} com preferências · ${c.joined} de ${c.party_size} entraram`}>
      <ul className="flex flex-col divide-y divide-line">
        {group.participants.map((p) => (
          <li key={p.id} className="flex items-center justify-between py-2.5">
            <span className="flex items-center gap-2 font-medium">
              {p.nickname}
              {p.is_organizer && <Badge>organiza</Badge>}
            </span>
            {p.has_preferences ? <Badge tone="green">✓ respondeu</Badge> : <Badge tone="amber">aguardando</Badge>}
          </li>
        ))}
        {Array.from({ length: Math.max(0, c.party_size - c.joined) }).map((_, i) => (
          <li key={`v${i}`} className="py-2.5 text-sm text-muted">Vaga ainda não ocupada</li>
        ))}
      </ul>

      <div className="mt-4 flex flex-col gap-2">
        {group.status === 'votacao_aberta' && (
          <Link to={`/g/${group.id}/match`} className="btn-primary">Ver o Match da rodada {group.current_round}</Link>
        )}
        {group.can_generate_match && (
          <button className="btn-primary" onClick={() => run(false)} disabled={busy}>
            {busy ? 'Calculando o Match...' : 'Gerar Match'}
          </button>
        )}
        {!group.can_generate_match && group.status === 'coletando_preferencias' && (
          <>
            <p className="rounded-xl bg-canvas p-3 text-sm text-muted">
              O Match fica disponível quando todos responderem.
              {group.missing.length > 0 && <> Faltam: <strong>{group.missing.join(', ')}</strong>.</>}
              {c.joined < c.party_size && <> Ainda faltam {c.party_size - c.joined} pessoa(s) entrar.</>}
            </p>
            {group.can_force_match && (group.is_organizer ? (
              <button className="btn-secondary" onClick={() => run(true)} disabled={busy}>
                Gerar com quem já respondeu ({c.answered})
              </button>
            ) : (
              <p className="text-xs text-muted">Quem organiza pode gerar o Match com quem já respondeu.</p>
            ))}
          </>
        )}
        {group.match_summary && group.match_summary.eligible_count === 0 && group.status !== 'votacao_aberta' && (
          <Link to={`/g/${group.id}/match`} className="btn-secondary">Ver por que nenhum restaurante passou</Link>
        )}
      </div>
      <ErrorBox error={error} />
    </Section>
  )
}

export default function Preferences() {
  return (
    <GroupShell>
      <Body />
    </GroupShell>
  )
}

function Body() {
  const { group } = useGroup()
  const me = group.me || activeIdentity(group.id)
  return (
    <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
      {group.me ? <PreferencesForm /> : <ErrorBox error={{ message: `Sessão de ${me?.nickname || 'participante'} não encontrada.` }} />}
      <div className="lg:sticky lg:top-24 lg:self-start">
        <GroupPanel />
      </div>
    </div>
  )
}
