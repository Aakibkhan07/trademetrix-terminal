'use client'

import { useEffect, useState } from 'react'

/**
 * A wall-clock string that is safe to render.
 *
 * ## The hazard
 *
 * `new Date().toLocaleTimeString(...)` in a render body is **not** deterministic, and this app is
 * server-rendered even where it is a client component. React renders the tree on the server, sends
 * that HTML, then re-renders it in the browser to hydrate. If a minute boundary falls between those
 * two passes, the server wrote `03:38 am` and the browser computes `03:39 am`, and React reports
 *
 *     Text content did not match server-rendered HTML.
 *
 * It is intermittent by construction — the crawl is clean most runs and fails whenever it happens to
 * straddle a minute change, which is why it can sit in a codebase for a long time looking fine.
 *
 * ## The rule
 *
 * Anything derived from *now* must not appear in the first render. `null` until after mount makes the
 * server and first client pass agree (both empty), and the real time appears on the next paint,
 * which is imperceptible for a clock.
 *
 * This is not the same as formatting a *data* timestamp. `new Date(order.executed_at)` is
 * deterministic — the same input string yields the same output — so those are fine, provided the
 * formatter pins `timeZone` (see `IST_TIME` below).
 */

/**
 * `Asia/Kolkata`, pinned.
 *
 * `toLocaleTimeString()` with no `timeZone` formats in the **runtime's** zone. On the server that is
 * usually UTC; in an Indian user's browser it is IST. The same `2026-10-03T02:38:00Z` therefore
 * renders as `08:08 am` on the server and `08:08 am` locally by accident, but `03:38 am` versus
 * `08:08 am` in production — a hydration mismatch that never reproduces on a laptop where both
 * halves run in the same zone, and therefore never gets caught locally.
 *
 * Pinning the zone is correct for an Indian broker terminal regardless: every broker timestamp here
 * is IST, and a user comparing the terminal's clock with their broker's should see the same number.
 */
export const IST_TIME: Pick<Intl.DateTimeFormatOptions, 'timeZone'> = { timeZone: 'Asia/Kolkata' }

/** `HH:MM am/pm` in IST, or `null` until after mount. */
export function useMountedClock(locale = 'en-IN'): string | null {
  const [clock, setClock] = useState<string | null>(null)

  useEffect(() => {
    const format = () =>
      new Date().toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', ...IST_TIME })

    setClock(format())

    // Re-format on the minute boundary rather than every second: the display has a one-minute
    // resolution, so a 1s timer would re-render this component sixty times for no visible change.
    const msToNextMinute = 60000 - (Date.now() % 60000)
    const timer = setInterval(() => setClock(format()), msToNextMinute)

    // A tab restored from the background has a stale clock. `visibilitychange` is the cheapest
    // correct fix and avoids polling while the tab is hidden.
    const onVisible = () => {
      if (document.visibilityState === 'visible') setClock(format())
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [locale])

  return clock
}