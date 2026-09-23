import type { ReactNode } from 'react'

import { humanise } from '../../lib/format'
import { verdictFor } from '../../lib/verdicts'
import type { VerifiedFindingOut } from '../../types/api'
import { Icon } from '../ui/Icon'
import { VerificationBadge } from '../ui/VerificationBadge'
import { Explanation } from './FindingCard'

function Label({ children }: { children: string }) {
  return (
    <h4 className="font-mono text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
      {children}
    </h4>
  )
}

function Disclosure({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="group rounded-lg border border-slate-200 bg-white">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 px-3.5 text-sm font-medium text-slate-800 [&::-webkit-details-marker]:hidden">
        {summary}
        <Icon name="chevronRight" className="size-4 text-slate-500 transition-transform group-open:rotate-90" />
      </summary>
      <div className="border-t border-slate-100 px-3.5 py-3 text-sm leading-relaxed text-slate-700">
        {children}
      </div>
    </details>
  )
}

/**
 * Everything the backend returned about one finding, laid out for checking.
 *
 * The verdict and its reason come from the finding's own `verification_status`.
 * The section appears only when the backend confirmed that exact label on the
 * cited page; otherwise the page is the whole citation.
 */
export function InspectorBody({ finding }: { finding: VerifiedFindingOut }) {
  const verdict = verdictFor(finding.verification_status)
  const { evidence } = finding

  return (
    <div className="space-y-5">
      <div>
        <p className="font-mono text-[0.6875rem] font-semibold tracking-wide text-accent-700 uppercase">
          {humanise(finding.type)}
        </p>
        <p className="mt-1.5 font-display text-lg leading-snug font-semibold text-slate-900">
          {finding.claim}
        </p>
      </div>

      <div>
        <Label>Document evidence</Label>
        <p className="mt-1 text-xs text-slate-500">Exact quotation from the uploaded document.</p>
        <blockquote className="mt-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-[0.8125rem] leading-[1.65] text-slate-800">
          <span className="block border-l-2 border-slate-300 pl-3">&ldquo;{evidence.quote}&rdquo;</span>
        </blockquote>
      </div>

      <div>
        <Label>Source</Label>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-slate-500">Page</dt>
          <dd className="font-mono text-slate-900">{evidence.page}</dd>
          {evidence.section && (
            <>
              <dt className="text-slate-500">Section</dt>
              <dd className="font-mono text-slate-900">{evidence.section}</dd>
            </>
          )}
        </dl>
      </div>

      <div>
        <Label>Verification</Label>
        <div className="mt-2">
          <VerificationBadge status={finding.verification_status} />
        </div>
      </div>

      {/* Carries its own label, which says whether the text establishes it. */}
      <Explanation finding={finding} />

      <div className="space-y-2">
        <Disclosure summary="Why this status?">
          <p>{verdict.why}</p>
          <p className="mt-2 text-xs text-slate-500">
            Verified means the quotation was found where it is cited &mdash; not that the clause
            is fair, enforceable or complete.
          </p>
          {!evidence.section && (
            <p className="mt-2 text-xs text-slate-500">
              No section is shown because a section label is displayed only when that exact
              label appears on the cited page.
            </p>
          )}
        </Disclosure>
        <Disclosure summary="Technical details">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
            <dt className="text-slate-500">Finding ID</dt>
            <dd className="font-mono break-all text-slate-800">{finding.id}</dd>
            <dt className="text-slate-500">Category (model)</dt>
            <dd className="font-mono break-all text-slate-800">{finding.type}</dd>
            <dt className="text-slate-500">Verification status</dt>
            <dd className="font-mono text-slate-800">{finding.verification_status}</dd>
            <dt className="text-slate-500">Explanation verified</dt>
            <dd className="font-mono text-slate-800">{finding.explanation_verified ? 'yes' : 'no'}</dd>
          </dl>
        </Disclosure>
      </div>
    </div>
  )
}

/** The inspector panel beside the findings list on wide screens. */
export function EvidenceInspector({ finding }: { finding: VerifiedFindingOut | null }) {
  return (
    <section
      id="evidence-inspector"
      aria-labelledby="evidence-inspector-heading"
      className="rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_0_rgb(15_23_42/0.04)]"
    >
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-5 py-3">
        <h3
          id="evidence-inspector-heading"
          className="flex items-center gap-2 font-display text-sm font-semibold text-slate-900"
        >
          <Icon name="book" className="size-4 text-accent-700" />
          Evidence inspector
        </h3>
        {finding && (
          <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[0.6875rem] font-semibold text-slate-700">
            p. {finding.evidence.page}
            {finding.evidence.section ? ` · ${finding.evidence.section}` : ''}
          </span>
        )}
      </div>
      <div className="p-5">
        {finding ? (
          <InspectorBody finding={finding} />
        ) : (
          <p className="text-sm text-slate-600">Select a finding to inspect its evidence.</p>
        )}
      </div>
    </section>
  )
}
