import { useState, type FormEvent } from 'react';
import { useLogin, type Me } from '../lib/auth';

/** Username + password sign-in. Credentials go only to the app's own /api/v1/auth/login. */
export function SignInForm({ intro, onSignedIn }: { intro?: string; onSignedIn?: (me: Me) => void }) {
  const login = useLogin();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate({ username, password }, { onSuccess: (me) => onSignedIn?.(me) });
  };

  return (
    <section className="card form-card" aria-labelledby="signin-title">
      <h2 id="signin-title">Sign in</h2>
      {intro && <p className="muted">{intro}</p>}
      <form onSubmit={submit} className="form-stack">
        <label className="field">
          <span className="field__label">Username</span>
          <input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label className="field">
          <span className="field__label">Password</span>
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {login.isError && (
          <p className="inline-error" role="alert">
            {login.error.message}
          </p>
        )}
        <button type="submit" className="btn btn--primary" disabled={login.isPending}>
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </section>
  );
}
