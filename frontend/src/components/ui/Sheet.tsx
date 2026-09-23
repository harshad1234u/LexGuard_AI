import { useEffect, useRef, type ReactNode } from 'react'

import { Icon } from './Icon'

/**
 * A bottom sheet for narrow screens, built on the native `<dialog>`.
 *
 * `showModal()` gives focus containment, Escape-to-close and an inert page
 * behind it without any script of our own, and returns focus to whatever
 * opened it when it closes.
 */
export function Sheet({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      aria-label={title}
      onClose={onClose}
      onClick={(event) => {
        // A click on the backdrop lands on the dialog element itself.
        if (event.target === event.currentTarget) onClose()
      }}
      className="fixed inset-x-0 top-auto bottom-0 m-0 max-h-[85dvh] w-full max-w-none overflow-hidden rounded-t-2xl border-t border-slate-200 bg-white p-0 text-slate-900 shadow-2xl"
    >
      <div className="flex max-h-[85dvh] flex-col">
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <p className="font-display text-base font-semibold">{title}</p>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex size-10 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100"
          >
            <Icon name="close" className="size-5" />
            <span className="sr-only">Close</span>
          </button>
        </div>
        <div className="overflow-y-auto px-4 pt-4 pb-8">{open && children}</div>
      </div>
    </dialog>
  )
}
