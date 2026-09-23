import { BRAND } from '../../config/brand'
import { Icon } from '../ui/Icon'

/** Legal-information notice (PRD sec. 12). Shown on every screen. */
export function Disclaimer() {
  return (
    <p className="flex items-start gap-2.5 text-xs leading-relaxed text-slate-600">
      <Icon name="shield" className="mt-px size-4 text-slate-500" />
      <span>
        <strong className="font-semibold text-slate-800">Legal disclaimer:</strong>{' '}
        {BRAND.name} provides legal information and document-understanding assistance for
        informational purposes only. It is not a substitute for advice from a qualified legal
        professional, does not create an attorney-client relationship, and does not guarantee
        legal correctness or outcomes.
      </span>
    </p>
  )
}
