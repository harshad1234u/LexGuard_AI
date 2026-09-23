import type { useAnalysis } from '../../hooks/useAnalysis'
import { plural } from '../../lib/format'
import type { StatusResponse, UploadResponse } from '../../types/api'
import type { WorkspaceTab } from '../../lib/tabs'
import { Button } from '../ui/Button'
import { Icon } from '../ui/Icon'
import { ErrorState, StatusBanner } from '../ui/StatusBanner'
import { AnalysisProgress } from './AnalysisProgress'
import { AnalysisStopped } from './AnalysisStopped'
import { CoveragePanel } from './CoveragePanel'

interface Props {
  document: UploadResponse
  status: StatusResponse | null
  extracting: boolean
  extractError: string | null
  analysis: ReturnType<typeof useAnalysis>
  onExtract: () => void
  onAnalyze: () => void
  onGoTo: (tab: WorkspaceTab) => void
}

/**
 * The one place the document moves forward: read it, then analyse it.
 *
 * Both steps are deliberate user actions. Nothing here runs from an effect, so
 * a re-render cannot buy an inference.
 */
export function DocumentProcess({
  document,
  status,
  extracting,
  extractError,
  analysis,
  onExtract,
  onAnalyze,
  onGoTo,
}: Props) {
  const extracted = status !== null && status.coverage_status !== 'pending'
  const eligible = status?.analysis_eligible === true
  const { result, running, error } = analysis

  return (
    <section
      aria-labelledby="processing-heading"
      className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_0_rgb(15_23_42/0.04)]"
    >
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-5 py-3">
        <h3 id="processing-heading" className="font-display text-sm font-semibold text-slate-900">
          Document processing
        </h3>
        <span className="hidden font-mono text-[0.6875rem] font-medium tracking-wide text-slate-500 uppercase sm:inline">
          Upload → verified results
        </span>
      </div>

      <div className="space-y-4 px-5 py-5" aria-live="polite">
        <AnalysisProgress
          document={document}
          status={status}
          extracting={extracting}
          extractError={extractError}
          analysis={analysis.status}
          result={result}
          starting={analysis.starting}
          running={running}
          reconnecting={analysis.reconnecting}
          analysisError={error}
        />

        {document.source_repaired && (
          <StatusBanner tone="partial" title="This PDF was repaired before it could be read">
            The page count may be lower than the original document, so a complete-document
            analysis will not be offered for it.
          </StatusBanner>
        )}

        {status && extracted && <CoveragePanel status={status} />}

        {extractError && (
          <ErrorState title="The document could not be read">{extractError}</ErrorState>
        )}

        {error && <AnalysisStopped status={analysis.status} document={status} error={error} />}

        {result && !running && (
          <StatusBanner tone="verified" role="status" title="Analysis complete">
            {result.findings.length} verified{' '}
            {plural(result.findings.length, 'finding', 'findings')} released
            {result.withheld.total > 0 ? ` · ${result.withheld.total} withheld` : ''}, out of{' '}
            {result.proposed_count} the model proposed.
          </StatusBanner>
        )}
      </div>

      <div className="flex flex-col gap-3 border-t border-slate-200 bg-slate-50 px-5 py-4 sm:flex-row sm:items-center">
        {!extracted && (
          <>
            <Button onClick={onExtract} disabled={extracting} className="sm:shrink-0">
              {extracting ? (
                <>
                  <Icon name="loader" className="size-4 animate-spin motion-reduce:animate-none" />
                  Reading every page…
                </>
              ) : (
                'Read the document'
              )}
            </Button>
            <p className="text-xs text-slate-600">
              Extracts the text of every page and checks that none are missing. No AI model is
              used for this step.
            </p>
          </>
        )}

        {/* Analysis is offered only when the backend says the document qualifies.
            The backend enforces the same rule independently: this button being
            hidden is a courtesy, not the control. */}
        {extracted && eligible && !result && (
          <>
            <Button onClick={onAnalyze} disabled={running} className="sm:shrink-0">
              {running ? (
                <>
                  <Icon name="loader" className="size-4 animate-spin motion-reduce:animate-none" />
                  Analysing…
                </>
              ) : error ? (
                'Try the analysis again'
              ) : (
                'Analyse this document'
              )}
            </Button>
            <p className="text-xs text-slate-600">
              {running
                ? 'This usually takes a minute or two. Every statement the model proposes is checked against the document before it is shown.'
                : 'The model proposes findings with quotations. Each one is checked against your document before it is released.'}
            </p>
          </>
        )}

        {result && !running && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => onGoTo('findings')}>
              Review findings
              <Icon name="arrowRight" className="size-4" />
            </Button>
            <Button variant="secondary" onClick={() => onGoTo('ask')}>
              Ask a question
            </Button>
          </div>
        )}

        {extracted && !eligible && (
          <p className="text-xs text-slate-600">
            Values and questions need every page to have been read, so they are held back for
            this file as well.
          </p>
        )}
      </div>
    </section>
  )
}
