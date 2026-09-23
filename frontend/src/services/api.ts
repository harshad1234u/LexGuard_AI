import type {
  AnalysisStatusResponse,
  AnalyzeResponse,
  ApiErrorPayload,
  AskResponse,
  FindingsResponse,
  ExtractionResponse,
  StatusResponse,
  UploadResponse,
  ValuesResponse,
} from '../types/api'

const BASE = '/api/v1'

/** An error the backend described explicitly, carrying its stable code. */
export class ApiError extends Error {
  readonly code: string
  readonly details: Record<string, unknown>
  /** HTTP status, or 0 when the request never reached the server. */
  readonly status: number

  constructor(
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    status = 0,
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.details = details
    this.status = status
  }

  /**
   * Whether retrying the same request could plausibly succeed.
   *
   * A 404 or a 409 is the server's settled answer and retrying it only wastes
   * requests. A network drop or a 5xx from something in front of the API is
   * not an answer at all, and the work it describes may still be running.
   */
  get isTransient(): boolean {
    return this.status === 0 || this.status === 408 || this.status === 429 || this.status >= 500
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const payload = (await response.json()) as ApiErrorPayload
    if (payload?.error?.message) {
      return new ApiError(
        payload.error.code,
        payload.error.message,
        payload.error.details,
        response.status,
      )
    }
  } catch {
    // Fall through to the generic message below.
  }
  return new ApiError('unexpected_error', `Request failed (${response.status}).`, {}, response.status)
}

/** Wrap a transport failure so callers see one error type, never a raw TypeError. */
function toNetworkError(): ApiError {
  return new ApiError(
    'network_error',
    'The server could not be reached. Check your connection and try again.',
  )
}

async function request(input: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(input, init)
  } catch {
    throw toNetworkError()
  }
  if (!response.ok) throw await toApiError(response)
  return response
}

export async function uploadDocument(file: File, signal?: AbortSignal): Promise<UploadResponse> {
  const body = new FormData()
  body.append('file', file)

  const response = await request(`${BASE}/documents/upload`, { method: 'POST', body, signal })
  return (await response.json()) as UploadResponse
}

/** Run page-level extraction and return the manifest plus the coverage verdict. */
export async function extractDocument(documentId: string): Promise<ExtractionResponse> {
  const response = await request(`${BASE}/documents/${encodeURIComponent(documentId)}/extract`, {
    method: 'POST',
  })
  return (await response.json()) as ExtractionResponse
}

export async function getStatus(documentId: string): Promise<StatusResponse> {
  const response = await request(`${BASE}/documents/${encodeURIComponent(documentId)}/status`)
  return (await response.json()) as StatusResponse
}

/**
 * The deterministic value index for a document.
 *
 * No model is involved, so this succeeds while the provider is unavailable.
 * Rejected with 409 `coverage_incomplete` until every page has been read.
 */
export async function getValues(documentId: string): Promise<ValuesResponse> {
  const response = await request(`${BASE}/documents/${encodeURIComponent(documentId)}/values`)
  return (await response.json()) as ValuesResponse
}

export async function deleteDocument(documentId: string): Promise<void> {
  await request(`${BASE}/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' })
}

/** Start an analysis. Returns immediately; the model runs in the background. */
export async function startAnalysis(documentId: string): Promise<AnalyzeResponse> {
  const response = await request(`${BASE}/documents/${encodeURIComponent(documentId)}/analyze`, {
    method: 'POST',
  })
  return (await response.json()) as AnalyzeResponse
}

export async function getAnalysisStatus(analysisId: string): Promise<AnalysisStatusResponse> {
  const response = await request(`${BASE}/analysis/${encodeURIComponent(analysisId)}/status`)
  return (await response.json()) as AnalysisStatusResponse
}

export async function getFindings(documentId: string): Promise<FindingsResponse> {
  const response = await request(`${BASE}/documents/${encodeURIComponent(documentId)}/findings`)
  return (await response.json()) as FindingsResponse
}

/**
 * Ask a question about one uploaded document.
 *
 * Synchronous: the backend answers in the response rather than handing back a
 * job to poll, so this call can take tens of seconds while the model reads.
 */
export async function askDocument(
  documentId: string,
  question: string,
  signal?: AbortSignal,
): Promise<AskResponse> {
  const response = await request(`${BASE}/documents/${encodeURIComponent(documentId)}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
    signal,
  })
  return (await response.json()) as AskResponse
}
