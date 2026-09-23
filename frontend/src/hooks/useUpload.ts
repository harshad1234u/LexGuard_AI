import { useCallback, useRef, useState } from 'react'

import { ApiError, uploadDocument } from '../services/api'
import type { UploadResponse } from '../types/api'

/**
 * One upload at a time, with the backend's own refusal message on failure.
 *
 * Validation is the backend's: the file type, the size and the page limit are
 * all checked there, and its message is already written for a non-technical
 * reader. The `accept` attribute on the input is a convenience, not the check.
 */
export function useUpload(onUploaded: (document: UploadResponse) => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const submit = useCallback(
    async (file: File) => {
      setError(null)
      setBusy(true)
      try {
        onUploaded(await uploadDocument(file))
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : 'The upload could not be completed.')
      } finally {
        setBusy(false)
        if (inputRef.current) inputRef.current.value = ''
      }
    },
    [onUploaded],
  )

  const clearError = useCallback(() => setError(null), [])

  return { submit, busy, error, clearError, inputRef }
}
