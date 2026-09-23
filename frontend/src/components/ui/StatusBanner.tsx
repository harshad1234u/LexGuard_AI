import type { ReactNode } from 'react'

import { TONE_CLASSES, type Tone } from '../../lib/verdicts'
import { Icon, type IconName } from './Icon'

const ICONS: Partial<Record<Tone, IconName>> = {
  verified: 'checkCircle',
  partial: 'alertTriangle',
  rejected: 'xCircle',
  danger: 'alertTriangle',
  info: 'info',
  neutral: 'info',
  withheld: 'ban',
}

interface Props {
  tone: Tone
  title?: ReactNode
  children?: ReactNode
  /**
   * `alert` only for a failure the user must hear about now. Most banners are
   * explanations and are announced, if at all, by the live region around them.
   */
  role?: 'alert' | 'status'
  icon?: IconName | null
  className?: string
}

/** A bordered, tinted message block with an icon and visible text. */
export function StatusBanner({ tone, title, children, role, icon, className = '' }: Props) {
  const glyph = icon === null ? null : (icon ?? ICONS[tone])
  return (
    <div role={role} className={`flex gap-3 rounded-lg border px-4 py-3 text-sm ${TONE_CLASSES[tone]} ${className}`}>
      {glyph && <Icon name={glyph} className="mt-0.5 size-4" />}
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={title ? 'mt-1' : ''}>{children}</div>}
      </div>
    </div>
  )
}

/**
 * A failure that belongs to one feature, headed by what failed.
 *
 * The heading matters: a Q&A outage once read as an analysis outage because
 * the message did not say which of the two things on screen it spoke for.
 */
export function ErrorState({
  title,
  children,
  className = '',
}: {
  title: string
  children: ReactNode
  className?: string
}) {
  return (
    <StatusBanner tone="danger" role="alert" className={className} title={title}>
      {children}
    </StatusBanner>
  )
}
