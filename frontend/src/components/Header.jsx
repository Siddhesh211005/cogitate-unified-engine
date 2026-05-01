import { Link, useLocation } from 'react-router-dom'

export default function Header({ mode = 'admin', engine = null }) {
  const location = useLocation()
  const isAdmin = location.pathname.startsWith('/admin')
  const engineLabel = String(engine || '').toLowerCase() === 'schema' ? 'Schema' : engine ? 'Excel' : null

  return (
    <header className="topbar">
      <div className="brand-mark">CR</div>
      <div className="topbar-copy">
        <h1>Cogitate Rater Engine</h1>
        <p>Unified insurance rating workspace</p>
        {engineLabel && (
          <span className={`type-badge type-badge-${engine?.toLowerCase()}`}>{engineLabel}</span>
        )}
      </div>
      <span className={`workspace-pill ${isAdmin ? 'workspace-pill-admin' : 'workspace-pill-client'}`}>
        {isAdmin ? 'Admin Workspace' : 'Client Workspace'}
      </span>
      <div className="topbar-actions">
        <Link
          to="/admin"
          className={isAdmin ? 'link-btn link-btn-solid mode-active' : 'link-btn mode-inactive'}
        >
          Admin
        </Link>
        <Link
          to="/client"
          className={!isAdmin ? 'link-btn link-btn-solid mode-active' : 'link-btn mode-inactive'}
        >
          Client
        </Link>
      </div>
    </header>
  )
}
