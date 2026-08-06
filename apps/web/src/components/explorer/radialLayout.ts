/** Radial placement for expanded attribute nodes.
 *
 * Persons are laid out by the force simulation; their attributes are not.
 * An attribute belongs to a specific person, so it reads best as a ring
 * around that person — a force layout would scatter them among unrelated
 * nodes and lose that ownership. These positions are computed here and
 * pinned on the canvas, never handed to fcose.
 *
 * The exception is an attribute two expanded people *share*: that node is
 * the reason they're linked, so it sits between them rather than being
 * duplicated into both rings.
 */

export interface Position {
  x: number
  y: number
}

export interface RadialChild {
  id: string
  /** Parents this attribute hangs off. Only the expanded ones matter. */
  parentIds: string[]
  /** Deterministic ordering within a ring — same input, same layout. */
  sortKey: string
}

export interface RadialOptions {
  /** Ring radius for a small number of children. */
  baseRadius?: number
  /** Minimum arc length between two neighbouring children. */
  spacing?: number
}

const DEFAULT_BASE_RADIUS = 90
const DEFAULT_SPACING = 46

/** Stable per-parent starting angle, so two nearby people's rings don't
 * line up and interleave. Same id always yields the same offset. */
function startAngle(parentId: string): number {
  let hash = 0
  for (let i = 0; i < parentId.length; i++) hash = (hash * 31 + parentId.charCodeAt(i)) >>> 0
  return ((hash % 360) * Math.PI) / 180
}

function centroid(points: Position[]): Position {
  const sum = points.reduce((acc, p) => ({ x: acc.x + p.x, y: acc.y + p.y }), { x: 0, y: 0 })
  return { x: sum.x / points.length, y: sum.y / points.length }
}

/** Unit vector perpendicular to the line through the first two anchors —
 * the direction to fan shared children out along so they don't stack. */
function perpendicular(points: Position[]): Position {
  if (points.length < 2) return { x: 0, y: 1 }
  const dx = points[1].x - points[0].x
  const dy = points[1].y - points[0].y
  const length = Math.hypot(dx, dy)
  if (length === 0) return { x: 0, y: 1 }
  return { x: -dy / length, y: dx / length }
}

function byOrder(a: RadialChild, b: RadialChild): number {
  return a.sortKey.localeCompare(b.sortKey) || a.id.localeCompare(b.id)
}

/**
 * Positions for every child with at least one expanded parent. Children
 * whose parents are all collapsed are omitted — the caller shouldn't be
 * rendering them anyway.
 */
export function computeRadialPositions(
  parents: Map<string, Position>,
  children: RadialChild[],
  options: RadialOptions = {},
): Map<string, Position> {
  const baseRadius = options.baseRadius ?? DEFAULT_BASE_RADIUS
  const spacing = options.spacing ?? DEFAULT_SPACING
  const positions = new Map<string, Position>()

  const ownRing = new Map<string, RadialChild[]>()
  const shared: { child: RadialChild; anchors: Position[] }[] = []

  for (const child of children) {
    const anchorIds = child.parentIds.filter((id) => parents.has(id))
    if (anchorIds.length === 0) continue
    if (anchorIds.length === 1) {
      const ring = ownRing.get(anchorIds[0])
      if (ring) ring.push(child)
      else ownRing.set(anchorIds[0], [child])
    } else {
      shared.push({ child, anchors: anchorIds.map((id) => parents.get(id)!) })
    }
  }

  for (const [parentId, ring] of ownRing) {
    const origin = parents.get(parentId)!
    ring.sort(byOrder)
    // Grow the ring with its population so a person with 15 details doesn't
    // pack them on top of each other.
    const radius = Math.max(baseRadius, (ring.length * spacing) / (2 * Math.PI))
    const step = (2 * Math.PI) / ring.length
    const offset = startAngle(parentId)
    ring.forEach((child, index) => {
      const angle = offset + index * step
      positions.set(child.id, {
        x: origin.x + radius * Math.cos(angle),
        y: origin.y + radius * Math.sin(angle),
      })
    })
  }

  // Shared attributes sit at the midpoint of the people who share them.
  // Several shared attributes between the same pair would land on the exact
  // same point, so they fan out perpendicular to the line between them.
  const byMidpoint = new Map<string, { child: RadialChild; anchors: Position[] }[]>()
  for (const entry of shared) {
    const key = entry.child.parentIds.filter((id) => parents.has(id)).sort().join('|')
    const group = byMidpoint.get(key)
    if (group) group.push(entry)
    else byMidpoint.set(key, [entry])
  }

  for (const group of byMidpoint.values()) {
    group.sort((a, b) => byOrder(a.child, b.child))
    const anchors = group[0].anchors
    const middle = centroid(anchors)
    const axis = perpendicular(anchors)
    group.forEach((entry, index) => {
      const shift = (index - (group.length - 1) / 2) * spacing
      positions.set(entry.child.id, {
        x: middle.x + axis.x * shift,
        y: middle.y + axis.y * shift,
      })
    })
  }

  return positions
}
