'use client'

import { useEffect, useState } from 'react'

import { IST_TIME } from './use-mounted-clock'

/**
 * Today's date in IST, as `YYYY-MM-DD`, and `null` until after mount.
 *
 * ## Why this exists rather than `new Date().toISOString().slice(0, 10)`
 *
 * `toISOString()` is UTC. The server renders in UTC and the browser runs in IST, so the two passes
 * disagree on the date for the five and a half hours between 18:30 and 00:00 UTC — which is the
 * middle of every Indian trading evening. The page then reports on the wrong day, and React throws
 *
 *     #425: Text content did not match server-rendered HTML
 *
 * Measured on production: `/reports/daily` produced 9 page errors on every load. The page still
 * *looked* fine, which is what makes this one easy to miss — the visible date was right, the
 * hydration was not.
 *
 * ## Why IST specifically
 *
 * This is a broker terminal for Indian markets and every session boundary here is IST: the 18:00
 * auto-send, the 09:15 open, the daily P&L cutoff. A daily report keyed to UTC would roll over at
 * 05:30 IST, mid-session, and attribute the morning's trades to the previous day.
 *
 * ## The rule
 *
 * Same as `useMountedClock`: nothing derived from *now* may appear in the first render. `null`
 * until after mount makes the server pass and the first client pass agree. Callers must handle the
 * `null` state — the report simply renders as "not ready" for one paint, which is invisible.
 */
export function useMountedToday(): string | null {
  const [today, setToday] = useState<string | null>(null)

  useEffect(() => {
    const format = () =>
      // `en-CA` formats as YYYY-MM-DD, which is what the API's `date` parameter expects.
      new Date().toLocaleDateString('en-CA', IST_TIME)

    setToday(format())

    // A tab left open past midnight would otherwise keep reporting yesterday. The next local
    // midnight is the only moment the value can change, so a timer is scheduled to that instant
    // and re-armed from inside itself — no polling.
    let timer: ReturnType<typeof setTimeout>
    const schedule = () => {
      const now = new Date()
      // `Date.UTC` on the local wall-clock parts gives the instant of the next local midnight.
      const nextMidnight = new Date(
        Date.UTC(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 5),
      ).getTime()
      timer = setTimeout(() => {
        setToday(format())
        schedule()
      }, Math.max(nextMidnight - now.getTime(), 1000))
    }
    schedule()

    const onVisible = () => {
      if (document.visibilityState === 'visible') setToday(format())
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  return today
}
