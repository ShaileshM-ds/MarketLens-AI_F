import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { PageHeader } from './PageHeader';
import { SignInForm } from '../components/SignInForm';
import { safeNext, takePending } from '../lib/pendingAction';
import { watchApi } from '../lib/watch';

export function SignInPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [resumeError, setResumeError] = useState<string | null>(null);
  const next = safeNext(params.get('next'));

  const onSignedIn = async () => {
    const pending = takePending();
    if (pending) {
      try {
        await watchApi.add(pending.productId, pending.mode);
        qc.invalidateQueries({ queryKey: ['watchlist', pending.mode] });
      } catch (e) {
        setResumeError(`Signed in, but the product couldn't be added to your watchlist: ${(e as Error).message}`);
        return;
      }
    }
    navigate(next, { replace: true });
  };

  return (
    <div className="stack-lg">
      <PageHeader title="Sign in" note="Sign in to keep a watchlist, set price alerts and see notifications." />
      <SignInForm onSignedIn={onSignedIn} />
      {resumeError && (
        <p className="inline-error" role="alert">
          {resumeError}
        </p>
      )}
      <p className="muted small">Accounts are created by an administrator. There's no self sign-up yet.</p>
    </div>
  );
}
