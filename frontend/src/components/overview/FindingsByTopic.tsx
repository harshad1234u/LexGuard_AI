import { humanise, pageRef, plural } from '../../lib/format'
import type { DocumentOverview, OverviewCategoryGroup, OverviewItem } from '../../types/api'
import { Icon } from '../ui/Icon'

/**
 * One released finding, under its topic.
 *
 * Every field here came from the backend's overview, which copied it from a
 * finding that had already passed the output gate. Nothing is derived in this
 * component, and nothing is rendered as markup.
 */
function Item({ item, onInspect }: { item: OverviewItem; onInspect: (id: string) => void }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-3.5">
      {/* The verified claim. The same sentence appears on the finding card,
          with its evidence badge; this is the navigational copy of it. */}
      <p className="text-sm font-medium text-slate-900">{item.claim}</p>

      {/* The document's own wording, as the verifier located it. */}
      <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 text-[0.8125rem] leading-relaxed text-slate-700 italic">
        &ldquo;{item.quote}&rdquo;
      </blockquote>

      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-[0.6875rem] text-slate-500">
          {pageRef(item.page, item.section)} · {humanise(item.label)}
        </p>
        <button
          type="button"
          onClick={() => onInspect(item.finding_id)}
          className="inline-flex min-h-8 items-center gap-1 rounded text-xs font-semibold text-accent-700 hover:underline"
        >
          Inspect evidence
          <Icon name="chevronRight" className="size-3.5" />
        </button>
      </div>
    </li>
  )
}

/**
 * One topic.
 *
 * An empty topic shows the backend's own sentence and nothing else. The
 * wording is not written here on purpose: "nothing was released for this
 * category" is a statement about what the application decided, and the
 * application is the thing that gets to phrase it. A frontend that composed
 * its own sentence could drift into saying the document lacks the clause,
 * which is an absence nothing in this system can establish.
 */
function Category({
  group,
  onInspect,
}: {
  group: OverviewCategoryGroup
  onInspect: (id: string) => void
}) {
  const empty = group.items.length === 0
  const headingId = `topic-${group.key}`

  if (empty) {
    return (
      <section
        aria-labelledby={headingId}
        className="flex flex-col gap-0.5 px-4 py-2.5 sm:flex-row sm:items-baseline sm:gap-4"
      >
        <h4 id={headingId} className="shrink-0 text-xs font-semibold text-slate-700 sm:w-40">
          {group.label}
        </h4>
        <p className="text-xs text-slate-500">{group.empty_message}</p>
      </section>
    )
  }

  return (
    <section aria-labelledby={headingId} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-0.5">
        <h4 id={headingId} className="text-xs font-semibold tracking-wide text-slate-600 uppercase">
          {group.label}
        </h4>
        <span className="font-mono text-[0.6875rem] text-slate-500 tabular-nums">
          {group.items.length} {plural(group.items.length, 'finding', 'findings')}
        </span>
      </div>
      <ul className="mt-2 space-y-2">
        {group.items.map((item) => (
          <Item key={item.finding_id} item={item} onInspect={onInspect} />
        ))}
      </ul>
    </section>
  )
}

/**
 * Released findings, grouped by document topic.
 *
 * This panel adds nothing. It shows findings that already passed the output
 * gate, under headings the application chose from a closed list, so a reader
 * can see the shape of what was established rather than an unordered list.
 *
 * Three things it is careful not to be:
 *
 *   - **Not a summary.** It contains no sentence about the document as a
 *     whole. A summary is a claim spanning a document, and the verifier binds
 *     a claim to the sentence its evidence sits in.
 *   - **Not a completeness statement.** An empty topic means nothing was
 *     released for it, never that the document is silent on it. The
 *     proposed/withheld counts are shown so a reader can see the difference.
 *   - **Not an assessment.** No risk badge, no attention level, no ordering by
 *     importance, and no statement about whose duty anything is.
 *
 * Topics with released findings are listed before topics without, each group
 * in the backend's own order. That is a layout decision about what is present,
 * not a ranking of what matters.
 */
export function FindingsByTopic({
  overview,
  onInspect,
}: {
  overview: DocumentOverview | null
  onInspect: (findingId: string) => void
}) {
  // Nothing to group until an analysis has completed.
  if (!overview || overview.categories.length === 0) return null

  const { released_count: released, proposed_count: proposed, withheld_count: withheld } =
    overview
  const filled = overview.categories.filter((group) => group.items.length > 0)
  const empty = overview.categories.filter((group) => group.items.length === 0)

  return (
    <section
      aria-labelledby="topics-heading"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_0_rgb(15_23_42/0.04)]"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 id="topics-heading" className="font-display text-base font-semibold text-slate-900">
          Verified findings by topic
        </h3>
        <span className="font-mono text-xs text-slate-500 tabular-nums">
          {released} of {proposed} {plural(proposed, 'statement', 'statements')} released
        </span>
      </div>

      <p className="mt-1 text-sm text-slate-600">
        Verified findings grouped by document topic. This is not a legal assessment and not a
        complete summary of the document.
      </p>

      {filled.length > 0 && (
        <div className="mt-4 grid gap-3 xl:grid-cols-2">
          {filled.map((group) => (
            <Category key={group.key} group={group} onInspect={onInspect} />
          ))}
        </div>
      )}

      {empty.length > 0 && (
        <div className="mt-4 divide-y divide-slate-200 rounded-lg border border-slate-200">
          {empty.map((group) => (
            <Category key={group.key} group={group} onInspect={onInspect} />
          ))}
        </div>
      )}

      {/* The sentence that stops an empty topic being read as a finding about
          the document. It states the two counts rather than reassuring. */}
      <p className="mt-4 text-xs leading-relaxed text-slate-500">
        {withheld > 0
          ? `${withheld} of ${proposed} statements the model proposed were withheld because the document did not confirm them. `
          : ''}
        A topic with nothing under it means nothing was confirmed for it in this analysis &mdash;
        not that the document does not cover it. Read the document itself, and consult a
        qualified lawyer about anything that matters.
      </p>
    </section>
  )
}
