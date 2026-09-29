export default function Navbar({ darkMode, setDarkMode }) {
  return (
    <header className="navbar">
      <div>
        <h1>DevOps AI</h1>
        <p>Incident Response Assistant</p>
      </div>

      <button onClick={() => setDarkMode(!darkMode)}>
        {darkMode ? '☀️' : '🌙'}
      </button>
    </header>
  )
}