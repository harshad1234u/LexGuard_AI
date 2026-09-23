import { useSyncExternalStore } from 'react'

/** Whether a CSS media query currently matches, kept in sync with the viewport. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', notify)
      return () => list.removeEventListener('change', notify)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}

/** The breakpoint at which inspectors sit beside their list instead of in a sheet. */
export const WIDE = '(min-width: 1024px)'
