import { useState } from 'react';
import { api, setToken } from '../../api';

export default function Login({ onAuth }) {
    const [mode, setMode] = useState('login');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);

    async function handleSubmit(event) {
        event.preventDefault();
        setError('');
        setBusy(true);
        try {
            const result = await api(mode === 'login' ? '/auth/login' : '/auth/register', {
                method: 'POST',
                json: { username: username.trim(), password },
            });
            setToken(result.access_token);
            onAuth(result.user);
        } catch (err) {
            setError(err.message);
        } finally {
            setBusy(false);
        }
    }

    const isLogin = mode === 'login';

    return (
        <div className="auth-page">
            <form className="auth-card" onSubmit={handleSubmit}>
                <h2>{isLogin ? 'Log in' : 'Create account'}</h2>
                <p>Your runbooks, logs and chats are private to your account.</p>

                <input
                    type="text"
                    placeholder="Username"
                    autoComplete="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    minLength={3}
                />
                <input
                    type="password"
                    placeholder="Password (min 6 characters)"
                    autoComplete={isLogin ? 'current-password' : 'new-password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={6}
                />

                {error && <div className="auth-error">{error}</div>}

                <button type="submit" className="auth-submit" disabled={busy}>
                    {busy ? 'Please wait…' : isLogin ? 'Log in' : 'Sign up'}
                </button>

                <button
                    type="button"
                    className="auth-switch"
                    onClick={() => { setMode(isLogin ? 'register' : 'login'); setError(''); }}
                >
                    {isLogin ? "No account? Sign up" : 'Already have an account? Log in'}
                </button>
            </form>
        </div>
    );
}
