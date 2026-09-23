import type { Tone } from './verdicts'
import type { AnalysisResult, CoverageStatus, StatusResponse } from '../types/api'

/**
 * Where the document is in its journey, derived only from backend state.
 *
 * One function, so the header, the overview and the tab empty states cannot
 * disagree about whether an analysis has run.
 */
export type Phase =
  | 'unread'
  | 'reading'
  | 'blocked'
  | 'ready'
  | 'running'
  | 'completed'
  | 'stopped'

export function documentPhase(input: {
  status: StatusResponse | null
  extracting: boolean
  running: boolean
  result: AnalysisResult | null
  error: string | null
}): Phase {
  const { status, extracting, running, result, error } = input
  if (extracting) return 'reading'
  if (running) return 'running'
  if (result) return 'completed'
  if (error) return 'stopped'
  if (!status || status.coverage_status === 'pending') return 'unread'
  if (!status.analysis_eligible) return 'blocked'
  return 'ready'
}

export const PHASE_LABEL: Record<Phase, { label: string; tone: Tone }> = {
  unread: { label: 'Not read yet', tone: 'neutral' },
  reading: { label: 'Reading pages…', tone: 'info' },
  blocked: { label: 'Analysis blocked', tone: 'partial' },
  ready: { label: 'Ready to analyse', tone: 'info' },
  running: { label: 'Analysing…', tone: 'info' },
  completed: { label: 'Results ready', tone: 'info' },
  stopped: { label: 'Stopped', tone: 'danger' },
}

export const COVERAGE_LABEL: Record<CoverageStatus, { label: string; tone: Tone }> = {
  complete: { label: 'Complete', tone: 'verified' },
  pending: { label: 'Not yet extracted', tone: 'neutral' },
  processing: { label: 'Extracting…', tone: 'neutral' },
  incomplete: { label: 'Incomplete', tone: 'partial' },
  blocked_repaired: { label: 'Cannot be confirmed', tone: 'partial' },
  failed: { label: 'Failed', tone: 'danger' },
}
