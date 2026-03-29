import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { api } from '../api/client';
import ThemeModeSelect from '../components/ThemeModeSelect';
import AppLogo from '../components/AppLogo';

export default function LoginPage() {
  const navigate = useNavigate();
  const [isSetup, setIsSetup] = useState(false);
  const [isForgotMode, setIsForgotMode] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setPreviewUrl(null);
    setLoading(true);

    try {
      if (isForgotMode) {
        const result = await api.requestPasswordReset(email);
        setMessage(result.message);
        setPreviewUrl(result.preview_url);
      } else if (isSetup) {
        await api.setup({ email, display_name: displayName, password });
        navigate('/');
      } else {
        await api.login(email, password);
        navigate('/');
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Something went wrong';
      setError(message);
      if (message.includes('Setup')) setIsSetup(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen px-4 py-6 md:px-8 md:py-10">
      <div className="mx-auto max-w-6xl hc-page">
        <div className="flex justify-end">
          <ThemeModeSelect />
        </div>

        <div className="hc-grid-2 items-start">
          <section className="hc-stagger">
            <p className="hc-kicker">Personal Finance System</p>
            <h1 className="hc-page-title" style={{ maxWidth: '11ch' }}>
              Your money. Fully local. Fully auditable.
            </h1>
            <p className="hc-page-subtitle" style={{ marginTop: '0.9rem', maxWidth: '56ch' }}>
              Parse statements, connect transfers, and generate tax-ready insights without sending
              personal documents to external servers.
            </p>
            <div className="hc-panel" style={{ marginTop: '1.1rem' }}>
              <div className="app-brand-title" style={{ gap: '0.7rem' }}>
                <AppLogo size={24} />
                HisabClub
              </div>
              <p className="hc-panel-sub">Poster-style interface built for high-signal finance workflows.</p>
            </div>
          </section>

          <section className="hc-panel">
            <div className="hc-panel-head">
              <div>
                <h2 className="hc-panel-title">
                  {isForgotMode ? 'Reset Password' : isSetup ? 'Create Account' : 'Sign In'}
                </h2>
                <p className="hc-panel-sub">
                  {isForgotMode
                    ? 'Request a one-time password reset link.'
                    : isSetup
                      ? 'Initialize your first local user.'
                      : 'Access your local finance workspace.'}
                </p>
              </div>
            </div>

            {error && <div className="hc-msg hc-msg-danger">{error}</div>}
            {message && <div className="hc-msg hc-msg-ok">{message}</div>}
            {previewUrl && (
              <div className="hc-panel" style={{ marginTop: '0.8rem' }}>
                <p className="hc-panel-sub">SMTP is not configured. Local preview link:</p>
                <a href={previewUrl} className="hc-btn hc-btn-primary" style={{ marginTop: '0.6rem' }}>
                  Open Reset Link
                </a>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4" style={{ marginTop: '0.9rem' }}>
              {isSetup && !isForgotMode && (
                <div>
                  <label htmlFor="display-name" className="hc-label">
                    Display Name
                  </label>
                  <input
                    id="display-name"
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    className="hc-input"
                    required
                  />
                </div>
              )}

              <div>
                <label htmlFor="email" className="hc-label">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="hc-input"
                  autoComplete="email"
                  required
                />
              </div>

              {!isForgotMode && (
                <div>
                  <label htmlFor="password" className="hc-label">
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="hc-input"
                    autoComplete={isSetup ? 'new-password' : 'current-password'}
                    required
                  />
                </div>
              )}

              <button type="submit" disabled={loading} className="hc-btn hc-btn-solid" style={{ width: '100%' }}>
                {loading
                  ? 'Working...'
                  : isForgotMode
                    ? 'Send Reset Link'
                    : isSetup
                      ? 'Create Account'
                      : 'Sign In'}
                {!isForgotMode && <ArrowRight size={16} strokeWidth={1.5} />}
              </button>
            </form>

            <div className="flex flex-wrap gap-3" style={{ marginTop: '0.8rem' }}>
              <button
                type="button"
                onClick={() => {
                  setIsForgotMode(false);
                  setIsSetup((v) => !v);
                  setError('');
                  setMessage('');
                }}
                className="hc-btn hc-btn-primary"
              >
                {isSetup ? 'Already have an account? Sign In' : 'First time? Create Account'}
              </button>

              {!isSetup && (
                <button
                  type="button"
                  onClick={() => {
                    setIsForgotMode((v) => !v);
                    setError('');
                    setMessage('');
                    setPreviewUrl(null);
                  }}
                  className="hc-btn hc-btn-ghost"
                >
                  {isForgotMode ? 'Back to Sign In' : 'Forgot password?'}
                </button>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
