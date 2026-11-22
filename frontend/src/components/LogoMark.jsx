/**
 * Símbolo do decide.ai: dois balões de conversa, e o da frente traz um check.
 * A conversa do grupo vira uma decisão. Desenho próprio em SVG.
 * Uso padrão: branco sobre o quadrado vermelho; `checkColor` é a cor do check dentro do balão.
 */
export default function LogoMark({ className = 'h-6 w-6', color = '#fff', checkColor = '#EA1D2C' }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <path d="M5 6.5h13a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3H10l-4 3.5V18.5H5a3 3 0 0 1-3-3v-6a3 3 0 0 1 3-3z"
        fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
      <path d="M14 12.5h13a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3h-1v3.5l-4-3.5h-8a3 3 0 0 1-3-3v-7a3 3 0 0 1 3-3z" fill={color} />
      <path d="M16.8 19l2.6 2.6 5.2-5.4" fill="none" stroke={checkColor} strokeWidth="2.4" strokeLinecap="round"
        strokeLinejoin="round" />
    </svg>
  )
}

/** Logo completa: símbolo no quadrado vermelho + a palavra "decide.ai". */
export function Wordmark({ size = 'md' }) {
  const box = size === 'lg' ? 'h-14 w-14 rounded-2xl' : 'h-9 w-9 rounded-xl'
  const icon = size === 'lg' ? 'h-9 w-9' : 'h-6 w-6'
  const text = size === 'lg' ? 'text-3xl' : 'text-lg'
  return (
    <span className="flex items-center gap-2">
      <span className={`flex items-center justify-center bg-brand ${box}`} aria-hidden>
        <LogoMark className={icon} />
      </span>
      <span className={`${text} font-extrabold leading-none tracking-tight text-ink`}>
        decide<span className="text-brand">.ai</span>
      </span>
    </span>
  )
}
