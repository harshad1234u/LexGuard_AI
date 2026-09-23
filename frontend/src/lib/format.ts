import type { DocumentValue, ValueKind } from '../types/api'

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many
}

/** A model-chosen category label, made readable. Never interpreted. */
export function humanise(label: string): string {
  const text = label.replace(/_/g, ' ').trim()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** "Page 2", or "Page 2 · Section 7.2" when the backend confirmed a section. */
export function pageRef(page: number, section: string | null): string {
  return section ? `Page ${page} · ${section}` : `Page ${page}`
}

/**
 * Display groups for extracted values, in the order they are shown.
 *
 * The headings name what a value *is*, never what it does. "Amounts", not
 * "Payments"; "Time periods", not "Deadlines". A period in a contract might be
 * a notice period, a cure period or a survival period, and deciding which is
 * interpretation the values index does not do.
 */
export const VALUE_GROUPS: { kind: ValueKind; heading: string; singular: string }[] = [
  { kind: 'currency', heading: 'Amounts', singular: 'Amount' },
  { kind: 'percentage', heading: 'Percentages', singular: 'Percentage' },
  { kind: 'duration', heading: 'Time periods', singular: 'Time period' },
  { kind: 'date', heading: 'Dates', singular: 'Date' },
]

export const VALUE_LABEL: Record<ValueKind, string> = Object.fromEntries(
  VALUE_GROUPS.map((group) => [group.kind, group.singular]),
) as Record<ValueKind, string>

/** A stable key for one entry in the values list; the list itself has no ids. */
export const valueKey = (item: DocumentValue, index: number) =>
  `${item.kind}-${item.page}-${item.value}-${index}`
