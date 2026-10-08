import { useCallback, useEffect, useState } from 'react'
import './App.css'
import './assets/auth.css'
import Navbar from './components/navbar'
import Chat from './components/chat'
import Login from './components/login'
import Sidebar from './components/sidebar'
import { api, clearToken, getToken, onUnauthorized } from '../api'

function App() {
  const [darkMode, setDarkMode] = useState(false)
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(Boolean(getToken()))
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)

  const logout = useCallback(() => {
    clearToken()
    setUser(null)
    setConversations([])
    setActiveId(null)
  }, [])

  // an expired/invalid token anywhere -> back to the login page
  useEffect(() => { onUnauthorized(logout) }, [logout])

  // restore the session after a page refresh
  useEffect(() => {
    if (!getToken()) return
    api('/auth/me')
      .then(setUser)
      .catch(() => {})
      .finally(() => setChecking(false))
  }, [])

  const refreshConversations = useCallback(async () => {
    const list = await api('/conversations')
    setConversations(list)
    return list
  }, [])

  const createConversation = useCallback(async () => {
    const created = await api('/conversations', { method: 'POST' })
    await refreshConversations()
    setActiveId(created.id)
  }, [refreshConversations])

  // after login: load the user's chats and open the latest (or a fresh one)
  useEffect(() => {
    if (!user) return
    ;(async () => {
      const list = await refreshConversations()
      if (list.length) setActiveId(list[0].id)
      else await createConversation()
    })().catch(console.error)
  }, [user, refreshConversations, createConversation])

  async function handleNewChat() {
    // reuse an empty chat instead of piling up blank ones
    const empty = conversations.find((c) => c.message_count === 0 && c.file_count === 0)
    if (empty) {
      setActiveId(empty.id)
      return
    }
    await createConversation()
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete this chat and the logs/metrics uploaded to it?')) return
    await api(`/conversations/${id}`, { method: 'DELETE' })
    const list = await refreshConversations()
    if (id === activeId) {
      if (list.length) setActiveId(list[0].id)
      else await createConversation()
    }
  }

  return (
    <div className={darkMode ? 'app dark' : 'app'}>
      <Navbar
        darkMode={darkMode}
        setDarkMode={setDarkMode}
        user={user}
        onLogout={logout}
      />

      {checking ? (
        <div className="auth-page"><p>Loading…</p></div>
      ) : !user ? (
        <Login onAuth={setUser} />
      ) : (
        <div className="workspace">
          <Sidebar
            conversations={conversations}
            activeId={activeId}
            onSelect={setActiveId}
            onNew={handleNewChat}
            onDelete={handleDelete}
          />
          {activeId && (
            <Chat
              key={activeId}
              conversationId={activeId}
              onChanged={refreshConversations}
            />
          )}
        </div>
      )}
    </div>
  )
}

export default App
