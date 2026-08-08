import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'

const DESKTOP_QUERY = '(min-width: 901px)'

/** Below this width, pages stack their panels full-width instead of side by
 * side (see the max-width: 900px rules in index.css) — a dragged pixel
 * width would fight that layout, so resizing is desktop-only. */
function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(() => window.matchMedia(DESKTOP_QUERY).matches)
  useEffect(() => {
    const mql = window.matchMedia(DESKTOP_QUERY)
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])
  return isDesktop
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function readSaved(storageKey: string, min: number, max: number): number | null {
  try {
    const saved = Number(localStorage.getItem(storageKey))
    return Number.isFinite(saved) && saved > 0 ? clamp(saved, min, max) : null
  } catch {
    return null // private-browsing / storage-disabled — fall back to the default
  }
}

interface Options {
  defaultWidth: number
  min?: number
  max?: number
  /** Persists the user's chosen width across sessions. */
  storageKey: string
  /** Which side of the drag handle this panel sits on, so dragging right
   * grows a left-hand panel but shrinks a right-hand one. */
  side: 'left' | 'right'
}

/** A panel width the user can drag-resize via a handle's pointer events,
 * with a sane default and a persisted override. `isDesktop` tells the
 * caller when to actually apply the width and render the handle — below
 * the mobile breakpoint panels go full-width/stacked instead. */
export function useResizablePanel({ defaultWidth, min = 180, max = 560, storageKey, side }: Options) {
  const isDesktop = useIsDesktop()
  const [width, setWidth] = useState(() => readSaved(storageKey, min, max) ?? defaultWidth)
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null)

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      dragRef.current = { startX: e.clientX, startWidth: width }
      e.currentTarget.setPointerCapture(e.pointerId)
    },
    [width],
  )

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (!dragRef.current) return
      const dx = e.clientX - dragRef.current.startX
      const delta = side === 'left' ? dx : -dx
      setWidth(clamp(dragRef.current.startWidth + delta, min, max))
    },
    [side, min, max],
  )

  const onPointerUp = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (!dragRef.current) return
      dragRef.current = null
      e.currentTarget.releasePointerCapture(e.pointerId)
      setWidth((w) => {
        try {
          localStorage.setItem(storageKey, String(w))
        } catch {
          // private-browsing / storage-disabled — the width still applies
          // for the rest of this session, it just won't persist
        }
        return w
      })
    },
    [storageKey],
  )

  return { width, isDesktop, handleProps: { onPointerDown, onPointerMove, onPointerUp } }
}
