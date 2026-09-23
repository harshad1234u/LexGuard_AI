import { COVERAGE_LABEL } from '../../lib/phase'
import { TONE_CLASSES } from '../../lib/verdicts'
import type { StatusResponse } from '../../types/api'

/**
 * Coverage is an application-measured fact, so it is shown as an explicit
 * count rather than a reassuring word. The user should be able to see that
 * the page total came from the file, not from the model.
 */
export function CoveragePanel({ status }: { status: StatusResponse }) {
  const coverage = COVERAGE_LABEL[status.coverage_status] ?? COVERAGE_LABEL.pending

  return (
    <div className={`rounded-lg border px-4 py-3 ${TONE_CLASSES[coverage.tone]}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-sm font-semibold">Coverage: {coverage.label}</span>
        <span className="font-mono text-xs tabular-nums">
          {status.processed_pages} of {status.expected_pages} pages processed
        </span>
      </div>

      {status.coverage_explanation && (
        <p className="mt-2 text-xs leading-relaxed opacity-90">{status.coverage_explanation}</p>
      )}

      {status.failed_pages.length > 0 && (
        <p className="mt-1 text-xs">Pages that failed: {status.failed_pages.join(', ')}</p>
      )}

      {status.unreadable_pages.length > 0 && (
        <p className="mt-1 text-xs">
          Pages with no readable text: {status.unreadable_pages.join(', ')}
        </p>
      )}

      {!status.analysis_eligible && status.coverage_status !== 'pending' && (
        <p className="mt-2 border-t border-current/20 pt-2 text-xs font-medium">
          {status.coverage_status === 'incomplete' &&
            'Some pages could not be fully processed, so analysis cannot safely continue. '}
          A complete-document analysis is not available for this file.
        </p>
      )}
    </div>
  )
}
