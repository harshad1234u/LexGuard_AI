import { useEffect, useState } from 'react'

import { ApiError, getValues } from '../services/api'
import type { DocumentValue, ValuesExtraction } from '../types/api'

interface State {
  /** The document this state describes, so a stale response cannot be shown. */
  documentId: string
  values: DocumentValue[] | null
  /** What the backend says it read. Decides which empty state is honest. */
  extraction: ValuesExtraction | null
  error: string | null
  loading: boolean
}

const initial = (documentId: string): State => ({
  documentId,
  values: null,
  extraction: null,
  error: null,
  loading: true,
})

/**
 * The deterministic value index for one document.
 *
 * Lifted out of the values view so the overview and the values tab share one
 * request. Fetched only once the backend says the document was fully read -
 * the endpoint refuses anything else - and never involves the model, so it
 * works while the provider is unavailable.
 */
export function useValues(documentId: string, eligible: boolean) {
  const [state, setState] = useState<State>(() => initial(documentId))

  // Reset during render rather than in an effect. A new document must not show
  // the previous one's values for a frame.
  if (state.documentId !== documentId) setState(initial(documentId))

  useEffect(() => {
    if (!eligible) return

    let cancelled = false

    getValues(documentId)
      .then((response) => {
        if (cancelled) return
        setState({
          documentId,
          values: response.values,
          extraction: response.extraction,
          error: null,
          loading: false,
        })
      })
      .catch((cause: unknown) => {
        if (cancelled) return
        setState({
          documentId,
          values: null,
          extraction: null,
          error: cause instanceof ApiError ? cause.message : 'The values could not be read.',
          loading: false,
        })
      })

    return () => {
      cancelled = true
    }
  }, [documentId, eligible])

  const current = state.documentId === documentId ? state : initial(documentId)
  return { ...current, eligible }
}

export type ValuesState = ReturnType<typeof useValues>
