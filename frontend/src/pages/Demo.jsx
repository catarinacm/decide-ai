import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import { saveIdentity } from '../services/session'
import { ErrorBox, Spinner } from '../components/ui'

/** Cria um grupo de demonstração novo (Ana, Bruno, Carla e Davi) e entra nele como organizadora. */
export default function Demo() {
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    api.demo()
      .then((out) => {
        const gid = out.group.id
        // Guarda as quatro identidades: dá para trocar de pessoa na mesma aba e votar como cada uma.
        out.identities.slice(1).forEach((i) => saveIdentity(gid, { ...i, is_simulated: true }, { makeActive: false }))
        saveIdentity(gid, { ...out.identities[0], is_simulated: true }, { organizerToken: out.organizer_token })
        navigate(`/g/${gid}/preferencias`, { replace: true })
      })
      .catch(setError)
  }, [navigate])

  return (
    <div className="mx-auto max-w-md">
      {error ? (
        <div className="flex flex-col gap-4">
          <ErrorBox error={error} />
          <Link to="/" className="btn-secondary">Voltar</Link>
        </div>
      ) : (
        <Spinner label="Montando o grupo de demonstração..." />
      )}
    </div>
  )
}
