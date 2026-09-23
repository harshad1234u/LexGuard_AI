import { useState } from 'react'

import { BRAND } from '../../config/brand'
import { useUpload } from '../../hooks/useUpload'
import type { UploadResponse } from '../../types/api'
import { Icon, type IconName } from '../ui/Icon'
import { ErrorState } from '../ui/StatusBanner'

/**
 * What the product does, in the order it does it. Each line describes a
 * mechanism the backend actually runs - nothing here is a promise about the
 * quality of the result.
 */
const STEPS: { icon: IconName; title: string; body: string }[] = [
  {
    icon: 'file',
    title: 'Every page is read and counted',
    body: 'Analysis is offered only when the whole document could be read.',
  },
  {
    icon: 'shieldCheck',
    title: 'Every finding is checked against the text',
    body: 'The model proposes; the application verifies each quote on the page it cites.',
  },
  {
    icon: 'ban',
    title: 'Anything unconfirmed is withheld',
    body: 'A statement the document does not support is counted, never shown.',
  },
]

/** The landing state: nothing uploaded yet. */
export function UploadView({ onUploaded }: { onUploaded: (document: UploadResponse) => void }) {
  const { submit, busy, error, inputRef } = useUpload(onUploaded)
  const [dragging, setDragging] = useState(false)

  return (
    <div className="mx-auto grid max-w-6xl gap-10 px-4 py-10 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)] lg:gap-16 lg:py-20">
      <div className="flex flex-col justify-center">
        <p className="font-mono text-xs font-semibold tracking-wider text-accent-700 uppercase">
          {BRAND.descriptor.replace(/\.$/, '')}
        </p>
        <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight text-navy-950 sm:text-4xl lg:text-[2.75rem] lg:leading-[1.15]">
          {BRAND.tagline}
        </h1>
        <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-600">
          Upload a legal document to review its clauses, values and dates, and to ask questions
          answered from its own text. The AI interprets the document; {BRAND.name} verifies the
          evidence before anything is shown to you.
        </p>

        <ul className="mt-8 grid gap-4 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
          {STEPS.map((step) => (
            <li key={step.title} className="flex gap-3 lg:max-w-md xl:block">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-navy-900">
                <Icon name={step.icon} className="size-[1.125rem]" />
              </span>
              <div className="xl:mt-3">
                <p className="text-sm font-semibold text-slate-900">{step.title}</p>
                <p className="mt-0.5 text-sm leading-snug text-slate-600">{step.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <section aria-labelledby="upload-heading" className="flex flex-col justify-center">
        <div
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            const file = event.dataTransfer.files?.[0]
            if (file) void submit(file)
          }}
          className={`rounded-xl border bg-white p-6 shadow-[0_1px_2px_0_rgb(15_23_42/0.04)] transition-colors sm:p-8 ${
            dragging ? 'border-accent-600 ring-4 ring-accent-100' : 'border-slate-200'
          }`}
        >
          <h2 id="upload-heading" className="font-display text-xl font-semibold text-slate-900">
            Upload a legal document
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            A contract, agreement, notice or policy, as a PDF.
          </p>

          <div
            className={`mt-6 flex flex-col items-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors ${
              dragging ? 'border-accent-600 bg-accent-50' : 'border-slate-300 bg-slate-50'
            }`}
          >
            <span className="flex size-11 items-center justify-center rounded-full bg-white text-navy-900 shadow-sm ring-1 ring-slate-200">
              <Icon name="upload" className="size-5" />
            </span>

            <label className="mt-4 inline-block">
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf,.pdf"
                disabled={busy}
                className="peer sr-only"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file) void submit(file)
                }}
              />
              <span
                className={`inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-5 text-sm font-medium text-white transition-colors peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent-600 ${
                  busy ? 'cursor-not-allowed bg-slate-400' : 'bg-navy-900 hover:bg-slate-800'
                }`}
              >
                {busy ? (
                  <>
                    <Icon name="loader" className="size-4 animate-spin motion-reduce:animate-none" />
                    Checking document…
                  </>
                ) : (
                  'Upload PDF'
                )}
              </span>
            </label>
            <p className="mt-3 text-sm text-slate-600">or drag and drop your PDF here</p>
          </div>

          <p className="mt-4 text-xs leading-relaxed text-slate-500">
            PDF only, up to 25&nbsp;MB. Your document is held in a temporary workspace on the
            server, is deleted when you discard it, and expires automatically. It is not stored
            permanently.
          </p>

          <p className="mt-4 flex items-start gap-2 border-t border-slate-200 pt-4 text-xs text-slate-600">
            <Icon name="info" className="mt-px size-3.5 text-slate-500" />
            Your analysis is grounded in the text of the uploaded document.
          </p>
        </div>

        {error && (
          <ErrorState title="The document could not be uploaded" className="mt-4">
            {error}
          </ErrorState>
        )}
      </section>
    </div>
  )
}
