import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../services/api'
import { brl, dateLabel } from '../services/format'
import { usePolled } from '../services/hooks'
import { getGroupSession, lastPreferences, saveIdentity } from '../services/session'
import { ErrorBox, Section, Spinner } from '../components/ui'

export default function Join() {
  const { code } = useParams()
  const navigate = useNavigate()
  const { data: preview, error: loadError, loading } = usePolled(() => api.preview(code), [code])
  const [nickname, setNickname] = useState(lastPreferences()?.nickname || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  if (loading) return <Spinner />
  if (loadError) return <div className="mx-auto max-w-md"><ErrorBox error={loadError} /></div>

  const already = getGroupSession(preview.group_id).identities.length > 0

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const out = await api.join({ invite_code: code, nickname })
      saveIdentity(out.group_id, out.identity)
      navigate(`/g/${out.group_id}/preferencias`)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex max-w-md flex-col gap-5">
      <Section>
        <p className="text-xs font-bold uppercase tracking-wide text-brand">Você foi convidado</p>
        <h1 className="mt-1 text-2xl font-extrabold">{preview.name}</h1>
        <p className="mt-2 text-sm text-muted">
          {dateLabel(preview.event_date)} · {preview.event_time} · {preview.neighborhood}
        </p>
        <p className="text-sm text-muted">Até {brl(preview.budget_per_person)} por pessoa · {preview.joined} de {preview.party_size} já entraram</p>
      </Section>

      {already && (
        <button className="btn-secondary" onClick={() => navigate(`/g/${preview.group_id}`)}>
          Você já está neste encontro: abrir
        </button>
      )}

      {preview.accepting_participants ? (
        <form onSubmit={submit} className="card flex flex-col gap-3 p-5">
          <label className="label" htmlFor="nick">Como o grupo te chama?</label>
          <input id="nick" className="input" value={nickname} onChange={(e) => setNickname(e.target.value)}
            required minLength={2} maxLength={30} placeholder="Só um apelido, sem nome completo" autoComplete="off" />
          <p className="text-xs text-muted">Não pedimos e-mail, telefone nem nome completo.</p>
          <ErrorBox error={error} />
          <button className="btn-primary" disabled={busy}>{busy ? 'Entrando...' : 'Entrar no encontro'}</button>
        </form>
      ) : (
        <ErrorBox error={{ message: 'Este encontro já fechou a escolha e não aceita novas pessoas.' }} />
      )}
    </div>
  )
}
