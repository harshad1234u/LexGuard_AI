import { BRAND } from '../../config/brand'
import { useUpload } from '../../hooks/useUpload'
import { COVERAGE_LABEL, PHASE_LABEL, type Phase } from '../../lib/phase'
import { TONE_CLASSES } from '../../lib/verdicts'
import type { StatusResponse, UploadResponse } from '../../types/api'
import { Icon } from '../ui/Icon'
import { ErrorState } from '../ui/StatusBanner'

interface Props {
  document: UploadResponse | null
  status: StatusResponse | null
  phase: Phase
  onDiscard: () => void
  /** A new upload succeeded. The caller retires the current document. */
  onReplace: (next: UploadResponse) => void
}

function Wordmark() {
  return (
    <div className="flex shrink-0 items-center gap-2">
      <span className="flex size-8 items-center justify-center rounded-md bg-navy-900 text-white">
        <Icon name="shieldCheck" className="size-[1.125rem]" />
      </span>
      <span className="font-display text-[0.9375rem] font-semibold tracking-tight text-navy-950">
        {BRAND.name}
      </span>
    </div>
  )
}

/**
 * A labelled status in the header.
 *
 * The label and the value are separate elements, and the label is short, so
 * the header never repeats a sentence the page itself uses to report the same
 * state in full.
 */
function HeaderStatus({
  label,
  value,
  tone,
  busy = false,
}: {
  label: string
  value: string
  tone: keyof typeof TONE_CLASSES
  busy?: boolean
}) {
  return (
    <div className="flex shrink-0 items-center gap-2 text-xs">
      <span className="font-medium text-slate-500">{label}</span>
      <span
        className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 font-semibold ${TONE_CLASSES[tone]}`}
      >
        {busy && <Icon name="loader" className="size-3 animate-spin motion-reduce:animate-none" />}
        {value}
      </span>
    </div>
  )
}

/**
 * The persistent header: brand, the open document, and its two statuses.
 *
 * Status is read from the backend's own fields. Nothing here claims an account,
 * a session or a user - the application has none.
 */
export function TopNavigation({ document, status, phase, onDiscard, onReplace }: Props) {
  const { submit, busy, error: uploadError, clearError, inputRef } = useUpload(onReplace)
  const coverage = status ? COVERAGE_LABEL[status.coverage_status] : COVERAGE_LABEL.pending
  const pages =
    status && status.coverage_status !== 'pending'
      ? ` · ${status.processed_pages}/${status.expected_pages} pages`
      : ''
  const analysis = PHASE_LABEL[phase]

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-[90rem] flex-wrap items-center gap-x-5 gap-y-3 px-4 py-3 sm:px-6 lg:flex-nowrap lg:px-8">
        <Wordmark />

        {document && (
          <>
            <div className="order-3 flex w-full min-w-0 flex-wrap items-center gap-x-5 gap-y-2 lg:order-none lg:w-auto lg:flex-1 lg:flex-nowrap lg:border-l lg:border-slate-200 lg:pl-5">
              {/* The filename is user-supplied: rendered as text, never markup. */}
              <div className="flex w-full min-w-0 items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 sm:w-auto sm:max-w-full lg:shrink">
                <Icon name="file" className="size-4 text-rose-700" />
                <span
                  className="min-w-0 flex-1 truncate font-mono text-xs font-medium text-slate-800 sm:max-w-[18rem] xl:max-w-[26rem]"
                  title={document.filename}
                >
                  {document.filename}
                </span>
                <span className="shrink-0 font-mono text-[0.6875rem] text-slate-500">
                  {document.page_count} {document.page_count === 1 ? 'pg' : 'pgs'}
                </span>
              </div>
              <HeaderStatus label="Coverage" value={`${coverage.label}${pages}`} tone={coverage.tone} />
              <HeaderStatus
                label="Analysis"
                value={analysis.label}
                tone={analysis.tone}
                busy={phase === 'running' || phase === 'reading'}
              />
            </div>

            <div className="ml-auto flex shrink-0 items-center gap-1 lg:ml-0">
              <label
                className={`inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-md px-3 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent-600 ${
                  busy ? 'cursor-not-allowed opacity-60' : ''
                }`}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  disabled={busy}
                  className="sr-only"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) void submit(file)
                  }}
                />
                <Icon
                  name={busy ? 'loader' : 'upload'}
                  className={`size-4 ${busy ? 'animate-spin motion-reduce:animate-none' : ''}`}
                />
                <span className="sr-only sm:not-sr-only">
                  {busy ? 'Uploading…' : 'Upload new document'}
                </span>
              </label>
              <button
                type="button"
                onClick={onDiscard}
                className="inline-flex min-h-10 items-center gap-2 rounded-md px-3 text-sm font-medium text-slate-700 transition-colors hover:bg-rose-50 hover:text-rose-700"
              >
                <Icon name="trash" className="size-4" />
                <span className="sr-only sm:not-sr-only">Discard document</span>
              </button>
            </div>
          </>
        )}

        {!document && (
          <p className="ml-auto hidden text-xs text-slate-500 sm:block">{BRAND.descriptor}</p>
        )}
      </div>

      {uploadError && (
        <div className="mx-auto max-w-[90rem] px-4 pb-3 sm:px-6 lg:px-8">
          <ErrorState title="The new document could not be uploaded">
            <p>{uploadError}</p>
            <p className="mt-1 text-xs">Your current document is unchanged.</p>
            <button
              type="button"
              onClick={clearError}
              className="mt-2 text-xs font-semibold underline underline-offset-2"
            >
              Dismiss
            </button>
          </ErrorState>
        </div>
      )}
    </header>
  )
}
