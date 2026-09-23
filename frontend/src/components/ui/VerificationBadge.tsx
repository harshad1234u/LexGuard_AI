import type { ReactNode } from 'react'

import { TONE_CLASSES, verdictFor, type Tone } from '../../lib/verdicts'
import type { VerificationStatus } from '../../types/api'
import { Icon, type IconName } from './Icon'

/** A compact status chip: icon plus text, never colour alone. */
export function Badge({
  tone,
  icon,
  children,
}: {
  tone: Tone
  icon?: IconName
  children: ReactNode
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-semibold ${TONE_CLASSES[tone]}`}
    >
      {icon && <Icon name={icon} className="size-3.5" />}
      {children}
    </span>
  )
}

/**
 * The backend's verification verdict, as a badge.
 *
 * Takes the status the backend sent, never a boolean the caller computed, so a
 * component cannot show "verified" for something the verifier did not verify.
 */
export function VerificationBadge({
  status,
  size = 'full',
}: {
  status: VerificationStatus
  size?: 'full' | 'short'
}) {
  const verdict = verdictFor(status)
  return (
    <Badge tone={verdict.tone} icon={verdict.icon}>
      {size === 'full' ? verdict.label : verdict.short}
    </Badge>
  )
}
