import { Link, Route, Routes } from 'react-router-dom'
import GraphsListPage from './pages/GraphsListPage'
import UploadPage from './pages/UploadPage'
import ExplorerPage from './pages/ExplorerPage'
import { InvestigationGraphPage } from './pages/InvestigationPage'

function App() {
  return (
    <div className="app-shell">
      <header className="top-bar">
        <Link to="/" className="top-bar__brand">
          Graph Explorer
        </Link>
        <nav className="top-bar__nav">
          <Link to="/investigation" className="top-bar__link">
            Investigation
          </Link>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<GraphsListPage />} />
        <Route path="/graphs/:graphId/upload" element={<UploadPage />} />
        <Route path="/graphs/:graphId" element={<ExplorerPage />} />
        <Route path="/investigation" element={<InvestigationGraphPage />} />
      </Routes>
    </div>
  )
}

export default App
