import type { IconName } from '../components/ui/Icon'
import type { AnswerStatus, VerificationStatus } from '../types/api'

export type Tone = 'verified' | 'partial' | 'rejected' | 'neutral' | 'withheld' | 'info' | 'danger'

/** Badge and banner colours per tone. Every use also carries visible text. */
export const TONE_CLASSES: Record<Tone, string> = {
  verified: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  partial: 'border-amber-200 bg-amber-50 text-amber-900',
  rejected: 'border-rose-200 bg-rose-50 text-rose-800',
  neutral: 'border-slate-200 bg-slate-100 text-slate-700',
  withheld: 'border-slate-300 bg-slate-100 text-slate-700',
  info: 'border-accent-100 bg-accent-50 text-accent-700',
  danger: 'border-rose-200 bg-rose-50 text-rose-800',
}

interface Verdict {
  /** The full sentence, shown wherever there is room for it. */
  label: string
  /** The badge form, for dense lists. */
  short: string
  tone: Tone
  icon: IconName
  /**
   * What the backend's verdict means, for the "Why this status?" panel.
   *
   * Written from the verifier's actual chain (backend/app/verification/
   * grounding.py and policy.py): quote present, page exists, quote occurs on
   * that page, the values in it agree, polarity agrees, and the claim is then
   * checked against the quote. Nothing here describes a check that is not run.
   */
  why: string
}

/**
 * How each verification verdict is presented.
 *
 * The output gate only releases `verified` findings today, but the label is
 * always derived from the finding rather than assumed, so a change on the
 * server can never leave the UI calling something verified that is not.
 */
export const VERDICTS: Record<VerificationStatus, Verdict> = {
  verified: {
    label: 'Verified against document evidence',
    short: 'Verified',
    tone: 'verified',
    icon: 'checkCircle',
    why:
      'The quotation was found on the cited page of your document, the numbers and dates in it ' +
      'match the text there, and the claim was checked against the quotation. The model’s own ' +
      'description of its answer played no part in this decision.',
  },
  partially_verified: {
    label: 'Partially supported — review details',
    short: 'Partially supported',
    tone: 'partial',
    icon: 'alertTriangle',
    why:
      'The quotation was found on the cited page, but a value in the claim could not be ' +
      'confirmed against it — for example a date whose written form has more than one reading.',
  },
  rejected: {
    label: 'Evidence did not support this claim',
    short: 'Not supported',
    tone: 'rejected',
    icon: 'xCircle',
    why:
      'The cited page does not exist, the quotation could not be found on it, or an amount, ' +
      'number or date in the claim differed from the document.',
  },
  unverified: {
    label: 'Could not verify from the document',
    short: 'Could not verify',
    tone: 'neutral',
    icon: 'helpCircle',
    why:
      'The finding had no usable quotation, or the text of the cited page could not be read, ' +
      'so the claim could not be checked either way.',
  },
}

export const verdictFor = (status: VerificationStatus): Verdict =>
  VERDICTS[status] ?? VERDICTS.unverified

/** Statements the output gate held back. Their text is never returned. */
export const WITHHELD = {
  label: 'Not displayed as a verified finding',
  tone: 'withheld' as Tone,
  icon: 'ban' as IconName,
}

/**
 * How each answer-level verdict is introduced. Backend values only.
 *
 * `not_found` is deliberately "couldn't confirm", not "doesn't exist". The
 * system checks whether evidence supports a claim; it cannot establish that a
 * clause is absent from a document.
 */
export const ANSWER_STATUS: Record<
  AnswerStatus,
  { label: string; tone: Tone; icon: IconName }
> = {
  supported: { label: 'Answered from the document', tone: 'verified', icon: 'checkCircle' },
  partially_supported: {
    label: 'Partly supported — check the evidence',
    tone: 'partial',
    icon: 'alertTriangle',
  },
  not_found: {
    label: "Couldn't confirm this from the document",
    tone: 'partial',
    icon: 'helpCircle',
  },
}
