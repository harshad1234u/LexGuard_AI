import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'

import type { useAnalysis } from '../../hooks/useAnalysis'
import { useValues } from '../../hooks/useValues'
import type { Phase } from '../../lib/phase'
import type { StatusResponse, UploadResponse } from '../../types/api'
import { AskDocumentView } from '../ask/AskDocumentView'
import { FindingsView } from '../findings/FindingsView'
import { OverviewView } from '../overview/OverviewView'
import { ValuesView } from '../values/ValuesView'
import { panelId, tabId, type WorkspaceTab } from '../../lib/tabs'
import { DocumentTabs, type TabSpec } from './DocumentTabs'

interface Props {
  document: UploadResponse
  status: StatusResponse | null
  phase: Phase
  extracting: boolean
  extractError: string | null
  analysis: ReturnType<typeof useAnalysis>
  onExtract: () => void
}

/** The heading each panel moves focus to when another view sends the user there. */
const HEADINGS: Record<WorkspaceTab, string> = {
  overview: 'panel-overview-heading',
  findings: 'panel-findings-heading',
  values: 'values-heading',
  ask: 'ask-heading',
}

/**
 * One uploaded document, as four views over the same backend state.
 *
 * Every panel stays mounted and inactive ones are `hidden`. That keeps each
 * view's own state - a question being answered, a selected value - when the
 * user looks elsewhere, and means switching tabs never re-requests anything.
 * `hidden` also removes a panel from the accessibility tree, so a screen
 * reader hears only the view on screen.
 */
export function DocumentWorkspace({
  document,
  status,
  phase,
  extracting,
  extractError,
  analysis,
  onExtract,
}: Props) {
  const [tab, setTab] = useState<WorkspaceTab>('overview')
  const [selectedFinding, setSelectedFinding] = useState<string | null>(null)
  const pendingFocus = useRef<string | null>(null)
  /** Marks where the tab bar starts, so a tab switch can scroll back to it. */
  const anchor = useRef<HTMLDivElement>(null)
  const eligible = status?.analysis_eligible === true
  const values = useValues(document.document_id, eligible)

  /** Switch view from a link inside another view, and take focus with it. */
  const goTo = useCallback((next: WorkspaceTab, focusId?: string) => {
    pendingFocus.current = focusId ?? HEADINGS[next]
    setTab(next)
  }, [])

  // A new view starts at its top, not at whatever depth the last one was
  // scrolled to - and never above the tab bar, which stays in reach.
  useEffect(() => {
    const top = anchor.current
      ? anchor.current.getBoundingClientRect().top + window.scrollY
      : 0
    if (window.scrollY > top) window.scrollTo({ top })

    const id = pendingFocus.current
    if (!id) return
    pendingFocus.current = null
    const target = window.document.getElementById(id)
    target?.focus({ preventScroll: true })
    if (target && target.tagName !== 'H2') target.scrollIntoView({ block: 'center' })
  }, [tab])

  const inspectFinding = useCallback(
    (findingId: string) => {
      setSelectedFinding(findingId)
      goTo('findings', `finding-card-${findingId}`)
    },
    [goTo],
  )

  const tabs: TabSpec[] = [
    { id: 'overview', label: 'Overview', icon: 'layout' },
    {
      id: 'findings',
      label: 'Findings & Clauses',
      icon: 'list',
      count: analysis.result ? analysis.result.findings.length : null,
    },
    {
      id: 'values',
      label: 'Values & Dates',
      icon: 'calendar',
      count: eligible && values.values ? values.values.length : null,
    },
    { id: 'ask', label: 'Ask Document', icon: 'message' },
  ]

  const panel = (id: WorkspaceTab, content: ReactNode) => (
    <div
      id={panelId(id)}
      role="tabpanel"
      aria-labelledby={tabId(id)}
      hidden={tab !== id}
      className="mx-auto max-w-[90rem] px-4 py-6 sm:px-6 lg:px-8 lg:py-8"
    >
      {content}
    </div>
  )

  return (
    <>
      <div ref={anchor} aria-hidden="true" />
      <DocumentTabs tabs={tabs} active={tab} onChange={setTab} />

      {panel(
        'overview',
        <OverviewView
          document={document}
          status={status}
          phase={phase}
          extracting={extracting}
          extractError={extractError}
          analysis={analysis}
          values={values}
          onExtract={onExtract}
          onAnalyze={() => void analysis.analyze()}
          onGoTo={goTo}
          onInspectFinding={inspectFinding}
        />,
      )}
      {panel(
        'findings',
        <FindingsView
          phase={phase}
          result={analysis.result}
          selectedId={selectedFinding}
          onSelect={setSelectedFinding}
          onGoTo={goTo}
        />,
      )}
      {panel('values', <ValuesView values={values} phase={phase} onGoTo={goTo} />)}
      {panel(
        'ask',
        <AskDocumentView
          documentId={document.document_id}
          eligible={eligible}
          phase={phase}
          // Results are available only once the findings endpoint has
          // answered, so this is the same condition that renders them - not a
          // guess from the analysis status alone.
          analysisComplete={analysis.result !== null}
          onGoTo={goTo}
        />,
      )}
    </>
  )
}
