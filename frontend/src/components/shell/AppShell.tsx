import type { ReactNode } from 'react'

import { Disclaimer } from './Disclaimer'

/**
 * The page frame: header, optional sub-navigation, content, disclaimer.
 *
 * The disclaimer sits in the footer of every screen, because the product's
 * claims are bounded on every screen, not only on the first one.
 */
export function AppShell({
  header,
  subnav,
  children,
}: {
  header: ReactNode
  subnav?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-navy-900 px-4 py-2 text-sm font-medium text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to main content
      </a>

      {header}
      {subnav}

      <main id="main" tabIndex={-1} className="flex-1 focus:outline-none">
        {children}
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-[90rem] px-4 py-5 sm:px-6 lg:px-8">
          <Disclaimer />
        </div>
      </footer>
    </div>
  )
}
