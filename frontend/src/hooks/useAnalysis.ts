import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, getAnalysisStatus, getFindings, startAnalysis } from '../services/api'
import type { AnalysisResult, AnalysisStatusResponse, DocumentOverview } from '../types/api'

const POLL_INTERVAL_MS = 1500

/**
 * How many consecutive transient failures to absorb before giving up.
 *
 * A dropped connection or a 502 from something in front of the API says
 * nothing about the analysis, which is running server-side and will finish
 * regardless. Reporting failure on the first blip would tell the user their
 * analysis died when it did not. Six attempts spans roughly half a minute of
 * backoff, after which a fault is real enough to report.
 */
const MAX_CONSECUTIVE_FAILURES = 6

/**
 * An upper bound on one poll loop, well past the server's own 900s budget.
 *
 * The server always reaches a terminal state on its own, so this exists only
 * so a bug upstream cannot leave a browser tab polling forever.
 */
const MAX_POLL_MS = 20 * 60 * 1000

interface AnalysisState {
  /** Which document this state belongs to, so a stale result is never shown. */
  ownerId: string | null
  status: AnalysisStatusResponse | null
  result: AnalysisResult | null
  /**
   * The findings endpoint's own grouping of `result`. Held beside the result
   * rather than derived here: grouping is a decision about what is published,
   * and the backend makes it. Null whenever the result is.
   */
  overview: DocumentOverview | null
  error: string | null
  starting: boolean
  /** True while polling is retrying through a transport fault. */
  reconnecting: boolean
}

const EMPTY: AnalysisState = {
  ownerId: null,
  status: null,
  result: null,
  overview: null,
  error: null,
  starting: false,
  reconnecting: false,
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

const message = (cause: unknown, fallback: string) =>
  cause instanceof ApiError ? cause.message : fallback

/**
 * Starts an analysis and polls until it settles.
 *
 * Analysis is asynchronous because a real model call takes tens of seconds, so
 * there is nothing to await here - the hook reports each stage as the backend
 * reaches it.
 *
 * State carries the document it belongs to and is discarded during render when
 * that no longer matches, rather than being cleared by an effect. A result for
 * one document must never be displayed against another.
 *
 * Starting is always a deliberate user action. Nothing here runs from an
 * effect, so a re-render cannot buy an inference.
 */
export function useAnalysis(documentId: string | null) {
  const [state, setState] = useState<AnalysisState>(EMPTY)
  const runToken = useRef(0)
  /**
   * Guards the gap between a click and the re-render that disables the button.
   * React batches state updates, so a fast double-click would otherwise send
   * two POSTs. The backend refuses to run the second, but not sending it is
   * better than relying on that.
   */
  const inFlight = useRef(false)

  // Cancel any in-flight poll when the document changes or the view unmounts.
  useEffect(() => {
    return () => {
      runToken.current += 1
      inFlight.current = false
    }
  }, [documentId])

  const run = useCallback(async (documentId: string) => {
    const token = ++runToken.current
    const live = () => runToken.current === token
    setState({ ...EMPTY, ownerId: documentId, starting: true })

    let started
    try {
      started = await startAnalysis(documentId)
    } catch (cause) {
      if (!live()) return
      setState({
        ...EMPTY,
        ownerId: documentId,
        error: message(cause, 'The analysis could not be started.'),
      })
      return
    }
    if (!live()) return

    // Poll as a loop: no recursive callback, no timer to leak.
    const deadline = Date.now() + MAX_POLL_MS
    let failures = 0

    for (;;) {
      if (Date.now() > deadline) {
        setState((previous) => ({
          ...previous,
          starting: false,
          reconnecting: false,
          error: 'The analysis is taking longer than expected. Please try again.',
        }))
        return
      }

      let status: AnalysisStatusResponse
      try {
        status = await getAnalysisStatus(started.analysis_id)
        failures = 0
      } catch (cause) {
        if (!live()) return

        // A settled answer - the analysis was discarded, say - is final.
        // Anything else may just be the network, and the run continues.
        const transient = cause instanceof ApiError && cause.isTransient
        failures += 1
        if (!transient || failures >= MAX_CONSECUTIVE_FAILURES) {
          setState((previous) => ({
            ...previous,
            starting: false,
            reconnecting: false,
            error: message(cause, 'The analysis could not be completed.'),
          }))
          return
        }

        setState((previous) => ({ ...previous, starting: false, reconnecting: true }))
        // Back off, so a struggling server is not hammered while it recovers.
        await sleep(POLL_INTERVAL_MS * failures)
        if (!live()) return
        continue
      }
      if (!live()) return

      if (status.status === 'completed') {
        // Findings come from the findings endpoint, never inferred from the
        // status response: the gated result is the backend's to publish.
        try {
          const findings = await getFindings(documentId)
          if (!live()) return
          setState({
            ownerId: documentId,
            status,
            result: findings.result,
            overview: findings.overview,
            error: null,
            starting: false,
            reconnecting: false,
          })
        } catch (cause) {
          if (!live()) return
          setState({
            ...EMPTY,
            ownerId: documentId,
            status,
            error: message(cause, 'The findings could not be retrieved.'),
          })
        }
        return
      }

      if (status.status === 'failed') {
        setState({
          ...EMPTY,
          ownerId: documentId,
          status,
          error: status.error_message ?? 'The analysis could not be completed.',
        })
        return
      }

      setState((previous) => ({
        ...previous,
        status,
        starting: false,
        reconnecting: false,
      }))
      await sleep(POLL_INTERVAL_MS)
      if (!live()) return
    }
  }, [])

  const analyze = useCallback(async () => {
    if (!documentId || inFlight.current) return
    inFlight.current = true
    try {
      await run(documentId)
    } finally {
      inFlight.current = false
    }
  }, [documentId, run])

  // Anything belonging to a previous document is not ours to show.
  const current = state.ownerId === documentId ? state : EMPTY
  const running =
    current.starting ||
    current.reconnecting ||
    current.status?.status === 'queued' ||
    current.status?.status === 'running'

  return {
    analyze,
    status: current.status,
    result: current.result,
    overview: current.overview,
    error: current.error,
    running,
    starting: current.starting,
    reconnecting: current.reconnecting,
  }
}
