import { pageRef, plural } from '../../lib/format'
import { ANSWER_STATUS, TONE_CLASSES } from '../../lib/verdicts'
import type { AnswerEvidence, AskResponse } from '../../types/api'
import { Icon } from '../ui/Icon'
import { TranslationLabel } from '../ui/LanguageSelect'

const PROVIDER_NAMES: Record<string, string> = { gemini: 'Gemini', nemotron: 'Nemotron' }
import { VerificationBadge } from '../ui/VerificationBadge'

function EvidenceItem({ item }: { item: AnswerEvidence }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[0.6875rem] font-semibold text-slate-700">
          {pageRef(item.page, item.section)}
        </span>
        {/* The backend's per-quote verdict. Never hardcoded to "verified". */}
        <VerificationBadge status={item.verification_status} size="short" />
      </div>
      {/* Rendered as text, never as markup, and never edited here — this is the
          document's own wording as the backend located it. */}
      <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 text-[0.8125rem] leading-[1.65] text-slate-800">
        “{item.quote}”
      </blockquote>
      {item.note && <p className="mt-2 text-xs text-amber-900">{item.note}</p>}
    </li>
  )
}

/**
 * One answer, with the evidence it rests on.
 *
 * The answer shown is whatever survived the backend's verification. When
 * nothing did, the backend's own not-found text is displayed and the model's
 * words never reach this component at all.
 */
export function AnswerCard({ answer }: { answer: AskResponse }) {
  const status = ANSWER_STATUS[answer.status] ?? ANSWER_STATUS.not_found

  return (
    // A section, not an article: `article` is the finding card's role, and an
    // answer must never be countable as a finding.
    <section
      aria-label="Answer"
      className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_0_rgb(15_23_42/0.04)]"
    >
      <div className="border-b border-slate-200 bg-slate-50 px-5 py-3">
        <p className="font-mono text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
          Your question
        </p>
        {/* Echoed by the backend, rendered as text. */}
        <p className="mt-1 text-sm font-medium text-slate-900">{answer.question}</p>
      </div>

      <div className="space-y-4 p-5">
        <div className={`rounded-lg border px-4 py-3 ${TONE_CLASSES[status.tone]}`}>
          <p className="flex items-center gap-2 text-xs font-semibold tracking-wide uppercase">
            <Icon name={status.icon} className="size-4" />
            {status.label}
          </p>
          <p className="mt-2 text-[0.9375rem] leading-relaxed text-slate-900">{answer.answer}</p>
        </div>

        {/* Present only when every sentence of the answer held up. The
            evidence below is always the document's own wording. */}
        {answer.answer_translation && (
          <div className="border-l-2 border-amber-300 pl-3" lang="ta">
            <TranslationLabel />
            <p className="mt-1 text-[0.9375rem] leading-relaxed text-slate-800">
              {answer.answer_translation}
            </p>
          </div>
        )}

        {answer.evidence.length > 0 && (
          <div>
            <h4 className="font-mono text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
              Evidence from your document
            </h4>
            <ul className="mt-2 space-y-2">
              {answer.evidence.map((item, index) => (
                <EvidenceItem key={`${item.page}-${index}`} item={item} />
              ))}
            </ul>
          </div>
        )}

        {answer.claims_withheld > 0 && (
          <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            {answer.claims_withheld} of {answer.claims_checked}{' '}
            {plural(answer.claims_checked, 'statement', 'statements')} in the answer{' '}
            {answer.claims_withheld === 1 ? 'was' : 'were'} removed because the evidence did not
            establish {answer.claims_withheld === 1 ? 'it' : 'them'}. A verified quote does not make
            every sentence beside it verified.
          </p>
        )}

        {answer.withheld_evidence > 0 && (
          <p className="text-xs text-slate-600">
            {answer.withheld_evidence}{' '}
            {answer.withheld_evidence === 1 ? 'quote was' : 'quotes were'} withheld because they
            could not be located in this document, or were instructions rather than contract terms.
            Their text is not shown.
          </p>
        )}

        {answer.provenance && (
          <p className="font-mono text-[0.6875rem] text-slate-500">
            Answered by{' '}
            {PROVIDER_NAMES[answer.provenance.provider] ?? answer.provenance.provider} ·
            Verification: application-controlled
          </p>
        )}

        <p className="border-t border-slate-100 pt-3 text-xs text-slate-500">{answer.disclaimer}</p>
      </div>
    </section>
  )
}
