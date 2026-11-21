import { useEffect, useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useParams } from 'react-router-dom'
import Layout from './components/Layout'
import { ErrorBox, Spinner } from './components/ui'
import CreateGroup from './pages/CreateGroup'
import Demo from './pages/Demo'
import Home from './pages/Home'
import Join from './pages/Join'
import MatchResults from './pages/MatchResults'
import Metrics from './pages/Metrics'
import Preferences from './pages/Preferences'
import Reservation from './pages/Reservation'
import Voting from './pages/Voting'
import { api } from './services/api'
import { screenFor } from './services/format'
import { getGroupSession } from './services/session'

/** /g/:id leva para a tela certa conforme a etapa do encontro. */
function GroupHome() {
  const { id } = useParams()
  const [target, setTarget] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    if (!getGroupSession(id).identities.length) return setTarget('preferencias')
    api.group(id).then((g) => setTarget(screenFor(g.status))).catch(setError)
  }, [id])
  if (error) return <ErrorBox error={error} />
  if (!target) return <Spinner />
  return <Navigate to={`/g/${id}/${target}`} replace />
}

function NotFound() {
  return (
    <div className="card mx-auto max-w-md p-6 text-center">
      <h1 className="text-xl font-bold">Página não encontrada</h1>
      <Link to="/" className="btn-primary mt-4">Ir para o início</Link>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/criar" element={<CreateGroup />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/entrar/:code" element={<Join />} />
          <Route path="/g/:id" element={<GroupHome />} />
          <Route path="/g/:id/preferencias" element={<Preferences />} />
          <Route path="/g/:id/match" element={<MatchResults />} />
          <Route path="/g/:id/votacao" element={<Voting />} />
          <Route path="/g/:id/reserva" element={<Reservation />} />
          <Route path="/metricas" element={<Metrics />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
