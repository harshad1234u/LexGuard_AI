import type { useAnalysis } from '../../hooks/useAnalysis'
import type { ValuesState } from '../../hooks/useValues'
import type { Phase } from '../../lib/phase'
import type { StatusResponse, UploadResponse } from '../../types/api'
import type { WorkspaceTab } from '../../lib/tabs'
import { DocumentProcess } from './DocumentProcess'
import { FindingsByTopic } from './FindingsByTopic'
import {
  DocumentHeader,
  DocumentStatusCard,
  ValuesSummaryCard,
  VerificationExplainer,
} from './OverviewCards'

interface Props {
  document: UploadResponse
  status: StatusResponse | null
  phase: Phase
  extracting: boolean
  extractError: string | null
  analysis: ReturnType<typeof useAnalysis>
  values: ValuesState
  onExtract: () => void
  onAnalyze: () => void
  onGoTo: (tab: WorkspaceTab) => void
  onInspectFinding: (findingId: string) => void
}

/**
 * The executive view: what the document is, how far it has got, and what was
 * established - each block drawn from a backend response and nothing else.
 *
 * There is no document summary here, because the backend produces none. The
 * topic grouping below is the closest honest thing: verified findings under
 * headings, with the counts of what was withheld beside them.
 */
export function OverviewView({
  document,
  status,
  phase,
  extracting,
  extractError,
  analysis,
  values,
  onExtract,
  onAnalyze,
  onGoTo,
  onInspectFinding,
}: Props) {
  const extracted = status !== null && status.coverage_status !== 'pending'

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0 space-y-6">
        <DocumentHeader document={document} />
        <DocumentProcess
          document={document}
          status={status}
          extracting={extracting}
          extractError={extractError}
          analysis={analysis}
          onExtract={onExtract}
          onAnalyze={onAnalyze}
          onGoTo={onGoTo}
        />
        {/* Rendered only once the backend has published a grouping, so the
            processing card keeps sole ownership of the loading, error and
            analysis-stopped states. */}
        {analysis.result && !analysis.running && !analysis.error && (
          <FindingsByTopic overview={analysis.overview} onInspect={onInspectFinding} />
        )}
      </div>

      <aside aria-label="Document details" className="space-y-6">
        <DocumentStatusCard status={status} phase={phase} result={analysis.result} />
        <ValuesSummaryCard values={values} extracted={extracted} onGoTo={onGoTo} />
        <VerificationExplainer />
      </aside>
    </div>
  )
}
