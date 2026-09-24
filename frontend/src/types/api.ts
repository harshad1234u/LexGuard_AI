/** Mirrors backend/app/schemas/documents.py and docs/07_API_SPEC.md. */

/**
 * Every value the backend's `DocumentStatus` enum declares.
 *
 * Only the first four are produced by the document endpoints today:
 * `validated`, `extracting`, `ingested`, `ingestion_failed`. The rest belong
 * to the later half of the workflow machine in docs/02_ARCHITECTURE.md §4,
 * which from Phase 7 is owned by the analysis resource and reported through
 * `AnalysisStatus` / `AnalysisStage` instead. Nothing in this app branches on
 * them; the union exists so a response can be typed without widening.
 */
export type DocumentStatus =
  | 'uploaded'
  | 'validated'
  | 'extracting'
  | 'ingested'
  | 'coverage_verified'
  | 'analyzing'
  | 'analyzed'
  | 'evidence_verified'
  | 'output_validated'
  | 'ready'
  | 'validation_failed'
  | 'ingestion_failed'
  | 'incomplete_document'
  | 'evidence_mismatch'
  | 'output_rejected'

export type CoverageStatus =
  | 'pending'
  | 'processing'
  | 'complete'
  | 'incomplete'
  | 'failed'
  | 'blocked_repaired'

export type PageStatus = 'processed' | 'empty' | 'unreadable' | 'failed'

export interface UploadResponse {
  document_id: string
  filename: string
  page_count: number
  size_bytes: number
  content_type: string
  status: DocumentStatus
  source_repaired: boolean
}

export interface StatusResponse {
  document_id: string
  status: DocumentStatus
  expected_pages: number
  processed_pages: number
  failed_pages: number[]
  unreadable_pages: number[]
  coverage_status: CoverageStatus
  coverage_explanation: string
  /** False blocks a complete-document analysis outright. */
  analysis_eligible: boolean
  source_repaired: boolean
}

export interface PageRecord {
  page_number: number
  status: PageStatus
  text_length: number
  image_count: number
  failure_reason: string | null
}

export interface DocumentManifest {
  document_id: string
  total_pages: number
  is_repaired: boolean
  extraction_method: string
  pages: PageRecord[]
}

export interface CoverageReport {
  status: CoverageStatus
  expected_pages: number
  processed_pages: number
  failed_pages: number[]
  unreadable_pages: number[]
  blocking_reasons: string[]
}

export interface ExtractionResponse {
  document_id: string
  status: DocumentStatus
  manifest: DocumentManifest
  coverage: CoverageReport
}

export interface ApiErrorPayload {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
  }
}

// --- Analysis (Phase 7) ---

export type AnalysisStatus = 'queued' | 'running' | 'completed' | 'failed'

export type AnalysisStage =
  | 'queued'
  | 'validating'
  | 'ingesting'
  | 'checking_coverage'
  | 'building_document_map'
  | 'analyzing'
  | 'verifying'
  | 'gating_output'
  | 'done'

export type VerificationStatus =
  | 'verified'
  | 'partially_verified'
  | 'rejected'
  | 'unverified'

export type AttentionLevel = 'info' | 'review' | 'high'

/**
 * A reader's language (Phase 23). Only translations follow it: claims, quotes
 * and the checked explanation or answer stay in the document's own language.
 */
export type LanguageCode = 'en' | 'ta'

/** Which providers produced a result, and which release rules applied. */
export interface Provenance {
  provider: string
  model: string
  /** Null when reasoning did not run. Always null on answers. */
  reasoning_provider: string | null
  reasoning_model: string | null
  verification_policy_version: string
  status: string
}

export type ReasoningStatus = 'completed' | 'disabled' | 'skipped' | 'unavailable' | 'failed'

/**
 * A model's observation relating released findings. Interpretation, never a
 * verified fact: there is deliberately no verification status on it.
 * `evidence_checked` says only that its quotes are real text from the findings
 * it cites. `label` is set by the backend and is always displayed.
 */
export interface ReasoningNoteOut {
  id: string
  category: string
  text: string
  finding_ids: string[]
  quotes: string[]
  evidence_checked: boolean
  label: string
}

export interface ReasoningResult {
  status: ReasoningStatus
  failure_kind: string | null
  provider: string | null
  notes: ReasoningNoteOut[]
  withheld_count: number
}

export interface EvidenceRef {
  page: number
  quote: string
  section: string | null
}

/** Only findings that passed the output gate are ever returned in `findings`. */
export interface VerifiedFindingOut {
  id: string
  type: string
  /** Verified against the document, claim by claim. */
  claim: string
  /**
   * `section` is present only when the cited page carries that exact label.
   * An unconfirmable citation is dropped by the backend rather than shown.
   */
  evidence: EvidenceRef
  explanation: string
  /**
   * Whether the quoted text establishes the explanation, as opposed to merely
   * not contradicting it. Usually false: an explanation is interpretation.
   * When false the UI must label it as such and never present it as a verified
   * fact about the document.
   */
  explanation_verified: boolean
  /**
   * Derived by the backend from what the quoted text contains - a prohibition,
   * an obligation, a sum, a deadline. Never supplied by the model, and not a
   * legal risk assessment.
   */
  attention: AttentionLevel
  verification_status: VerificationStatus
  /**
   * The explanation in the reader's requested language. NOT independently
   * checked; present only beside a verified explanation. Always labelled.
   */
  explanation_translation?: string | null
  explanation_translation_language?: LanguageCode | null
}

/**
 * Kinds of value the backend can locate deterministically.
 *
 * A kind says what sort of token was found, never what it means. Nothing here
 * implies a value is a deadline, an obligation or a risk - establishing that
 * is interpretation, and interpretation belongs to the findings path.
 */
export type ValueKind = 'currency' | 'percentage' | 'duration' | 'date'

/** One value located in the document, bound to the page it appears on. */
export interface DocumentValue {
  kind: ValueKind
  /** The value as the document writes it. Never paraphrased, never resolved. */
  value: string
  page: number
  /**
   * Dates only. True when the written form has more than one reading, in which
   * case it is shown as written and no calendar meaning is assigned.
   */
  ambiguous: boolean
}

/**
 * Response for GET /documents/{id}/values.
 *
 * A deterministic index of the document's own text. No model is involved, so
 * nothing here is a claim - and nothing here is a summary or a risk
 * assessment. An empty `values` list means none were detected, not that the
 * document contains none.
 */
/**
 * How much text the application actually read, as counts only.
 *
 * Lets an empty `values` list be explained instead of merely reported: a
 * document read in full that states no amounts is not the same as one from
 * which no text could be recovered, and the panel must not tell a reader the
 * second is the first.
 */
export interface ValuesExtraction {
  characters: number
  pages_with_text: number
  pages_total: number
}

export interface ValuesResponse {
  document_id: string
  coverage_status: string
  extraction: ValuesExtraction
  values: DocumentValue[]
}

export interface WithheldSummary {
  total: number
  rejected: number
  unverified: number
  partially_verified: number
}

export interface CoverageSummary {
  status: string
  expected_pages: number
  processed_pages: number
  failed_pages: number[]
  unreadable_pages: number[]
  source_repaired: boolean
}

export interface AnalysisResult {
  findings: VerifiedFindingOut[]
  withheld: WithheldSummary
  proposed_count: number
  insufficient_evidence: boolean
  coverage: CoverageSummary | null
  language?: LanguageCode
  provenance?: Provenance | null
  reasoning?: ReasoningResult | null
}

export interface AnalyzeResponse {
  analysis_id: string
  document_id: string
  status: AnalysisStatus
  stage: AnalysisStage
  created_at: string
  reused: boolean
}

export interface AnalysisStatusResponse {
  analysis_id: string
  document_id: string
  status: AnalysisStatus
  stage: AnalysisStage
  created_at: string
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  coverage: CoverageSummary | null
  proposed_count: number | null
  verified_count: number | null
  withheld_count: number | null
  error_category: string | null
  error_message: string | null
}

// --- Document overview (Phase 21) ---

/**
 * The closed set of topics the backend groups released findings under.
 *
 * Closed on the backend, and mirrored here as a union so an unexpected value
 * is a type error rather than an unlabelled heading. The model cannot add to
 * this set: it chooses a finding's free-form `type`, and the application maps
 * that onto one of these.
 */
export type OverviewCategory =
  | 'parties_roles'
  | 'fees_payments'
  | 'term_renewal'
  | 'termination'
  | 'confidentiality'
  | 'liability'
  | 'notices'
  | 'governing_law'
  | 'other'

/**
 * One released finding, as the overview refers to it.
 *
 * Every field is already present on a `VerifiedFindingOut` in the same
 * response. `explanation` and `attention` are deliberately absent from this
 * shape: the explanation is interpretation and carries its own label on the
 * finding card, and `attention` is not a risk assessment and is not rendered.
 */
export interface OverviewItem {
  finding_id: string
  claim: string
  quote: string
  page: number
  section: string | null
  /** The finding's own category label, kept so an `other` item still says what it is. */
  label: string
}

export interface OverviewCategoryGroup {
  key: OverviewCategory
  label: string
  items: OverviewItem[]
  /**
   * Present only when `items` is empty. The backend's own wording, which says
   * nothing was released for the topic and never that the document lacks it.
   * Displayed as given — the frontend does not write this sentence.
   */
  empty_message: string | null
}

export interface DocumentOverview {
  categories: OverviewCategoryGroup[]
  released_count: number
  proposed_count: number
  withheld_count: number
}

export interface FindingsResponse {
  document_id: string
  analysis_id: string
  status: AnalysisStatus
  result: AnalysisResult
  overview: DocumentOverview
}

// --- Document-grounded Q&A (Phase 9) ---

/**
 * How well the uploaded document supports the answer.
 *
 * A support level, not a confidence score — the backend has no calibrated
 * basis for a probability and does not imply one. Coverage refusals and
 * provider failures are not values here: they arrive as HTTP errors carrying
 * the standard `ApiErrorPayload` envelope.
 */
export type AnswerStatus = 'supported' | 'partially_supported' | 'not_found'

export interface AnswerEvidence {
  quote: string
  page: number
  section: string | null
  /** The backend's deterministic verdict, never the model's claim about itself. */
  verification_status: VerificationStatus
  /** Plain-language caveat, present when the status is not `verified`. */
  note: string
}

export interface AskResponse {
  document_id: string
  question: string
  answer: string
  status: AnswerStatus
  evidence: AnswerEvidence[]
  /** Quotes the verifier could not place in the document. Text is never returned. */
  withheld_evidence: number
  /** Statements the answer made, each checked against its evidence separately. */
  claims_checked: number
  /** Statements dropped because the evidence did not establish them. */
  claims_withheld: number
  /** Not independently checked; present only when the answer held up in full. */
  answer_translation?: string | null
  answer_translation_language?: LanguageCode | null
  provenance?: Provenance | null
  disclaimer: string
}
