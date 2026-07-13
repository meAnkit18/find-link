import { NavLink, Route, Routes } from 'react-router-dom'
import GraphsListPage from './pages/GraphsListPage'
import UploadPage from './pages/UploadPage'
import ExplorerPage from './pages/ExplorerPage'
import { InvestigationGraphPage } from './pages/InvestigationPage'
import CasesPage from './pages/CasesPage'
import EntitiesRiskPage from './pages/EntitiesRiskPage'
import ReviewQueuePage from './pages/ReviewQueuePage'
import AgentToolsPage from './pages/AgentToolsPage'
import ApiConsolePage from './pages/ApiConsolePage'
import IngestPage from './pages/IngestPage'

const NAV = [
  { to: '/', label: 'Graphs', end: true },
  { to: '/ingest', label: 'Ingest' },
  { to: '/investigation', label: 'Investigation' },
  { to: '/cases', label: 'Cases' },
  { to: '/entities', label: 'Entities & Risk' },
  { to: '/review', label: 'Review Queue' },
  { to: '/agent', label: 'Agent Tools' },
  { to: '/console', label: 'API Console' },
]

function App() {
  return (
    <div className="app-shell">
      <header className="top-bar">
        <NavLink to="/" className="top-bar__brand">
          Graph Explorer <span className="badge badge-primary">testing workbench</span>
        </NavLink>
        <nav className="top-bar__nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `top-bar__link ${isActive ? 'top-bar__link--active' : ''}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<GraphsListPage />} />
        <Route path="/ingest" element={<IngestPage />} />
        <Route path="/graphs/:graphId/upload" element={<UploadPage />} />
        <Route path="/graphs/:graphId" element={<ExplorerPage />} />
        <Route path="/investigation" element={<InvestigationGraphPage />} />
        <Route path="/cases" element={<CasesPage />} />
        <Route path="/entities" element={<EntitiesRiskPage />} />
        <Route path="/review" element={<ReviewQueuePage />} />
        <Route path="/agent" element={<AgentToolsPage />} />
        <Route path="/console" element={<ApiConsolePage />} />
      </Routes>
    </div>
  )
}

export default App
