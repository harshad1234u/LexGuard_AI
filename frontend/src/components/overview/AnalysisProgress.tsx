import type {
  AnalysisResult,
  AnalysisStage,
  AnalysisStatusResponse,
  StatusResponse,
  UploadResponse,
} from '../../types/api'
import { Icon } from '../ui/Icon'

interface Props {
  document: UploadResponse
  status: StatusResponse | null
  /** True while the extraction request is in flight. */
  extracting: boolean
  /** Set when the extraction request itself failed. */
  extractError: string | null
  analysis: AnalysisStatusResponse | null
  /**
   * The published result, once the findings endpoint has answered. Its counts
   * are the ones the rest of the workspace shows, so the timeline uses them
   * too rather than the status response's.
   */
  result: AnalysisResult | null
  /** True between the click and the first status response. */
  starting: boolean
  running: boolean
  /** True while polling is retrying through a transport fault. */
  reconnecting: boolean
  analysisError: string | null
}

type StepState = 'done' | 'active' | 'pending' | 'failed'

/**
 * The workflow's stages in order, matching the backend graph's nodes.
 * Position in this list is what decides whether a step is behind or ahead.
 */
const STAGE_ORDER: AnalysisStage[] = [
  'queued',
  'validating',
  'ingesting',
  'checking_coverage',
  'building_document_map',
  'analyzing',
  'verifying',
  'gating_output',
  'done',
]

const stageIndex = (stage: AnalysisStage | undefined): number =>
  stage ? STAGE_ORDER.indexOf(stage) : 0

/** What the backend is doing while the analysis step is active, by stage. */
const STAGE_DETAIL: Partial<Record<AnalysisStage, string>> = {
  queued: 'Queued…',
  validating: 'Preparing the document…',
  ingesting: 'Preparing the document…',
  checking_coverage: 'Re-checking page coverage…',
  building_document_map: 'Mapping the document…',
  analyzing: 'Analysing the document…',
}

const STATE_TEXT: Record<StepState, string> = {
  done: 'Completed',
  active: 'In progress',
  pending: 'Waiting',
  failed: 'Failed',
}

interface Step {
  key: string
  label: string
  state: StepState
  detail: string
}

/**
 * Turn backend state into the six things a user wants to know.
 *
 * Every state here is read from the backend, never guessed, and there is no
 * percentage: the backend reports a stage, not a fraction, and inventing one
 * would be a number with nothing behind it. "Preparing results" completes only
 * when the analysis is `completed`, which the backend sets only after its
 * output gate has run - so the UI cannot call a result ready earlier than the
 * application does.
 */
function buildSteps(props: Props): Step[] {
  const { document, status, extracting, extractError, analysis, starting, running } = props
  const coverage = status?.coverage_status ?? 'pending'
  const extracted = coverage !== 'pending' && coverage !== 'processing'
  const eligible = status?.analysis_eligible === true

  const at = stageIndex(analysis?.stage)
  const failed = analysis?.status === 'failed' || (props.analysisError !== null && !starting)
  const completed = analysis?.status === 'completed'
  const started = running || failed || completed

  /** A step is failed if the run stopped inside it, otherwise positional. */
  const positional = (from: number, to: number): StepState => {
    if (!started) return 'pending'
    if (failed) {
      if (at >= from && at <= to) return 'failed'
      return at > to ? 'done' : 'pending'
    }
    if (completed || at > to) return 'done'
    if (at >= from) return 'active'
    return 'pending'
  }

  const extractState: StepState =
    extracting || coverage === 'processing'
      ? 'active'
      : coverage === 'failed' || (extractError !== null && !extracted)
        ? 'failed'
        : extracted
          ? 'done'
          : 'pending'

  const coverageState: StepState = !extracted ? 'pending' : eligible ? 'done' : 'failed'

  // The run re-validates the document before it analyses it, so every stage
  // up to the model call belongs to this step.
  const analysisState = positional(0, 5)
  const verifyState = positional(6, 6)

  const resultsState: StepState = completed
    ? 'done'
    : failed
      ? 'failed'
      : started && at >= 7
        ? 'active'
        : 'pending'

  return [
    {
      key: 'uploaded',
      label: 'Document uploaded',
      state: 'done',
      detail: document.source_repaired ? 'Uploaded (repaired PDF)' : 'PDF accepted',
    },
    {
      key: 'extract',
      label: 'Extracting text',
      state: extractState,
      detail:
        extractState === 'active'
          ? 'Reading every page…'
          : extractState === 'failed'
            ? 'Pages could not be read'
            : extractState === 'done' && status
              ? `${status.processed_pages}/${status.expected_pages} pages read`
              : 'Waiting',
    },
    {
      key: 'coverage',
      label: 'Checking document coverage',
      state: coverageState,
      detail:
        coverageState === 'done'
          ? 'Every page accounted for'
          : coverageState === 'failed'
            ? coverage === 'blocked_repaired'
              ? 'Cannot be confirmed — analysis blocked'
              : coverage === 'failed'
                ? 'Could not be checked — analysis blocked'
                : 'Incomplete — analysis blocked'
            : 'Waiting',
    },
    {
      key: 'analysis',
      label: 'Analyzing clauses',
      state: analysisState,
      detail:
        analysisState === 'active'
          ? starting && !analysis
            ? 'Starting…'
            : (STAGE_DETAIL[analysis?.stage ?? 'queued'] ?? 'Analysing the document…')
          : analysisState === 'done'
            ? 'Document analysed'
            : analysisState === 'failed'
              ? 'Analysis stopped'
              : 'Waiting',
    },
    {
      key: 'verification',
      label: 'Verifying evidence',
      state: verifyState,
      detail:
        verifyState === 'active'
          ? 'Checking each statement against the text…'
          : verifyState === 'done'
            ? 'Evidence checked'
            : verifyState === 'failed'
              ? 'Verification stopped'
              : 'Waiting',
    },
    {
      key: 'results',
      label: 'Preparing results',
      state: resultsState,
      detail:
        resultsState === 'done'
          ? props.result
            ? `${props.result.findings.length} verified · ${props.result.withheld.total} withheld`
            : `${analysis?.verified_count ?? 0} verified · ${analysis?.withheld_count ?? 0} withheld`
          : resultsState === 'failed'
            ? 'Not available'
            : resultsState === 'active'
              ? 'Applying the output safety gate…'
              : 'Waiting',
    },
  ]
}

const MARKER: Record<StepState, string> = {
  done: 'border-emerald-600 bg-emerald-600 text-white',
  active: 'border-accent-600 bg-white text-accent-600',
  pending: 'border-slate-300 bg-white text-slate-300',
  failed: 'border-rose-600 bg-rose-600 text-white',
}

const DETAIL_TONE: Record<StepState, string> = {
  done: 'text-emerald-800',
  active: 'text-accent-700',
  pending: 'text-slate-500',
  failed: 'text-rose-700',
}

function Marker({ state }: { state: StepState }) {
  return (
    <span
      aria-hidden="true"
      className={`relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full border-2 ${MARKER[state]}`}
    >
      {state === 'done' && (
        <svg viewBox="0 0 16 16" className="size-3" fill="none" stroke="currentColor" strokeWidth={2.5}>
          <path d="M3.5 8.5l3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      {state === 'failed' && (
        <svg viewBox="0 0 16 16" className="size-3" fill="none" stroke="currentColor" strokeWidth={2.5}>
          <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" strokeLinecap="round" />
        </svg>
      )}
      {state === 'active' && (
        <span className="size-2 rounded-full bg-accent-600 motion-safe:animate-pulse" />
      )}
    </span>
  )
}

/**
 * The document's journey, as named steps rather than a spinner.
 *
 * Naming the real step matters for a call that takes the better part of a
 * minute: "Checking each statement against the text" tells the user what the
 * application is doing for them, and is the part of the product that a generic
 * "AI thinking…" would hide.
 */
export function AnalysisProgress(props: Props) {
  const steps = buildSteps(props)

  return (
    <div>
      <ol className="relative">
        {steps.map((step, index) => (
          <li
            key={step.key}
            aria-current={step.state === 'active' ? 'step' : undefined}
            className="relative flex gap-3 pb-4 last:pb-0"
          >
            {index < steps.length - 1 && (
              <span
                aria-hidden="true"
                className={`absolute top-6 bottom-0 left-[0.6875rem] w-0.5 ${
                  step.state === 'done' ? 'bg-emerald-600/40' : 'bg-slate-200'
                }`}
              />
            )}
            <Marker state={step.state} />
            <div className="flex min-w-0 flex-1 flex-col gap-x-4 sm:flex-row sm:items-baseline sm:justify-between">
              <span className="text-sm font-medium text-slate-900">
                <span className="sr-only">{STATE_TEXT[step.state]}: </span>
                {step.label}
              </span>
              <span className={`text-sm sm:text-right ${DETAIL_TONE[step.state]}`}>{step.detail}</span>
            </div>
          </li>
        ))}
      </ol>

      {props.reconnecting && (
        <p className="mt-4 flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <Icon name="alertTriangle" className="size-3.5" />
          Lost contact with the server &mdash; retrying. The analysis is still running.
        </p>
      )}
    </div>
  )
}
