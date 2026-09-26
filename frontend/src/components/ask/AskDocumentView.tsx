import { useState } from 'react'

import { useAsk } from '../../hooks/useAsk'
import type { Phase } from '../../lib/phase'
import type { LanguageCode } from '../../types/api'
import type { WorkspaceTab } from '../../lib/tabs'
import { Button } from '../ui/Button'
import { EmptyState } from '../ui/EmptyState'
import { Icon } from '../ui/Icon'
import { LanguageSelect } from '../ui/LanguageSelect'
import { ErrorState } from '../ui/StatusBanner'
import { AnswerCard } from './AnswerCard'

const MAX_QUESTION_CHARS = 2000

/**
 * Generic examples, labelled as examples. Nothing here assumes the uploaded
 * document contains the clause a question asks about.
 */
const EXAMPLES = [
  'What is the termination notice period?',
  'What are the payment terms?',
  'What are the termination conditions?',
]

interface Props {
  documentId: string
  /** False when the backend says this document is not eligible for answering. */
  eligible: boolean
  phase: Phase
  /**
   * Whether an analysis of this document has completed and its results are
   * available. Used for one sentence only: when a question fails, a reader
   * with results needs telling that those results still stand. Asserting it
   * unconditionally would be a claim about a run that may never have happened.
   */
  analysisComplete: boolean
  onGoTo: (tab: WorkspaceTab) => void
}

function Guidance() {
  return (
    <aside
      aria-label="About these answers"
      className="self-start rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_0_rgb(15_23_42/0.04)]"
    >
      <h3 className="font-mono text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
        How answers are checked
      </h3>
      <ul className="mt-3 space-y-3 text-sm text-slate-700">
        <li className="flex gap-2.5">
          <Icon name="book" className="mt-0.5 size-4 text-accent-700" />
          The answer is written from this document only &mdash; no web search and no other
          documents.
        </li>
        <li className="flex gap-2.5">
          <Icon name="shieldCheck" className="mt-0.5 size-4 text-accent-700" />
          Every quotation is located in the document, and each statement is checked against its
          quotation.
        </li>
        <li className="flex gap-2.5">
          <Icon name="ban" className="mt-0.5 size-4 text-accent-700" />
          Statements the evidence does not establish are removed. If nothing can be confirmed, you
          are told so instead of being given a guess.
        </li>
      </ul>
      <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
        One question, one answer. Earlier questions are not carried into later ones, so every
        answer rests on the document alone.
      </p>
    </aside>
  )
}

/**
 * Ask a question about the uploaded document.
 *
 * One question, one answer, with the evidence it rests on — not a chat. The
 * hook keeps no history on purpose: carrying earlier turns would add a second
 * source of context the verifier cannot check.
 */
export function AskDocumentView({ documentId, eligible, phase, analysisComplete, onGoTo }: Props) {
  const [question, setQuestion] = useState('')
  const [language, setLanguage] = useState<LanguageCode>('en')
  const { ask, answer, error, asking } = useAsk(documentId)

  const submit = () => {
    if (!asking && question.trim()) void ask(question, language)
  }

  return (
    // Named as a landmark with an unambiguous scope. Everything inside belongs
    // to the question, which is what makes a failure inside it a failure of the
    // question and not of the analysis.
    <section aria-labelledby="ask-heading" className="space-y-6">
      <div className="max-w-2xl">
        <h2
          id="ask-heading"
          tabIndex={-1}
          className="font-display text-2xl font-semibold tracking-tight text-navy-950 focus:outline-none"
        >
          Ask your document
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Ask questions about the document. Answers are grounded in the uploaded text and shown
          with the passages they are based on.
        </p>
      </div>

      {!eligible ? (
        <EmptyState
          icon="message"
          title={phase === 'blocked' ? 'Questions need the whole document' : 'Read the document first'}
          action={
            <Button variant="secondary" onClick={() => onGoTo('overview')}>
              {phase === 'blocked' ? 'See coverage details' : 'Go to Overview'}
            </Button>
          }
        >
          {phase === 'blocked'
            ? 'Not every page of this document could be read, so questions cannot be answered from it safely.'
            : 'Questions are answered once every page of the document has been read.'}
        </EmptyState>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="min-w-0 space-y-5">
            <form
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_0_rgb(15_23_42/0.04)] sm:p-5"
              onSubmit={(event) => {
                event.preventDefault()
                submit()
              }}
            >
              <label htmlFor="question" className="text-sm font-semibold text-slate-900">
                Your question about this document
              </label>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <input
                  id="question"
                  type="text"
                  value={question}
                  maxLength={MAX_QUESTION_CHARS}
                  disabled={asking}
                  placeholder="What is the termination notice period?"
                  onChange={(event) => setQuestion(event.target.value)}
                  className="min-h-11 min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-accent-600 focus:ring-2 focus:ring-accent-600/15 focus:outline-none disabled:bg-slate-50"
                />
                <Button type="submit" disabled={asking || !question.trim()} className="min-h-11 sm:px-6">
                  {asking ? (
                    <>
                      <Icon name="loader" className="size-4 animate-spin motion-reduce:animate-none" />
                      Reading…
                    </>
                  ) : (
                    'Ask'
                  )}
                </Button>
              </div>
              <div className="mt-2">
                <LanguageSelect
                  id="ask-language"
                  label="Answer language"
                  value={language}
                  onChange={setLanguage}
                  disabled={asking}
                />
              </div>

              {!answer && !asking && !error && (
                <div className="mt-3">
                  <p className="text-xs text-slate-500">Example questions</p>
                  <ul className="mt-1.5 flex flex-wrap gap-1.5">
                    {EXAMPLES.map((example) => (
                      <li key={example}>
                        <button
                          type="button"
                          onClick={() => setQuestion(example)}
                          className="min-h-9 rounded-md border border-slate-200 bg-slate-50 px-2.5 text-xs text-slate-700 hover:border-slate-300 hover:bg-white"
                        >
                          {example}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </form>

            <div aria-live="polite" className="space-y-5">
              {asking && (
                <div className="flex gap-3 rounded-xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-800">
                  <Icon name="loader" className="mt-0.5 size-4 animate-spin text-accent-600 motion-reduce:animate-none" />
                  <div>
                    Reading the document and checking the answer against it…
                    <span className="mt-1 block text-xs text-slate-500">
                      This can take up to a minute. Every quote is verified before it is shown.
                    </span>
                  </div>
                </div>
              )}

              {/* Scoped to the question, deliberately. The heading says which
                  of the two things in this workspace failed — a Q&A outage
                  used to read as an analysis outage, and a user with completed
                  results was told they had none. */}
              {error && (
                <ErrorState title="Question not answered">
                  <p>{error}</p>
                  {analysisComplete && (
                    <p className="mt-1.5 text-xs">
                      Your document analysis is unaffected — its findings are unchanged.
                    </p>
                  )}
                </ErrorState>
              )}

              {answer && !asking && <AnswerCard answer={answer} />}

              {!answer && !asking && !error && (
                <p className="text-sm text-slate-500">
                  Answers appear here, with the passages from your document they are based on.
                </p>
              )}
            </div>
          </div>

          <Guidance />
        </div>
      )}
    </section>
  )
}
