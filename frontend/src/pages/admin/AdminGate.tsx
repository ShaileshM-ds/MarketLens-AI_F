import type { ReactNode } from 'react';
import { useLogout, useMe } from '../../lib/auth';
import { SignInForm } from '../../components/SignInForm';

/** Renders children only for administrators; otherwise sign-in or an explanation. */
export function AdminGate({ children }: { children: ReactNode }) {
  const me = useMe();
  if (me.isPending) return <p className="muted">Checking your account…</p>;
  if (me.isError) return <p className="inline-error" role="alert">Couldn't check your account: {me.error.message}</p>;
  if (!me.data) return <SignInForm intro="Data administration needs an administrator account." />;
  if (me.data.role !== 'admin') {
    return (
      <section className="card empty-state">
        <h2>Administrator access required</h2>
        <p className="muted">You're signed in as {me.data.username}, which isn't an administrator account.</p>
        <SignOutButton />
      </section>
    );
  }
  return <>{children}</>;
}

export function SignOutButton() {
  const logout = useLogout();
  return (
    <button type="button" className="btn btn--secondary" onClick={() => logout.mutate()} disabled={logout.isPending}>
      Sign out
    </button>
  );
}
