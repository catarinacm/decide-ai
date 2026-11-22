import { useEffect, useState } from 'react'
import { onWaking } from '../services/api'

export function Spinner({ label = 'Carregando...' }) {
  return (
    <div className="flex items-center justify-center gap-3 py-10 text-muted" role="status">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-brand border-t-transparent" />
      {label}
    </div>
  )
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
      <p className="font-semibold">{error.message || String(error)}</p>
      {Array.isArray(error.details) && error.details.length > 0 && (
        <ul className="mt-2 list-disc pl-5">
          {error.details.map((d, i) => (
            <li key={i}>{d.field ? `${d.field}: ` : ''}{d.message}</li>
          ))}
        </ul>
      )}
      {onRetry && (
        <button className="mt-3 font-semibold underline" onClick={onRetry}>Tentar de novo</button>
      )}
    </div>
  )
}

export function Chip({ selected, onClick, children, disabled }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      aria-pressed={selected}
      className={`chip ${selected ? 'border-brand bg-brand text-white' : 'border-line bg-white text-ink hover:border-brand'}`}
    >
      {selected && <span aria-hidden>✓</span>}
      {children}
    </button>
  )
}

export function ChipGroup({ options, value, onChange, single = false }) {
  const toggle = (v) => {
    if (single) return onChange(value === v ? null : v)
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v])
  }
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <Chip key={o.value} selected={single ? value === o.value : value.includes(o.value)} onClick={() => toggle(o.value)}>
          {o.label}
        </Chip>
      ))}
    </div>
  )
}

export function Badge({ children, tone = 'neutral' }) {
  const tones = {
    neutral: 'bg-canvas text-ink',
    brand: 'bg-brand-soft text-brand-dark',
    green: 'bg-green-50 text-green-800',
    amber: 'bg-amber-50 text-amber-800',
    dark: 'bg-ink text-white',
  }
  return <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}>{children}</span>
}

export function ScoreRing({ score, size = 56 }) {
  const r = 22
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, score)) / 100
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} aria-label={`Compatibilidade ${Math.round(score)} de 100`}>
      <svg viewBox="0 0 52 52" className="h-full w-full -rotate-90">
        <circle cx="26" cy="26" r={r} fill="none" stroke="#F1F1F1" strokeWidth="6" />
        <circle cx="26" cy="26" r={r} fill="none" stroke="#EA1D2C" strokeWidth="6" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - pct)} />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-bold">{Math.round(score)}</span>
    </div>
  )
}

export function CopyButton({ text, label = 'Copiar' }) {
  const [done, setDone] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const el = document.createElement('textarea')
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      el.remove()
    }
    setDone(true)
    setTimeout(() => setDone(false), 1800)
  }
  return (
    <button type="button" className="btn-secondary py-2" onClick={copy}>
      {done ? 'Copiado!' : label}
    </button>
  )
}

/** Aviso amigável enquanto o servidor gratuito acorda (o primeiro acesso pode levar cerca de 1 minuto). */
export function WakeBanner() {
  const [waking, setWaking] = useState(false)
  useEffect(() => onWaking(setWaking), [])
  if (!waking) return null
  return (
    <div className="fixed inset-x-0 top-0 z-50 flex justify-center p-3" role="status" aria-live="polite">
      <div className="flex max-w-md items-center gap-3 rounded-2xl bg-ink px-4 py-3 text-sm text-white shadow-lg">
        <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-white border-t-transparent" />
        <span>
          <strong>Acordando o servidor...</strong> O primeiro acesso pode levar até 1 minuto; depois fica rápido.
        </span>
      </div>
    </div>
  )
}

export function Section({ title, subtitle, children, right }) {
  return (
    <section className="card p-5 sm:p-6">
      {(title || right) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-lg font-bold">{title}</h2>}
            {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}
