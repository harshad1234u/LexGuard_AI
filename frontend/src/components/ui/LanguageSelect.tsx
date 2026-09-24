import type { LanguageCode } from '../../types/api'

const OPTIONS: { value: LanguageCode; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'ta', label: 'தமிழ் (Tamil)' },
]

/**
 * The reader's language for explanations and answers.
 *
 * Choosing Tamil adds a labelled translation beside the checked English text;
 * it never replaces the document's own wording, and the quotes are always the
 * document's own words.
 */
export function LanguageSelect({
  id,
  value,
  onChange,
  disabled,
  label = 'Explanation language',
}: {
  id: string
  value: LanguageCode
  onChange: (value: LanguageCode) => void
  disabled?: boolean
  label?: string
}) {
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="text-xs font-medium text-slate-600">
        {label}
      </label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as LanguageCode)}
        className="min-h-9 rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-900 focus:border-accent-600 focus:ring-2 focus:ring-accent-600/15 focus:outline-none disabled:bg-slate-50"
      >
        {OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}

/** The fixed label shown above every translation. */
export function TranslationLabel() {
  return (
    <p className="text-xs font-semibold tracking-wide text-amber-900 uppercase">
      Translation (தமிழ்) &mdash; not independently checked
    </p>
  )
}
