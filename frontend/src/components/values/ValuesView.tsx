import { useMemo, useState } from 'react'

import { useMediaQuery, WIDE } from '../../hooks/useMediaQuery'
import type { ValuesState } from '../../hooks/useValues'
import { VALUE_GROUPS, valueKey } from '../../lib/format'
import type { Phase } from '../../lib/phase'
import type { ValueKind, ValuesExtraction } from '../../types/api'
import type { WorkspaceTab } from '../../lib/tabs'
import { Button } from '../ui/Button'
import { EmptyState } from '../ui/EmptyState'
import { Sheet } from '../ui/Sheet'
import { ErrorState, StatusBanner } from '../ui/StatusBanner'
import { ValueDetails, ValueInspector } from './ValueInspector'
import { ValueTable } from './ValueTable'

/**
 * What to say when nothing was found.
 *
 * "No values were detected" is true of two different documents and useful for
 * only one of them. A contract the application read in full that simply states
 * no amounts has been searched; a document from which no text was recovered
 * has not. Saying the same sentence to both readers presents a fact about the
 * extraction as a fact about the document - a quiet false negative, and the
 * opposite of what this project exists to do.
 *
 * The counts come from the backend manifest. The scanned-PDF wording appears
 * only when the application really did read nothing, never merely because the
 * list is empty.
 */
function NothingFound({ extraction }: { extraction: ValuesExtraction | null }) {
  // No counts means an older or unexpected response shape. Fall back to the
  // claim that holds either way rather than guessing at a cause.
  if (extraction === null) {
    return (
      <p className="text-sm text-slate-600">No supported values were detected in this document.</p>
    )
  }

  if (extraction.characters === 0) {
    return (
      <StatusBanner tone="partial" title="No readable text was extracted from this document.">
        <p className="text-xs">
          This PDF may be scanned, image-based, or use a text format the application does not
          support. Nothing here says the document is empty - only that its text could not be read,
          so it could not be searched.
        </p>
      </StatusBanner>
    )
  }

  return (
    <p className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
      No supported values were detected in the extracted text. The application read{' '}
      {extraction.pages_with_text} of {extraction.pages_total}{' '}
      {extraction.pages_total === 1 ? 'page' : 'pages'} and found no amounts, percentages, time
      periods or dates in them.
    </p>
  )
}

/**
 * Values the application located in the uploaded document.
 *
 * Deliberately not part of the findings path. A finding is a model-proposed
 * statement that the backend verified; a value here is a string that occurs in
 * the document, with the page it occurs on. The view therefore makes no claim
 * about importance, obligation or risk, and says so in its own subtitle.
 *
 * It needs no model call, so it works when the provider is unavailable.
 */
export function ValuesView({
  values: state,
  phase,
  onGoTo,
}: {
  values: ValuesState
  phase: Phase
  onGoTo: (tab: WorkspaceTab) => void
}) {
  const wide = useMediaQuery(WIDE)
  const [filter, setFilter] = useState<ValueKind | null>(null)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)

  const { values, extraction, error, loading, eligible } = state
  const keyed = useMemo(
    () => (values ?? []).map((item, index) => ({ item, key: valueKey(item, index) })),
    [values],
  )
  const selected = keyed.find((entry) => entry.key === selectedKey)?.item ?? null

  const select = (key: string) => {
    setSelectedKey(key)
    if (!wide) setSheetOpen(true)
  }

  let body
  if (!eligible) {
    // Before extraction, and when coverage is incomplete. The backend refuses
    // to index a document it did not read in full.
    body =
      phase === 'blocked' ? (
        <EmptyState
          icon="alertTriangle"
          title="Values are listed only for documents read in full"
          action={
            <Button variant="secondary" onClick={() => onGoTo('overview')}>
              See coverage details
            </Button>
          }
        >
          Not every page of this document could be read, so its values are not indexed.
        </EmptyState>
      ) : (
        <EmptyState
          icon="calendar"
          title="Read the document first"
          action={
            <Button variant="secondary" onClick={() => onGoTo('overview')}>
              Go to Overview
            </Button>
          }
        >
          Values are indexed from the extracted text once every page has been read.
        </EmptyState>
      )
  } else if (loading) {
    body = <p className="text-sm text-slate-600">Reading the document&hellip;</p>
  } else if (error) {
    body = <ErrorState title="Values could not be listed">{error}</ErrorState>
  } else if (values !== null && values.length === 0) {
    body = <NothingFound extraction={extraction} />
  } else if (values !== null) {
    const groups = VALUE_GROUPS.map((group) => ({
      ...group,
      items: keyed.filter((entry) => entry.item.kind === group.kind),
    })).filter((group) => group.items.length > 0)
    const shown = filter ? groups.filter((group) => group.kind === filter) : groups

    body = (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1fr)_26rem]">
        <div className="min-w-0 space-y-4">
          <div role="group" aria-label="Filter values by category" className="flex flex-wrap gap-2">
            {[{ kind: null, heading: 'All', count: keyed.length }, ...groups.map((g) => ({ kind: g.kind, heading: g.heading, count: g.items.length }))].map(
              ({ kind, heading, count }) => {
                const active = filter === kind
                return (
                  <button
                    key={kind ?? 'all'}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setFilter(kind)}
                    className={`inline-flex min-h-9 items-center gap-1.5 rounded-md border px-3 text-xs font-medium transition-colors ${
                      active
                        ? 'border-navy-900 bg-navy-900 text-white'
                        : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
                    }`}
                  >
                    {heading}
                    <span className="font-mono opacity-75">{count}</span>
                  </button>
                )
              },
            )}
          </div>

          {shown.map((group) => (
            <ValueTable
              key={group.kind}
              heading={group.heading}
              headingId={`values-${group.kind}`}
              items={group.items}
              selectedKey={selectedKey}
              wide={wide}
              onSelect={select}
            />
          ))}

          <p className="text-xs leading-relaxed text-slate-500">
            These are values the application detected in the document text. They are not ranked,
            and nothing here says what a value means or whether it matters.
          </p>
        </div>

        {wide && (
          <div className="self-start lg:sticky lg:top-16">
            <ValueInspector item={selected} all={values} />
          </div>
        )}
      </div>
    )
  }

  return (
    // Named so the view is a landmark a screen-reader user can jump to, and so
    // its scope is unambiguous: everything inside is extraction, nothing inside
    // is interpretation.
    <section aria-labelledby="values-heading" className="space-y-6">
      <div className="max-w-2xl">
        <h2
          id="values-heading"
          tabIndex={-1}
          className="font-display text-2xl font-semibold tracking-tight text-navy-950 focus:outline-none"
        >
          Values &amp; Dates
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Amounts, dates, percentages and time periods detected in the uploaded document, with page
          references. This is not a summary and not a risk assessment.
        </p>
      </div>

      <div aria-live="polite">{body}</div>

      {!wide && values && (
        <Sheet open={sheetOpen && selected !== null} title="Value inspector" onClose={() => setSheetOpen(false)}>
          {selected && <ValueDetails item={selected} all={values} />}
        </Sheet>
      )}
    </section>
  )
}
