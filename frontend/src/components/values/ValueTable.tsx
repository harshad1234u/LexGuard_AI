import type { DocumentValue } from '../../types/api'
import { Icon } from '../ui/Icon'

/**
 * One group of values - amounts, say - as a table.
 *
 * Columns are only what the backend returns: the value as written (with a
 * note when a date's written form is ambiguous) and its page. There is no
 * "context" or "meaning" column, because the index records neither.
 */
export function ValueTable({
  heading,
  headingId,
  items,
  selectedKey,
  wide,
  onSelect,
}: {
  heading: string
  headingId: string
  items: { item: DocumentValue; key: string }[]
  selectedKey: string | null
  wide: boolean
  onSelect: (key: string) => void
}) {
  return (
    <section aria-labelledby={headingId} className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="flex items-baseline justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2.5">
        <h3 id={headingId} className="text-sm font-semibold text-slate-900">
          {heading}
        </h3>
        <span className="font-mono text-[0.6875rem] text-slate-500 tabular-nums">{items.length}</span>
      </div>
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{heading} located in the document, with page references</caption>
        <thead>
          <tr className="border-b border-slate-100 font-mono text-[0.6875rem] tracking-wide text-slate-500 uppercase">
            <th scope="col" className="px-4 py-2 font-semibold">
              Value
            </th>
            <th scope="col" className="w-24 px-4 py-2 font-semibold">
              Page
            </th>
            <th scope="col" className="w-12 px-2 py-2">
              <span className="sr-only">Inspect</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map(({ item, key }) => {
            const selected = selectedKey === key && wide
            return (
              <tr
                key={key}
                onClick={() => onSelect(key)}
                className={`cursor-pointer transition-colors ${selected ? 'bg-accent-50' : 'hover:bg-slate-50'}`}
              >
                <td className="px-4 py-2.5 align-top">
                  {/* Rendered as escaped text, never as markup - this is
                      document content and is treated as untrusted. */}
                  <span className="font-mono text-[0.8125rem] font-medium text-slate-900">{item.value}</span>
                  {item.ambiguous && (
                    <span className="mt-0.5 block text-xs text-amber-800">Date format unclear</span>
                  )}
                </td>
                <td className="px-4 py-2.5 align-top font-mono text-xs whitespace-nowrap text-slate-600">
                  Page {item.page}
                </td>
                <td className="px-2 py-1.5 text-right align-top">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation()
                      onSelect(key)
                    }}
                    // Named by attribute, not by hidden text, so the value appears
                    // once in the page's text and once in the accessibility tree.
                    aria-label={`Inspect ${item.value}, page ${item.page}`}
                    aria-pressed={wide ? selected : undefined}
                    aria-haspopup={wide ? undefined : 'dialog'}
                    className="inline-flex size-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                  >
                    <Icon name="chevronRight" className="size-4" />
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}
