import InfoTooltip from '../common/InfoTooltip'

interface Props {
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
      <div className="graph-controls" role="toolbar" aria-label="Graph controls">
        <div className="row" style={{ justifyContent: 'center', margin: '2px 0' }}>
          <InfoTooltip text="Zoom, fit, rearrange, save as an image, or view the graph full-screen. Hover any button to see what it does." />
        </div>
        <div className="graph-controls__divider" />
        <button className="graph-controls__btn" title="Zoom in (+)" onClick={onZoomIn}>
          {'\u002B'}
        </button>
        <button className="graph-controls__btn" title="Zoom out (\u2212)" onClick={onZoomOut}>
          {'\u2212'}
        </button>
        <div className="graph-controls__divider" />
        <button className="graph-controls__btn" title="Fit graph to view (0)" onClick={onFit}>
          {'\u26F6'}
        </button>
        <button
          className="graph-controls__btn"
          title="Center on selected node"
          onClick={onCenterSelected}
          disabled={!hasSelection}
        >
          {'\u25CE'}
        </button>
        <button className="graph-controls__btn" title="Re-run layout" onClick={onRelayout}>
          {'\u21BB'}
        </button>
        <div className="graph-controls__divider" />
        <button className="graph-controls__btn" title="Export as PNG" onClick={onExportPng}>
          {'\u2B07'}
        </button>
        <button
          className="graph-controls__btn"
          title={isFullscreen ? 'Exit fullscreen (f)' : 'Fullscreen (f)'}
          onClick={onToggleFullscreen}
        >
          {isFullscreen ? '\u2715' : '\u26F6'}
        </button>
      </div>

      <div className="graph-zoom-indicator" aria-live="polite">
        {Math.round(zoom * 100)}%
      </div>
    </>
  )
}