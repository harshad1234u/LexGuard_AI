import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, askDocument } from '../services/api'
import type { AskResponse, LanguageCode } from '../types/api'

interface AskState {
  /** Which document this state belongs to, so a stale answer is never shown. */
  ownerId: string | null
  answer: AskResponse | null
  error: string | null
  asking: boolean
}

const EMPTY: AskState = { ownerId: null, answer: null, error: null, asking: false }

/**
 * Asks one question about one document.
 *
 * Deliberately not a chat: there is no history, no thread, no conversational
 * state. Each question is answered from the document alone, so carrying
 * earlier turns would add a second source of context the verifier cannot check.
 *
 * The request is synchronous and can take tens of seconds. It is abortable, and
 * an answer belonging to a previous document or a superseded question is
 * discarded rather than displayed.
 */
export function useAsk(documentId: string | null) {
  const [state, setState] = useState<AskState>(EMPTY)
  const controller = useRef<AbortController | null>(null)
  const runToken = useRef(0)

  // Abandon anything in flight when the document changes or the view unmounts.
  useEffect(() => {
    return () => {
      runToken.current += 1
      controller.current?.abort()
      controller.current = null
    }
  }, [documentId])

  const ask = useCallback(
    async (question: string, language: LanguageCode = 'en') => {
      if (!documentId || !question.trim()) return

      // A second question supersedes the first rather than racing it.
      controller.current?.abort()
      const request = new AbortController()
      controller.current = request

      const token = ++runToken.current
      const live = () => runToken.current === token
      setState({ ownerId: documentId, answer: null, error: null, asking: true })

      try {
        const answer = await askDocument(documentId, question.trim(), request.signal, language)
        if (!live()) return
        setState({ ownerId: documentId, answer, error: null, asking: false })
      } catch (cause) {
        if (!live()) return
        setState({
          ownerId: documentId,
          answer: null,
          // The backend writes its messages for a non-technical reader.
          error:
            cause instanceof ApiError
              ? cause.message
              : 'The question could not be answered just now.',
          asking: false,
        })
      }
    },
    [documentId],
  )

  const reset = useCallback(() => {
    runToken.current += 1
    controller.current?.abort()
    setState(EMPTY)
  }, [])

  // Anything belonging to a previous document is not ours to show.
  const current = state.ownerId === documentId ? state : EMPTY

  return { ask, reset, answer: current.answer, error: current.error, asking: current.asking }
}
