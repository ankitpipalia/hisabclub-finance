import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { api } from '../api/client';
import ThemeModeSelect from '../components/ThemeModeSelect';
import AppLogo from '../components/AppLogo';

export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = useMemo(() => params.get('token')?.trim() || '', [params]);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (!token) {
      setError('Reset link is missing or invalid.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      const response = await api.resetPassword(token, password);
      setSuccess(response.message);
      setPassword('');
      setConfirmPassword('');
      setTimeout(() => navigate('/login'), 1200);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Could not reset password';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen px-4 py-6 md:px-8 md:py-10">
      <div className="mx-auto max-w-4xl hc-page">
        <div className="flex justify-end">
          <ThemeModeSelect />
        </div>

        <div className="mx-auto max-w-2xl">
          <section className="hc-panel">
            <div className="app-brand-title" style={{ gap: '0.7rem', marginBottom: '1rem' }}>
              <AppLogo size={24} />
              HisabClub
            </div>

            <div className="hc-panel-head">
              <div>
                <p className="hc-kicker">Account Recovery</p>
                <h1 className="hc-panel-title">Reset Password</h1>
                <p className="hc-panel-sub">
                  Set a new password for your HisabClub account.
                </p>
              </div>
            </div>

            {error && <div className="hc-msg hc-msg-danger">{error}</div>}
            {success && <div className="hc-msg hc-msg-ok">{success}</div>}

            <form onSubmit={handleSubmit} className="space-y-4" style={{ marginTop: '0.9rem' }}>
              <div>
                <label htmlFor="new-password" className="hc-label">
                  New Password
                </label>
                <input
                  id="new-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="hc-input"
                  autoComplete="new-password"
                  required
                />
              </div>

              <div>
                <label htmlFor="confirm-password" className="hc-label">
                  Confirm Password
                </label>
                <input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="hc-input"
                  autoComplete="new-password"
                  required
                />
              </div>

              <button type="submit" disabled={loading} className="hc-btn hc-btn-solid" style={{ width: '100%' }}>
                {loading ? 'Updating...' : 'Update Password'}
                <ArrowRight size={16} strokeWidth={1.5} />
              </button>
            </form>

            <button
              type="button"
              onClick={() => navigate('/login')}
              className="hc-btn hc-btn-primary"
              style={{ marginTop: '0.8rem' }}
            >
              Back to Sign In
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}
