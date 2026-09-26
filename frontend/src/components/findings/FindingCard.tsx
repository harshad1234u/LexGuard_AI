import { humanise, pageRef } from '../../lib/format'
import type { VerifiedFindingOut } from '../../types/api'
import { Icon } from '../ui/Icon'
import { TranslationLabel } from '../ui/LanguageSelect'
import { VerificationBadge } from '../ui/VerificationBadge'

/**
 * The model's plain-language reading of a finding, labelled for what it is.
 *
 * The claim was verified against the document. The explanation usually was
 * not - it is the model's interpretation, and the backend measured that it
 * cannot reliably tell a faithful paraphrase from a reversed one
 * (PHASE_15_REPORT.md sec. 11). So it is set apart and labelled, never shown
 * as part of the verified finding.
 */
export function Explanation({ finding }: { finding: VerifiedFindingOut }) {
  if (!finding.explanation) return null

  return finding.explanation_verified ? (
    <div>
      <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
        Plain-language explanation
      </p>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">{finding.explanation}</p>
      {/* Only ever beside a verified explanation, and always labelled: the
          backend checks its figures, not its meaning. */}
      {finding.explanation_translation && (
        <div className="mt-3 border-l-2 border-amber-300 pl-3" lang="ta">
          <TranslationLabel />
          <p className="mt-1 text-sm leading-relaxed text-slate-700">
            {finding.explanation_translation}
          </p>
        </div>
      )}
    </div>
  ) : (
    <div className="border-l-2 border-amber-300 pl-3">
      <p className="text-xs font-semibold tracking-wide text-amber-900 uppercase">
        Interpretation &mdash; not verified against the document
      </p>
      <p className="mt-1 text-sm leading-relaxed text-slate-700">{finding.explanation}</p>
    </div>
  )
}

/**
 * One released finding, with the evidence it rests on.
 *
 * Grounding information is never hidden or collapsed: the claim, the quote,
 * the page and the verdict sit together on the card, because the claim is
 * only worth as much as the evidence under it. The inspector beside it adds
 * explanation of the verdict; it does not hold anything the card leaves out.
 */
export function FindingCard({
  finding,
  selected,
  wide,
  onInspect,
}: {
  finding: VerifiedFindingOut
  selected: boolean
  /** Whether the inspector sits beside the list (true) or opens as a sheet. */
  wide: boolean
  onInspect: (id: string) => void
}) {
  const claimId = `finding-${finding.id}-claim`

  return (
    <article
      id={`finding-card-${finding.id}`}
      tabIndex={-1}
      aria-labelledby={claimId}
      className={`rounded-xl border bg-white p-5 transition-shadow focus:outline-none ${
        selected && wide
          ? 'border-accent-600 shadow-[0_0_0_1px_var(--color-accent-600)]'
          : 'border-slate-200 shadow-[0_1px_2px_0_rgb(15_23_42/0.04)]'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-[0.6875rem] font-semibold tracking-wide text-accent-700 uppercase">
          {humanise(finding.type)}
          <span className="font-medium text-slate-500 normal-case">
            {' · '}
            {pageRef(finding.evidence.page, finding.evidence.section)}
          </span>
        </p>
        <VerificationBadge status={finding.verification_status} />
      </div>

      <h3 id={claimId} className="mt-3 font-display text-base leading-snug font-semibold text-slate-900">
        {finding.claim}
      </h3>

      <div className="mt-3">
        <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
          Document evidence
        </p>
        {/* Rendered as text, never as markup, and never edited here - this is
            the document's own wording, quoted back by the backend. */}
        <blockquote className="mt-1.5 rounded-r-md border-l-2 border-slate-300 bg-slate-50 py-2 pr-3 pl-3 text-[0.8125rem] leading-[1.65] text-slate-800">
          &ldquo;{finding.evidence.quote}&rdquo;
        </blockquote>
      </div>

      <div className="mt-3">
        <Explanation finding={finding} />
      </div>

      <div className="mt-4 flex justify-end border-t border-slate-100 pt-3">
        <button
          type="button"
          onClick={() => onInspect(finding.id)}
          aria-pressed={wide ? selected : undefined}
          aria-controls={wide ? 'evidence-inspector' : undefined}
          aria-haspopup={wide ? undefined : 'dialog'}
          aria-describedby={claimId}
          className="inline-flex min-h-9 items-center gap-1 rounded-md px-2 text-xs font-semibold text-accent-700 hover:bg-accent-50"
        >
          {wide && selected ? 'Shown in inspector' : 'Inspect evidence'}
          <Icon name="chevronRight" className="size-3.5" />
        </button>
      </div>
    </article>
  )
}
