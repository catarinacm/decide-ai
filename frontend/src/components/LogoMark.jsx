/** Símbolo do Decide.ai: uma pessoa pensando (cabeça e ombros com balões de pensamento). Desenho próprio. */
export default function LogoMark({ className = 'h-6 w-6', color = '#fff' }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true" fill={color}>
      {/* cabeça e ombros */}
      <circle cx="11.5" cy="17" r="4.6" />
      <path d="M3.5 29c0-4.6 3.6-7.6 8-7.6s8 3 8 7.6z" />
      {/* balões de pensamento */}
      <circle cx="18.6" cy="12.4" r="1.2" />
      <circle cx="21.4" cy="9.4" r="1.6" />
      {/* nuvem */}
      <circle cx="23.6" cy="5.6" r="2.4" />
      <circle cx="26.8" cy="5" r="2.6" />
      <circle cx="28.6" cy="7.2" r="1.8" />
      <rect x="23.6" y="5.6" width="5" height="3.4" rx="1.7" />
    </svg>
  )
}
