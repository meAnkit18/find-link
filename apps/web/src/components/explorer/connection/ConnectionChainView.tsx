import { useMemo, useRef } from 'react'
import type { ConnectionResult } from '../../../api/types'
import type { Selection } from '../detail/detailModel'
import { Callout } from '../detail/parts'
import GraphCanvas, { type GraphCanvasHandle } from '../GraphCanvas'
import { PERSON_TAG } from '../../../hooks/usePersonNetworkState'
import { pathToElements } from './connectionGraphElements'

const MAIN_TAGS = new Set([PERSON_TAG])

interface Props {
  sourceLabel: string
  targetLabel: string
  result: ConnectionResult
  selection: Selection | null
  onSelect: (selection: Selection | null) => void
}

/** The graph half of the answer to "are these two people connected, and
 * why". The reasoning behind any one person or hop lives in the detail
 * panel beside it — this is the shape of the path, not the evidence for it.
 *
 * Drawn on the same cytoscape canvas Explore uses, fed by
 * `pathToElements`: a hop between two people should look the same whether
 * you arrived at it by exploring outward or by asking about two names, and
 * the shared canvas is what guarantees that rather than a second renderer
 * kept in sync by hand. */
export default function ConnectionChainView({
  sourceLabel,
  targetLabel,
  result,
  selection,
  onSelect,
}: Props) {
  const canvasRef = useRef<GraphCanvasHandle>(null)
  const path = result.connected ? result.path : null

  const elements = useMemo(
    () => pathToElements(path?.persons ?? [], path?.links ?? []),
    [path],
  )

  if (!result.connected) {
    return (
      <div className="connection-chain">
        <Callout>
          No connection found between <strong>{sourceLabel}</strong> and{' '}
          <strong>{targetLabel}</strong> within {result.max_degree_searched} degrees of
          separation.
        </Callout>
      </div>
    )
  }

  return (
    // `explorer-center` rather than a class of its own: this is the same
    // canvas in the same slot Explore puts it in, including the mobile
    // min-height rule that stops a flex canvas collapsing to nothing.
    <div className="explorer-center">
      <GraphCanvas
        ref={canvasRef}
        nodes={elements.nodes}
        edges={elements.edges}
        selectedVid={selection?.kind === 'person' ? selection.id : null}
        rootVid={result.source_id}
        mainTags={MAIN_TAGS}
        onSelect={(vid) => onSelect(vid ? { kind: 'person', id: vid } : null)}
        onSelectEdge={(source, target) => onSelect({ kind: 'link', source, target })}
        selectedEdge={
          selection?.kind === 'link'
            ? { source: selection.source, target: selection.target }
            : null
        }
        // Nothing to fan out: this mode projects a path between two people,
        // not a person's own attributes, so a tap selects and never expands.
        onToggleExpand={() => {}}
        // A path is a few edges that exist to state their own reason, so
        // the hop labels stay on rather than waiting for a hover.
        alwaysLabelEdges
      />
    </div>
  )
}
