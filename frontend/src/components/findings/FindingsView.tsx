import { useMemo, useState } from 'react'

import { useMediaQuery, WIDE } from '../../hooks/useMediaQuery'
import { humanise, plural } from '../../lib/format'
import type { Phase } from '../../lib/phase'
import type { AnalysisResult } from '../../types/api'
import type { WorkspaceTab } from '../../lib/tabs'
import { Button } from '../ui/Button'
import { EmptyState } from '../ui/EmptyState'
import { Sheet } from '../ui/Sheet'
import { StatusBanner } from '../ui/StatusBanner'
import { EvidenceInspector, InspectorBody } from './EvidenceInspector'
import { FindingCard } from './FindingCard'
import { WithheldSummary } from './WithheldSummary'

interface Props {
  phase: Phase
  result: AnalysisResult | null
  selectedId: string | null
  onSelect: (id: string) => void
  onGoTo: (tab: WorkspaceTab) => void
}

function ViewHeader({ result }: { result: AnalysisResult | null }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h2
          id="panel-findings-heading"
          tabIndex={-1}
          className="font-display text-2xl font-semibold tracking-tight text-navy-950 focus:outline-none"
        >
          Findings &amp; Clauses
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Statements the model proposed about this document that the application verified against
          its text, each shown with the quotation it rests on.
        </p>
      </div>
      {result && (
        <dl className="flex gap-2 font-mono text-xs">
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-emerald-800">
            <dt className="inline">Released </dt>
            <dd className="inline font-semibold">{result.findings.length}</dd>
          </div>
          <div className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-700">
            <dt className="inline">Withheld </dt>
            <dd className="inline font-semibold">{result.withheld.total}</dd>
          </div>
          <div className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-700">
            <dt className="inline">Proposed </dt>
            <dd className="inline font-semibold">{result.proposed_count}</dd>
          </div>
        </dl>
      )}
    </div>
  )
}

const goToOverview = (onGoTo: Props['onGoTo'], label = 'Go to Overview') => (
  <Button variant="secondary" onClick={() => onGoTo('overview')}>
    {label}
  </Button>
)

/**
 * The primary review surface: released findings beside an evidence inspector.
 *
 * Everything shown here came from the findings endpoint, after the output
 * gate. The view has no notion of a finding it was not given: withheld
 * statements are counts, and an analysis that did not finish shows nothing
 * but the fact that it did not.
 */
export function FindingsView({ phase, result, selectedId, onSelect, onGoTo }: Props) {
  const wide = useMediaQuery(WIDE)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [filter, setFilter] = useState<string | null>(null)

  const findings = useMemo(() => result?.findings ?? [], [result])
  const types = useMemo(() => [...new Set(findings.map((finding) => finding.type))], [findings])
  const visible = filter ? findings.filter((finding) => finding.type === filter) : findings
  const selected =
    visible.find((finding) => finding.id === selectedId) ?? (wide ? visible[0] : undefined) ?? null

  const inspect = (id: string) => {
    onSelect(id)
    if (!wide) setSheetOpen(true)
  }

  let body
  if (!result) {
    body =
      phase === 'running' ? (
        <EmptyState icon="loader" title="Analysis in progress" action={goToOverview(onGoTo, 'Follow progress')}>
          Findings appear here once every statement the model proposes has been checked against
          the document.
        </EmptyState>
      ) : phase === 'stopped' ? (
        <EmptyState icon="ban" title="No findings were released" action={goToOverview(onGoTo)}>
          The analysis did not finish, so nothing was released and nothing unverified is shown.
          The Overview explains what happened and lets you try again.
        </EmptyState>
      ) : phase === 'blocked' ? (
        <EmptyState icon="alertTriangle" title="Analysis is blocked for this document" action={goToOverview(onGoTo, 'See coverage details')}>
          Not every page could be read, so a complete-document analysis is not offered. The
          Overview shows which pages were affected.
        </EmptyState>
      ) : (
        <EmptyState icon="list" title="No findings yet" action={goToOverview(onGoTo)}>
          {phase === 'ready'
            ? 'Run the analysis from the Overview. Findings appear here once each one has been checked against the text.'
            : 'Read the document and run the analysis from the Overview. Findings appear here once each one has been checked against the text.'}
        </EmptyState>
      )
  } else if (findings.length === 0) {
    // Two different statements, deliberately not merged. Neither one claims
    // the document is free of risk - that is a conclusion this tool is not in
    // a position to reach.
    body = (
      <div className="max-w-3xl space-y-4">
        <StatusBanner tone="partial" title="No verified findings">
          {result.insufficient_evidence
            ? 'No verified findings could be established from this document. The model proposed ' +
              'statements, but none could be confirmed against the text, so none are shown.'
            : 'No verified findings could be established from this document.'}{' '}
          This does not mean the document carries no risk &mdash; only that nothing was
          confirmed. Read the document itself, and consult a qualified lawyer about anything that
          matters.
        </StatusBanner>
        <WithheldSummary result={result} />
      </div>
    )
  } else {
    body = (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_26rem] xl:grid-cols-[minmax(0,1fr)_30rem]">
        <div className="min-w-0 space-y-4">
          {types.length > 1 && (
            <div role="group" aria-label="Filter findings by category" className="flex flex-wrap gap-2">
              {[null, ...types].map((type) => {
                const active = filter === type
                const count = type ? findings.filter((f) => f.type === type).length : findings.length
                return (
                  <button
                    key={type ?? 'all'}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setFilter(type)}
                    className={`inline-flex min-h-9 items-center gap-1.5 rounded-md border px-3 text-xs font-medium transition-colors ${
                      active
                        ? 'border-navy-900 bg-navy-900 text-white'
                        : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
                    }`}
                  >
                    {type ? humanise(type) : 'All'}
                    <span className="font-mono opacity-75">{count}</span>
                  </button>
                )
              })}
            </div>
          )}

          <div className="space-y-4">
            {visible.map((finding) => (
              <FindingCard
                key={finding.id}
                finding={finding}
                wide={wide}
                selected={selected?.id === finding.id}
                onInspect={inspect}
              />
            ))}
          </div>

          <WithheldSummary result={result} />

          <p className="text-xs leading-relaxed text-slate-500">
            Showing {findings.length} of {result.proposed_count} proposed{' '}
            {plural(result.proposed_count, 'statement', 'statements')}. Verified means the quoted
            text was found on the cited page &mdash; not that the clause is fair, enforceable, or
            complete.
          </p>
        </div>

        {wide && (
          <div className="self-start lg:sticky lg:top-16">
            <EvidenceInspector finding={selected} />
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <ViewHeader result={result} />
      {body}
      {!wide && (
        <Sheet open={sheetOpen && selected !== null} title="Evidence inspector" onClose={() => setSheetOpen(false)}>
          {selected && <InspectorBody finding={selected} />}
        </Sheet>
      )}
    </div>
  )
}
