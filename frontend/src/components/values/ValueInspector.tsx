import { plural, VALUE_LABEL } from '../../lib/format'
import type { DocumentValue } from '../../types/api'
import { Icon } from '../ui/Icon'

function Label({ children }: { children: string }) {
  return (
    <h4 className="font-mono text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
      {children}
    </h4>
  )
}

/**
 * Where one value was found, and nothing it does not know.
 *
 * Everything here is derived from the values response alone: the value, its
 * kind, its page, and the other entries that share a page or a spelling. The
 * index does not keep the surrounding sentence, so this panel does not show
 * one - and it says so, rather than leaving a reader to wonder.
 */
export function ValueDetails({
  item,
  all,
}: {
  item: DocumentValue
  all: DocumentValue[]
}) {
  const otherPages = [
    ...new Set(all.filter((v) => v.value === item.value && v.page !== item.page).map((v) => v.page)),
  ].sort((a, b) => a - b)
  const samePage = all.filter((v) => v.page === item.page && v !== item)

  return (
    <div className="space-y-5">
      <div>
        <p className="font-mono text-[0.6875rem] font-semibold tracking-wide text-accent-700 uppercase">
          {VALUE_LABEL[item.kind]}
        </p>
        <p className="mt-1.5 font-mono text-2xl font-semibold break-words text-slate-900">
          {item.value}
        </p>
      </div>

      <div>
        <Label>Source</Label>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-slate-500">Page</dt>
          <dd className="font-mono text-slate-900">{item.page}</dd>
          {otherPages.length > 0 && (
            <>
              <dt className="text-slate-500">Also on</dt>
              <dd className="font-mono text-slate-900">
                {plural(otherPages.length, 'page', 'pages')} {otherPages.join(', ')}
              </dd>
            </>
          )}
        </dl>
      </div>

      {item.ambiguous && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-900">
          <p className="font-semibold">This date can be read more than one way</p>
          <p className="mt-1 text-xs leading-relaxed">
            Its written form has more than one reading &mdash; day-first or month-first, for
            example &mdash; so it is shown exactly as written and no calendar date is assigned to
            it.
          </p>
        </div>
      )}

      <div>
        <Label>How it was found</Label>
        <p className="mt-2 text-sm leading-relaxed text-slate-700">
          Located in the text extracted from page {item.page}. No AI model was involved, and
          nothing here says what the value refers to or whether it matters.
        </p>
      </div>

      <div className="flex gap-2.5 rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-3 text-xs leading-relaxed text-slate-600">
        <Icon name="info" className="mt-px size-3.5 text-slate-500" />
        <p>
          The surrounding text is not part of this index. Open page {item.page} of your PDF to
          read the value in context, or ask a question about it.
        </p>
      </div>

      {samePage.length > 0 && (
        <div>
          <Label>Also on this page</Label>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {samePage.map((v, index) => (
              <li
                key={`${v.kind}-${v.value}-${index}`}
                className="rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-xs text-slate-700"
              >
                {v.value}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** The value inspector beside the tables on wide screens. */
export function ValueInspector({
  item,
  all,
}: {
  item: DocumentValue | null
  all: DocumentValue[]
}) {
  return (
    <section
      id="value-inspector"
      aria-labelledby="value-inspector-heading"
      className="rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_0_rgb(15_23_42/0.04)]"
    >
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-5 py-3">
        <h3
          id="value-inspector-heading"
          className="flex items-center gap-2 font-display text-sm font-semibold text-slate-900"
        >
          <Icon name="book" className="size-4 text-accent-700" />
          Value inspector
        </h3>
        {item && (
          <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[0.6875rem] font-semibold text-slate-700">
            p. {item.page}
          </span>
        )}
      </div>
      <div className="p-5">
        {item ? (
          <ValueDetails item={item} all={all} />
        ) : (
          <p className="text-sm text-slate-600">
            Select a value to see the page it was found on and what else that page contains.
          </p>
        )}
      </div>
    </section>
  )
}
