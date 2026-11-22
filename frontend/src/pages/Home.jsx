import { Wordmark } from '../components/LogoMark'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import { recentGroups } from '../services/session'

export default function Home() {
  const [last] = useState(() => recentGroups()[0] || null)

  // Acorda a API em segundo plano assim que alguém abre a página inicial.
  useEffect(() => {
    api.health().catch(() => {})
  }, [])

  return (
    <section className="flex min-h-[calc(100vh-14rem)] flex-col items-center justify-center text-center">
      <Wordmark size="lg" />
      <h1 className="mt-8 max-w-xl text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
        Onde todo mundo <span className="text-brand">combina</span>.
      </h1>
      <p className="mt-4 max-w-md text-lg text-muted">
        Cada um diz o que quer e quanto pode gastar. A gente encontra o lugar que agrada o grupo todo.
      </p>
      <Link to="/criar" className="btn-primary mt-10 w-full max-w-xs py-4 text-lg">
        Criar encontro
      </Link>
      <div className="mt-6 flex flex-col items-center gap-2 text-sm">
        {last && (
          <Link to={`/g/${last.id}`} className="font-semibold text-ink hover:text-brand">
            Voltar ao meu último encontro
          </Link>
        )}
        <Link to="/demo" className="text-muted underline-offset-4 hover:text-brand hover:underline">
          ou veja um exemplo pronto
        </Link>
      </div>
    </section>
  )
}
