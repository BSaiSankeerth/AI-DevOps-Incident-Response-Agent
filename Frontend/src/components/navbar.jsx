export default function Navbar({ darkMode, setDarkMode, user, onLogout }) {
  return (
    <header className="navbar">
      <div>
        <h1>DevOps AI</h1>
        <p>Incident Response Assistant</p>
      </div>

      <div className="navbar-actions">
        {user && <span className="navbar-user">👤 {user.username}</span>}
        {user && (
          <button type="button" className="logout-btn" onClick={onLogout}>
            Log out
          </button>
        )}
        <button type="button" onClick={() => setDarkMode(!darkMode)}>
          {darkMode ? '☀️' : '🌙'}
        </button>
      </div>
    </header>
  )
}