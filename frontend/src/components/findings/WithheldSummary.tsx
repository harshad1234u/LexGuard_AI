import { WITHHELD } from '../../lib/verdicts'
import type { AnalysisResult } from '../../types/api'
import { Badge } from '../ui/VerificationBadge'

/**
 * What the output gate held back, counted by reason.
 *
 * Counts only. The backend never returns a withheld statement's text, and a
 * placeholder that paraphrased one would be exactly the unverified claim the
 * gate exists to stop.
 */
export function WithheldSummary({ result }: { result: AnalysisResult }) {
  const { withheld } = result
  if (withheld.total === 0) return null

  const reasons = [
    [withheld.rejected, 'contradicted by the document'],
    [withheld.unverified, 'not found in the document'],
    [withheld.partially_verified, 'only partly confirmed'],
  ] as const

  return (
    <section
      aria-label="Withheld statements"
      className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-slate-900">
          {withheld.total} {withheld.total === 1 ? 'statement was' : 'statements were'} withheld
        </p>
        <Badge tone={WITHHELD.tone} icon={WITHHELD.icon}>
          {WITHHELD.label}
        </Badge>
      </div>
      <ul className="mt-2 space-y-0.5 font-mono text-xs text-slate-600">
        {reasons
          .filter(([count]) => count > 0)
          .map(([count, reason]) => (
            <li key={reason}>
              {count} {reason}
            </li>
          ))}
      </ul>
      <p className="mt-3 text-xs leading-relaxed text-slate-600">
        Their text is not shown. A statement the document does not support is not something this
        tool will repeat back to you.
      </p>
    </section>
  )
}
