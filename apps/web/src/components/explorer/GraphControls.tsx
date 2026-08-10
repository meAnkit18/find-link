import { Boxes, Download, Maximize2, Minimize2, Network, RotateCw, Scan, Target, ZoomIn, ZoomOut } from 'lucide-react'
import InfoTooltip from '../common/InfoTooltip'

interface Props {
  /** Both optional — Explorer doesn't pass them and keeps today's behavior
   * unchanged (no toggle button, zoom indicator always shown). Investigation
   * passes both to enable the 2D/3D switch. */
  view?: '2d' | '3d'
  onToggleView?: () => void
  onZoomIn: () => void
  onZoomOut: () => void
  onFit: () => void
  onCenterSelected: () => void
  onRelayout: () => void
  onExportPng: () => void
  onToggleFullscreen: () => void
  isFullscreen: boolean
  hasSelection: boolean
  zoom: number
}

export default function GraphControls({
  view = '2d',
  onToggleView,
  onZoomIn,
  onZoomOut,
  onFit,
  onCenterSelected,
  onRelayout,
  onExportPng,
  onToggleFullscreen,
  isFullscreen,
  hasSelection,
  zoom,
}: Props) {
  return (
    <>
      <div
        className="graph-controls pill-toolbar pill-toolbar--vertical"
        role="toolbar"
        aria-orientation="vertical"
        aria-label="Graph controls"
      >
        <InfoTooltip text="Zoom, fit, rearrange, save as an image, or view the graph full-screen. Hover any button to see what it does." />
        {onToggleView && (
          <>
            <div className="pill-divider" />
            {/* Icon-only, like every other button here — the column stays
                narrow, and the filled pill still says which view is live. */}
            <button
              className={`pill-btn${view === '3d' ? ' pill-btn--active' : ''}`}
              title="Switch to 3D view"
              aria-label="Switch to 3D view"
              aria-pressed={view === '3d'}
              onClick={() => view !== '3d' && onToggleView()}
            >
              <Boxes size={14} />
            </button>
            <button
              className={`pill-btn${view === '2d' ? ' pill-btn--active' : ''}`}
              title="Switch to 2D view"
              aria-label="Switch to 2D view"
              aria-pressed={view === '2d'}
              onClick={() => view !== '2d' && onToggleView()}
            >
              <Network size={14} />
            </button>
          </>
        )}
        <div className="pill-divider" />
        <button className="pill-btn" title="Zoom in (+)" onClick={onZoomIn}>
          <ZoomIn size={14} />
        </button>
        <button className="pill-btn" title="Zoom out (−)" onClick={onZoomOut}>
          <ZoomOut size={14} />
        </button>
        <div className="pill-divider" />
        <button className="pill-btn" title="Fit graph to view (0)" onClick={onFit}>
          <Scan size={14} />
        </button>
        <button className="pill-btn" title="Center on selected node" onClick={onCenterSelected} disabled={!hasSelection}>
          <Target size={14} />
        </button>
        <button className="pill-btn" title="Re-run layout" onClick={onRelayout}>
          <RotateCw size={14} />
        </button>
        <div className="pill-divider" />
        <button className="pill-btn" title="Export as PNG" onClick={onExportPng}>
          <Download size={14} />
        </button>
        <button
          className="pill-btn"
          title={isFullscreen ? 'Exit fullscreen (f)' : 'Fullscreen (f)'}
          onClick={onToggleFullscreen}
        >
          {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </button>
      </div>

      {view === '2d' && (
        <div className="graph-zoom-indicator" aria-live="polite">
          {Math.round(zoom * 100)}%
        </div>
      )}
    </>
  )
}
