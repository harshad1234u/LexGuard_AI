import type { ReactNode } from 'react'

import type { ValuesState } from '../../hooks/useValues'
import { formatSize, plural, VALUE_GROUPS } from '../../lib/format'
import { COVERAGE_LABEL, PHASE_LABEL, type Phase } from '../../lib/phase'
import type { AnalysisResult, StatusResponse, UploadResponse, ValueKind } from '../../types/api'
import type { WorkspaceTab } from '../../lib/tabs'
import { Icon, type IconName } from '../ui/Icon'
import { Badge } from '../ui/VerificationBadge'

function Card({
  title,
  children,
  action,
}: {
  title: string
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_0_rgb(15_23_42/0.04)]">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-mono text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
          {title}
        </h3>
        {action}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  )
}

/** The document as uploaded: name, format, size and pages. Read from the upload response. */
export function DocumentHeader({ document }: { document: UploadResponse }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_0_rgb(15_23_42/0.04)] sm:p-6">
      <div className="flex flex-wrap items-center gap-2 font-mono text-[0.6875rem] font-semibold tracking-wide text-slate-600 uppercase">
        <span className="rounded border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-rose-700">
          PDF
        </span>
        <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5">
          {document.page_count} {plural(document.page_count, 'page', 'pages')}
        </span>
        <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5">
          {formatSize(document.size_bytes)}
        </span>
        {document.source_repaired && (
          <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-amber-900">
            Repaired
          </span>
        )}
      </div>
      {/* Rendered as text, never as markup - the filename is user-supplied. */}
      <h2
        id="panel-overview-heading"
        tabIndex={-1}
        className="mt-3 font-display text-xl font-semibold tracking-tight break-words text-navy-950 focus:outline-none sm:text-2xl"
      >
        {document.filename}
      </h2>
    </div>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd className="text-right text-sm text-slate-900">{children}</dd>
    </div>
  )
}

/**
 * Where the document stands, in the backend's own terms.
 *
 * Counts only, each one taken from a response field. No score, no percentage
 * and no rating: the backend computes none, and a number here that it did not
 * compute would be the one thing on the page with nothing behind it.
 */
export function DocumentStatusCard({
  status,
  phase,
  result,
}: {
  status: StatusResponse | null
  phase: Phase
  result: AnalysisResult | null
}) {
  const coverage = status ? COVERAGE_LABEL[status.coverage_status] : COVERAGE_LABEL.pending
  const analysis = PHASE_LABEL[phase]

  return (
    <Card title="Document status">
      <dl className="divide-y divide-slate-100">
        <Row label="Coverage">
          <Badge tone={coverage.tone}>{coverage.label}</Badge>
          {status && status.coverage_status !== 'pending' && (
            <span className="mt-1 block font-mono text-xs text-slate-500">
              {status.processed_pages}/{status.expected_pages} pages read
            </span>
          )}
        </Row>
        <Row label="Analysis">
          <Badge tone={analysis.tone}>{analysis.label}</Badge>
        </Row>
        <Row label="Verification">
          {result ? (
            <span className="font-mono text-xs leading-5">
              <span className="block text-emerald-800">{result.findings.length} released</span>
              <span className="block text-slate-600">{result.withheld.total} withheld</span>
              <span className="block text-slate-500">of {result.proposed_count} proposed</span>
            </span>
          ) : (
            <span className="text-xs text-slate-500">Runs with the analysis</span>
          )}
        </Row>
      </dl>
    </Card>
  )
}

const VALUE_ICONS: Record<ValueKind, IconName> = {
  currency: 'banknote',
  percentage: 'percent',
  duration: 'timer',
  date: 'calendar',
}

/**
 * How many values of each kind the index holds, with a route to the list.
 *
 * Counts, not a selection: picking "the important ones" would be a ranking the
 * index does not make.
 */
export function ValuesSummaryCard({
  values,
  extracted,
  onGoTo,
}: {
  values: ValuesState
  extracted: boolean
  onGoTo: (tab: WorkspaceTab) => void
}) {
  const list = values.values

  let body: ReactNode
  if (!extracted) {
    body = <p className="text-sm text-slate-600">Indexed once the document has been read.</p>
  } else if (!values.eligible) {
    body = <p className="text-sm text-slate-600">Listed only for documents read in full.</p>
  } else if (values.loading) {
    body = <p className="text-sm text-slate-600">Reading the document…</p>
  } else if (values.error || list === null) {
    body = <p className="text-sm text-slate-600">The values could not be loaded.</p>
  } else if (list.length === 0) {
    body = <p className="text-sm text-slate-600">None detected. See the Values tab for why.</p>
  } else {
    body = (
      <ul className="grid grid-cols-2 gap-2">
        {VALUE_GROUPS.map(({ kind, heading }) => {
          const count = list.filter((item) => item.kind === kind).length
          return (
            <li key={kind} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
              <span className="flex items-center gap-1.5 text-xs text-slate-600">
                <Icon name={VALUE_ICONS[kind]} className="size-3.5" />
                {heading}
              </span>
              <span className="mt-1 block font-display text-xl font-semibold text-slate-900 tabular-nums">
                {count}
              </span>
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <Card
      title="Values & dates"
      action={
        list && list.length > 0 ? (
          <button
            type="button"
            onClick={() => onGoTo('values')}
            className="inline-flex min-h-8 items-center gap-1 text-xs font-semibold text-accent-700 hover:underline"
          >
            View all
            <Icon name="chevronRight" className="size-3.5" />
          </button>
        ) : null
      }
    >
      {body}
      <p className="mt-3 text-xs text-slate-500">
        Located in the document text without an AI model.
      </p>
    </Card>
  )
}

/**
 * The product's one idea, stated where the results are.
 *
 * Each sentence describes a mechanism the backend runs (grounding.py,
 * policy.py). None of them is a claim about how accurate the result is.
 */
export function VerificationExplainer() {
  const steps = [
    ['The model interprets', 'It reads the document and proposes findings, each with a quotation and a page.'],
    ['The application verifies', 'Each quotation is located on the page it cites, and each claim is checked against its quotation.'],
    ['Only verified findings are released', 'The rest are withheld and counted. Their text is never shown.'],
  ] as const

  return (
    <Card title="How verification works">
      <ol className="space-y-3">
        {steps.map(([title, body], index) => (
          <li key={title} className="flex gap-3">
            <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-accent-50 font-mono text-xs font-semibold text-accent-700">
              {index + 1}
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-900">{title}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-600">{body}</p>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  )
}
