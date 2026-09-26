import { humanise, plural } from '../../lib/format'
import type { ReasoningResult } from '../../types/api'

const STATUS_TEXT: Record<Exclude<ReasoningResult['status'], 'completed'>, string> = {
  disabled: 'Reasoning notes are switched off for this deployment.',
  skipped:
    'No reasoning notes: they are produced only when at least two findings were released, and within the analysis time budget.',
  unavailable: 'Reasoning notes are unavailable: the reasoning service is not configured.',
  failed:
    'Reasoning notes could not be produced this time. The findings above are unaffected — they were released before this step ran.',
}

/**
 * Notes a reasoning model proposed about how released findings relate.
 *
 * Deliberately styled apart from findings: no verification badge, an amber
 * interpretation border, and the backend's fixed label on every note. A note
 * never changes a finding, and nothing here says a note is verified.
 */
export function ReasoningNotes({
  reasoning,
  onInspect,
}: {
  reasoning: ReasoningResult | null | undefined
  onInspect: (findingId: string) => void
}) {
  if (!reasoning || reasoning.status === 'disabled') return null

  return (
    <section
      aria-labelledby="reasoning-notes-heading"
      className="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_0_rgb(15_23_42/0.04)] sm:p-5"
    >
      <h3 id="reasoning-notes-heading" className="font-display text-sm font-semibold text-slate-900">
        Reasoning notes
      </h3>
      <p className="mt-1 text-xs text-slate-600">
        How some released findings may relate to each other. These are AI interpretation to help
        you decide what to read together &mdash; not findings, not verified, and not legal advice.
      </p>

      {reasoning.status !== 'completed' ? (
        <p className="mt-3 text-sm text-slate-700">{STATUS_TEXT[reasoning.status]}</p>
      ) : reasoning.notes.length === 0 ? (
        <p className="mt-3 text-sm text-slate-700">No reasoning notes were released.</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {reasoning.notes.map((note) => (
            <li key={note.id} className="border-l-2 border-amber-300 pl-3">
              <p className="text-xs font-semibold tracking-wide text-amber-900 uppercase">
                {note.label}
              </p>
              <p className="mt-0.5 font-mono text-[0.6875rem] text-slate-500 uppercase">
                {humanise(note.category)}
              </p>
              <p className="mt-1 text-sm leading-relaxed text-slate-800">{note.text}</p>
              {note.quotes.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {note.quotes.map((quote, index) => (
                    <li key={index} className="text-[0.8125rem] leading-[1.6] text-slate-700">
                      &ldquo;{quote}&rdquo;
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-slate-600">
                Relates to:
                {note.finding_ids.map((id) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => onInspect(id)}
                    className="min-h-7 rounded border border-slate-200 bg-slate-50 px-1.5 font-mono text-[0.6875rem] text-slate-800 hover:border-slate-300"
                  >
                    {id}
                  </button>
                ))}
              </p>
              {note.evidence_checked && (
                <p className="mt-1 text-[0.6875rem] text-slate-500">
                  The quoted text above was confirmed to come from the cited findings. The
                  note&rsquo;s conclusion was not checked.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {reasoning.withheld_count > 0 && (
        <p className="mt-3 text-xs text-slate-600">
          {reasoning.withheld_count} {plural(reasoning.withheld_count, 'note was', 'notes were')}{' '}
          withheld because {reasoning.withheld_count === 1 ? 'it' : 'they'} went beyond the
          released findings. Their text is not shown.
        </p>
      )}
    </section>
  )
}
