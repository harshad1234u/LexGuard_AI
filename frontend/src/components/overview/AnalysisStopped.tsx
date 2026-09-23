import type { AnalysisStatusResponse, StatusResponse } from '../../types/api'
import { StatusBanner } from '../ui/StatusBanner'

/**
 * Why the analysis stopped, and what it does and does not say about the document.
 *
 * A bare provider error reads as "your document failed". It is not: the
 * document was read, every page of it, and the extraction results are still on
 * screen. Only the model step stopped. Conflating the two would push a user to
 * re-upload or doubt a file that is perfectly fine.
 *
 * The second half is the safety statement, and it is the reason this is not
 * merely nicer wording: when the model does not answer, *nothing* is released.
 * There is no partial analysis behind this message to go looking for.
 *
 * Driven entirely by backend state - the category the workflow recorded and the
 * document's own coverage verdict. Nothing here infers a cause.
 */
const STOPPED_BECAUSE: Record<string, string> = {
  provider_unavailable: 'the AI analysis service was unavailable',
  provider_timeout: 'the AI analysis service did not respond in time',
  provider_rate_limited: 'the AI analysis service was busy',
  provider_not_configured: 'the AI analysis service is not configured',
  model_output_invalid: 'the model’s reply could not be read as an analysis',
  analysis_timeout: 'the analysis took too long and was stopped',
}

export function AnalysisStopped({
  status,
  document,
  error,
}: {
  status: AnalysisStatusResponse | null
  document: StatusResponse | null
  error: string
}) {
  const category = status?.error_category ?? null
  const because = category ? STOPPED_BECAUSE[category] : undefined

  // Only claim the document is fine when the backend says it is. A coverage or
  // ingestion failure is a document problem, and must not be reassured away.
  const documentIsFine = document?.analysis_eligible === true

  return (
    <StatusBanner tone="danger" role="alert" title="The analysis could not be completed">
      <p>{error}</p>
      {documentIsFine && (
        <p className="mt-2 text-xs">
          Your document was read in full
          {document ? ` — all ${document.expected_pages} pages` : ''}
          {because ? `, but ${because}` : ', but the analysis could not be completed'}. No
          analysis results were released, and nothing unverified was shown. Your document is
          still available, and you can try the analysis again.
        </p>
      )}
    </StatusBanner>
  )
}
