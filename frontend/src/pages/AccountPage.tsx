import { useEffect, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { api } from '../api/client';

type Me = {
  id: string;
  email: string;
  display_name: string;
};

export default function AccountPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    api.getMe()
      .then((data) => {
        if (active) {
          setMe(data);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Could not load account details.');
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setMessage('');

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setSaving(true);
    try {
      const response = await api.changePassword(currentPassword, newPassword);
      setMessage(response.message);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not update password.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="hc-page">
      <section className="hc-stagger">
        <p className="hc-kicker">Account</p>
        <h1 className="hc-page-title" style={{ maxWidth: '11ch' }}>
          Identity, access, and password controls.
        </h1>
        <p className="hc-page-subtitle" style={{ marginTop: '0.9rem', maxWidth: '52ch' }}>
          Use password reset from sign-in if you are locked out. Use this page when you are
          already authenticated and want to rotate credentials without touching the database.
        </p>
      </section>

      <div className="hc-grid-2">
        <section className="hc-panel">
          <div className="hc-panel-head">
            <div>
              <h2 className="hc-panel-title">Profile</h2>
              <p className="hc-panel-sub">Current local account details.</p>
            </div>
          </div>

          {loading ? (
            <p className="hc-panel-sub">Loading account...</p>
          ) : me ? (
            <div className="space-y-4" style={{ marginTop: '0.9rem' }}>
              <div>
                <p className="hc-label">Display Name</p>
                <p>{me.display_name}</p>
              </div>
              <div>
                <p className="hc-label">Email</p>
                <p>{me.email}</p>
              </div>
            </div>
          ) : (
            <div className="hc-msg hc-msg-danger">{error || 'Could not load account details.'}</div>
          )}
        </section>

        <section className="hc-panel">
          <div className="hc-panel-head">
            <div>
              <h2 className="hc-panel-title">Change Password</h2>
              <p className="hc-panel-sub">Requires your current password.</p>
            </div>
          </div>

          {error && <div className="hc-msg hc-msg-danger">{error}</div>}
          {message && <div className="hc-msg hc-msg-ok">{message}</div>}

          <form onSubmit={handleSubmit} className="space-y-4" style={{ marginTop: '0.9rem' }}>
            <div>
              <label htmlFor="current-password" className="hc-label">
                Current Password
              </label>
              <input
                id="current-password"
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="hc-input"
                autoComplete="current-password"
                required
              />
            </div>

            <div>
              <label htmlFor="new-password" className="hc-label">
                New Password
              </label>
              <input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
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

            <button type="submit" disabled={saving} className="hc-btn hc-btn-solid" style={{ width: '100%' }}>
              {saving ? 'Updating...' : 'Update Password'}
              <ArrowRight size={16} strokeWidth={1.5} />
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
