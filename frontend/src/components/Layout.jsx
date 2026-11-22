import { Link, NavLink, useLocation } from 'react-router-dom'
import { Wordmark } from './LogoMark'
import { WakeBanner } from './ui'

function Logo() {
  return (
    <Link to="/" aria-label="decide.ai, início">
      <Wordmark />
    </Link>
  )
}

export default function Layout({ children }) {
  const { pathname } = useLocation()
  const isHome = pathname === '/'
  return (
    <div className="flex min-h-screen flex-col">
      <WakeBanner />
      {/* Na página inicial a logo já aparece grande no centro; o cabeçalho só existe nas outras telas. */}
      {!isHome && (
        <header className="sticky top-0 z-40 border-b border-line bg-white/90 backdrop-blur">
          <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4">
            <Logo />
            <nav className="flex items-center gap-1 text-sm font-semibold">
              <NavLink to="/criar" className="btn-primary px-4 py-2 text-sm">Criar encontro</NavLink>
            </nav>
          </div>
        </header>
      )}
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
