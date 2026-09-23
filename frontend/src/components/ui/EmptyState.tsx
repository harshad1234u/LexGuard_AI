import type { ReactNode } from 'react'

import { Icon, type IconName } from './Icon'

/** A quiet placeholder for a view with nothing to show yet, and why. */
export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: IconName
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
      <span className="flex size-11 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
        <Icon name={icon} className="size-5" />
      </span>
      <p className="mt-4 font-display text-base font-semibold text-slate-900">{title}</p>
      {children && <div className="mt-1.5 max-w-md text-sm text-slate-600">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}
