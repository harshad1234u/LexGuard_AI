import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger-ghost'

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-navy-900 text-white hover:bg-slate-800 active:bg-slate-950 disabled:bg-slate-400 disabled:text-white',
  secondary:
    'border border-slate-200 bg-white text-slate-800 hover:border-slate-300 hover:bg-slate-50 disabled:text-slate-400',
  ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:text-slate-400',
  'danger-ghost': 'text-slate-600 hover:bg-rose-50 hover:text-rose-700 disabled:text-slate-400',
}

/** The one button style, so actions look the same on every screen. */
export function Button({
  variant = 'primary',
  className = '',
  type = 'button',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type={type}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  )
}
