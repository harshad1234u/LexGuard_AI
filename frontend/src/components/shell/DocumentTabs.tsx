import { useRef, type KeyboardEvent } from 'react'

import { panelId, tabId, type WorkspaceTab } from '../../lib/tabs'
import { Icon, type IconName } from '../ui/Icon'

export interface TabSpec {
  id: WorkspaceTab
  label: string
  icon: IconName
  /** Shown only when the backend has supplied a number to show. */
  count?: number | null
}

/**
 * The workspace sections, as an ARIA tab list.
 *
 * Arrow keys, Home and End move between tabs and activate them, and only the
 * active tab is in the page's tab order - the pattern screen-reader users
 * expect from a `tablist`.
 */
export function DocumentTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: TabSpec[]
  active: WorkspaceTab
  onChange: (tab: WorkspaceTab) => void
}) {
  const refs = useRef<Partial<Record<WorkspaceTab, HTMLButtonElement | null>>>({})

  const move = (event: KeyboardEvent<HTMLButtonElement>) => {
    const index = tabs.findIndex((tab) => tab.id === active)
    const target =
      event.key === 'ArrowRight'
        ? (index + 1) % tabs.length
        : event.key === 'ArrowLeft'
          ? (index - 1 + tabs.length) % tabs.length
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? tabs.length - 1
              : null
    if (target === null) return
    event.preventDefault()
    const next = tabs[target].id
    onChange(next)
    refs.current[next]?.focus()
  }

  return (
    <div className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/85">
      <div
        role="tablist"
        aria-label="Document workspace"
        className="mx-auto flex max-w-[90rem] gap-1 overflow-x-auto px-2 scrollbar-none sm:gap-2 sm:px-4 lg:px-6"
      >
        {tabs.map((tab) => {
          const selected = tab.id === active
          return (
            <button
              key={tab.id}
              ref={(node) => {
                refs.current[tab.id] = node
              }}
              id={tabId(tab.id)}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={panelId(tab.id)}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.id)}
              onKeyDown={move}
              className={`relative flex min-h-12 shrink-0 items-center gap-2 px-3 text-sm font-medium whitespace-nowrap transition-colors focus-visible:-outline-offset-2 ${
                selected ? 'text-navy-950' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              <Icon name={tab.icon} className="hidden size-4 sm:block" />
              {tab.label}
              {typeof tab.count === 'number' && (
                <span
                  className={`rounded px-1.5 py-px font-mono text-[0.6875rem] font-semibold ${
                    selected ? 'bg-navy-900 text-white' : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  {tab.count}
                </span>
              )}
              <span
                aria-hidden="true"
                className={`absolute inset-x-2 bottom-0 h-0.5 rounded-full ${
                  selected ? 'bg-accent-600' : 'bg-transparent'
                }`}
              />
            </button>
          )
        })}
      </div>
    </div>
  )
}
