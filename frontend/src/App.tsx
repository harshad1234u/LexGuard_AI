import { useCallback, useEffect, useState } from 'react'

import { AppShell } from './components/shell/AppShell'
import { DocumentWorkspace } from './components/shell/DocumentWorkspace'
import { TopNavigation } from './components/shell/TopNavigation'
import { UploadView } from './components/upload/UploadView'
import { BRAND } from './config/brand'
import { useAnalysis } from './hooks/useAnalysis'
import { documentPhase } from './lib/phase'
import { ApiError, deleteDocument, extractDocument, getStatus } from './services/api'
import type { StatusResponse, UploadResponse } from './types/api'

export default function App() {
  const [document, setDocument] = useState<UploadResponse | null>(null)
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [extracting, setExtracting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const analysis = useAnalysis(document?.document_id ?? null)

  // Status is cleared by whichever event replaced the document, so the effect
  // only ever has to fetch.
  useEffect(() => {
    if (!document) return
    let cancelled = false
    getStatus(document.document_id)
      .then((next) => {
        if (!cancelled) setStatus(next)
      })
      .catch(() => {
        if (!cancelled) setStatus(null)
      })
    return () => {
      cancelled = true
    }
  }, [document])

  // The filename is the page's subject once there is one. Set as text, never markup.
  useEffect(() => {
    window.document.title = document ? `${document.filename} · ${BRAND.name}` : BRAND.name
  }, [document])

  const accept = useCallback((next: UploadResponse) => {
    setStatus(null)
    setError(null)
    setDocument(next)
  }, [])

  const extract = useCallback(async () => {
    if (!document) return
    setExtracting(true)
    setError(null)
    try {
      await extractDocument(document.document_id)
      // Re-read status so the displayed coverage comes from the same source of
      // truth the rest of the app uses.
      setStatus(await getStatus(document.document_id))
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The document could not be read.')
    } finally {
      setExtracting(false)
    }
  }, [document])

  const discard = useCallback(() => {
    if (document) void deleteDocument(document.document_id).catch(() => undefined)
    setStatus(null)
    setError(null)
    setDocument(null)
  }, [document])

  /**
   * A second upload from inside the workspace. The previous document is
   * deleted only once the new one has been accepted, so a refused upload
   * leaves the user exactly where they were.
   */
  const replace = useCallback(
    (next: UploadResponse) => {
      if (document) void deleteDocument(document.document_id).catch(() => undefined)
      accept(next)
    },
    [document, accept],
  )

  const phase = documentPhase({
    status,
    extracting,
    running: analysis.running,
    result: analysis.result,
    error: analysis.error,
  })

  return (
    <AppShell
      header={
        <TopNavigation
          document={document}
          status={status}
          phase={phase}
          onDiscard={discard}
          onReplace={replace}
        />
      }
    >
      {document ? (
        // Keyed by document: every view's local state - a selection, a filter,
        // a question in flight - belongs to one document and is discarded with it.
        <DocumentWorkspace
          key={document.document_id}
          document={document}
          status={status}
          phase={phase}
          extracting={extracting}
          extractError={error}
          analysis={analysis}
          onExtract={() => void extract()}
        />
      ) : (
        <UploadView onUploaded={accept} />
      )}
    </AppShell>
  )
}
