import { Link, Route, Routes } from 'react-router-dom'
import GraphsListPage from './pages/GraphsListPage'
import UploadPage from './pages/UploadPage'
import ExplorerPage from './pages/ExplorerPage'

function App() {
  return (
    <div className="app-shell">
      <header className="top-bar">
        <Link to="/" className="top-bar__brand">
          Graph Explorer
        </Link>
      </header>
      <Routes>
        <Route path="/" element={<GraphsListPage />} />
        <Route path="/graphs/:graphId/upload" element={<UploadPage />} />
        <Route path="/graphs/:graphId" element={<ExplorerPage />} />
      </Routes>
    </div>
  )
}

export default App
