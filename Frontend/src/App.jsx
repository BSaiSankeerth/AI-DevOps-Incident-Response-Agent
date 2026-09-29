
import { useState } from 'react'
import './App.css'
import Navbar from './components/navbar'
import Chat from './components/chat'

function App() {
  const [darkMode, setDarkMode] = useState(false)

  return (
    <div className={darkMode ? 'app dark' : 'app'}>
      <Navbar
        darkMode={darkMode}
        setDarkMode={setDarkMode}
      />
      <Chat />
    </div>
  )
}

export default App