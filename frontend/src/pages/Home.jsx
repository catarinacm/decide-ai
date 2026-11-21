import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import { recentGroups } from '../services/session'
import { ErrorBox } from '../components/ui'

const STEPS = [
  { n: 1, title: 'Crie o encontro', text: 'Data, horário, orçamento por pessoa e região. Você recebe um link para mandar no grupo.' },
  { n: 2, title: 'Cada um diz o que prefere', text: 'Culinárias, restrições, ambiente e de onde sai. Pode escrever do seu jeito que a IA organiza.' },
  { n: 3, title: 'Match, voto e reserva', text: 'O algoritmo filtra e pontua, a IA explica o porquê, o grupo vota e a reserva (simulada) sai.' },
]

export default function Home() {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [recent] = useState(() => recentGroups().slice(0, 3))

  // Acorda a API em segundo plano assim que alguém abre a página inicial.
  useEffect(() => {
    api.health().catch(() => {})
  }, [])

  const demo = () => navigate('/demo')

  return (
    <div className="flex flex-col gap-10">
      <section className="grid items-center gap-8 md:grid-cols-[1.1fr_0.9fr]">
        <div>
          <span className="inline-block rounded-full bg-brand-soft px-3 py-1 text-xs font-bold uppercase tracking-wide text-brand-dark">
            Comer fora em grupo
          </span>
          <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
            Onde todo mundo <span className="text-brand">combina</span>.
          </h1>
          <p className="mt-4 text-lg text-muted">
            Cinco amigos, cinco orçamentos, uma vegetariana e alguém que mora longe. O iFood Match transforma essa
            conversa sem fim em uma decisão: só aparecem lugares que cabem no bolso e nas restrições de todos, com o
            motivo de cada sugestão.
          </p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <Link to="/criar" className="btn-primary text-base">Criar encontro</Link>
            <button type="button" className="btn-secondary text-base" onClick={demo} disabled={busy}>
              Ver demonstração
            </button>
          </div>
          <p className="mt-3 text-xs text-muted">
            A demonstração cria um grupo com 4 amigos fictícios já preenchidos, para você ir até a reserva em 2 minutos.
          </p>
          <ErrorBox error={error} />
        </div>
        <div className="card relative overflow-hidden p-6" aria-hidden>
          <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-brand-soft" />
          <p className="relative text-sm font-semibold text-muted">Match do grupo</p>
          {[
            ['Panela de Barro Fumê', 'Brasileira · R$ 45', 63],
            ['Fogão de Lenha Serra Fina', 'Brasileira · R$ 58', 61],
            ['Forno Quintal Nove', 'Pizzaria · R$ 58', 57],
          ].map(([name, sub, s], i) => (
            <div key={name} className="relative mt-3 flex items-center gap-3 rounded-xl border border-line bg-white p-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand text-sm font-bold text-white">{i + 1}</span>
              <div className="flex-1">
                <p className="font-semibold">{name}</p>
                <p className="text-xs text-muted">{sub}</p>
              </div>
              <span className="text-sm font-bold text-brand">{s}</span>
            </div>
          ))}
          <p className="relative mt-4 text-xs text-muted">Exemplo com dados fictícios.</p>
        </div>
      </section>

      <section>
        <h2 className="text-xl font-bold">Como funciona</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.n} className="card p-5">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand text-white font-bold">{s.n}</span>
              <h3 className="mt-3 font-bold">{s.title}</h3>
              <p className="mt-1 text-sm text-muted">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="card grid gap-4 p-6 sm:grid-cols-3">
        <div>
          <h3 className="font-bold">O algoritmo decide</h3>
          <p className="mt-1 text-sm text-muted">Orçamento, restrições, capacidade e horário são filtros obrigatórios, antes de qualquer ranking.</p>
        </div>
        <div>
          <h3 className="font-bold">A IA explica</h3>
          <p className="mt-1 text-sm text-muted">Ela só comenta os restaurantes já escolhidos, citando dados cadastrados e o principal ponto de atenção.</p>
        </div>
        <div>
          <h3 className="font-bold">Justo com todos</h3>
          <p className="mt-1 text-sm text-muted">O score é calculado para cada pessoa, e um lugar que agrada a maioria mas exclui alguém perde pontos.</p>
        </div>
      </section>

      {recent.length > 0 && (
        <section>
          <h2 className="text-lg font-bold">Seus encontros neste aparelho</h2>
          <div className="mt-3 flex flex-col gap-2">
            {recent.map((g) => (
              <Link key={g.id} to={`/g/${g.id}`} className="card flex items-center justify-between p-4 hover:border-brand">
                <span className="font-semibold">
                  {g.identities.map((i) => i.nickname).join(', ')}
                </span>
                <span className="text-sm text-brand">Abrir</span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
