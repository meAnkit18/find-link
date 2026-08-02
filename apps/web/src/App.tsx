import { useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import {
  AlertTriangle,
  Bot,
  Briefcase,
  ChevronLeft,
  ChevronRight,
  ListChecks,
  Network,
  ScanSearch,
  Terminal,
  Upload,
} from 'lucide-react'
import GraphsListPage from './pages/GraphsListPage'
import ExplorerPage from './pages/ExplorerPage'
import { InvestigationGraphPage } from './pages/InvestigationPage'
import CasesPage from './pages/CasesPage'
import EntitiesRiskPage from './pages/EntitiesRiskPage'
import ReviewQueuePage from './pages/ReviewQueuePage'
import AgentToolsPage from './pages/AgentToolsPage'
import ApiConsolePage from './pages/ApiConsolePage'
import IngestPage from './pages/IngestPage'
import InfoTooltip from './components/common/InfoTooltip'

const NAV = [
  { to: '/', label: 'Graphs', end: true, icon: Network },
  { to: '/ingest', label: 'Ingest', icon: Upload },
  { to: '/investigation', label: 'Investigation', icon: ScanSearch },
  { to: '/cases', label: 'Cases', icon: Briefcase },
  { to: '/entities', label: 'Entities & Risk', icon: AlertTriangle },
  { to: '/review', label: 'Review Queue', icon: ListChecks },
]

const TECHNICAL_NAV = [
  { to: '/agent', label: 'Agent Tools', icon: Bot },
  { to: '/console', label: 'API Console', icon: Terminal },
]

function App() {
  const [isCollapsed, setIsCollapsed] = useState(false)

  return (
    <div className="app-shell">
      <header className={`sidebar ${isCollapsed ? 'sidebar--collapsed' : ''}`}>
        <NavLink to="/" className="sidebar__brand">
          <span className="sidebar__logo">FL</span>
          {!isCollapsed && <span className="sidebar__brand-name">FindLink</span>}
        </NavLink>
        <nav className="sidebar__nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              title={isCollapsed ? item.label : undefined}
              className={({ isActive }) =>
                `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`
              }
            >
              <item.icon className="sidebar__link-icon" size={16} />
              {!isCollapsed && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__divider" />
        {!isCollapsed && (
          <div className="sidebar__section-label">
            Technical tools
            <InfoTooltip text="Advanced pages for developers to test the system directly — not needed for everyday investigation work." />
          </div>
        )}
        <nav className="sidebar__nav">
          {TECHNICAL_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              title={isCollapsed ? item.label : undefined}
              className={({ isActive }) =>
                `sidebar__link sidebar__link--muted ${isActive ? 'sidebar__link--active' : ''}`
              }
            >
              <item.icon className="sidebar__link-icon" size={16} />
              {!isCollapsed && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>
      </header>
      <button
        type="button"
        className={`sidebar__toggle ${isCollapsed ? 'sidebar__toggle--collapsed' : ''}`}
        onClick={() => setIsCollapsed((value) => !value)}
        aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>
      <div className="app-main">
        <Routes>
          <Route path="/" element={<GraphsListPage />} />
          <Route path="/ingest" element={<IngestPage />} />
          <Route path="/graphs/:graphId" element={<ExplorerPage />} />
          <Route path="/investigation" element={<InvestigationGraphPage />} />
          <Route path="/cases" element={<CasesPage />} />
          <Route path="/entities" element={<EntitiesRiskPage />} />
          <Route path="/review" element={<ReviewQueuePage />} />
          <Route path="/agent" element={<AgentToolsPage />} />
          <Route path="/console" element={<ApiConsolePage />} />
        </Routes>
      </div>
    </div>
  )
}

export default App
