import LogoMark from './LogoMark'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { WakeBanner } from './ui'

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2 font-extrabold tracking-tight text-ink" aria-label="Decide.ai, início">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand" aria-hidden>
        <LogoMark className="h-6 w-6" />
      </span>
      <span className="text-lg leading-none">
        Decide<span className="text-brand">.ai</span>
      </span>
    </Link>
  )
}

export default function Layout({ children }) {
  const { pathname } = useLocation()
  const isHome = pathname === '/'
  return (
    <div className="flex min-h-screen flex-col">
      <WakeBanner />
      <header className="sticky top-0 z-40 border-b border-line bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4">
          <Logo />
          {!isHome && (
            <nav className="flex items-center gap-1 text-sm font-semibold">
              <NavLink to="/criar" className="btn-primary px-4 py-2 text-sm">Criar encontro</NavLink>
            </nav>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:py-10">{children}</main>
      <footer className="border-t border-line bg-white">
        <div className="mx-auto max-w-5xl px-4 py-6 text-xs leading-relaxed text-muted">
          <p>
            Protótipo criado para o case AI Builder, proposta para o Comer Fora. Dados fictícios, sem vínculo oficial
            com o iFood.
          </p>
        </div>
      </footer>
    </div>
  )
}
