import { useEffect, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { api } from '../api/client';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { useToast } from '../components/ui/Toast';

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
  const [wipePassword, setWipePassword] = useState('');
  const [wipeConfirmation, setWipeConfirmation] = useState('');
  const [wiping, setWiping] = useState(false);
  const [wipeError, setWipeError] = useState('');
  const [wipeMessage, setWipeMessage] = useState('');
  const [wipeConfirmOpen, setWipeConfirmOpen] = useState(false);
  const toast = useToast();

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

  const handleWipeData = async (e: React.FormEvent) => {
    e.preventDefault();
    setWipeError('');
    setWipeMessage('');

    if (!wipePassword.trim()) {
      setWipeError('Current password is required to clear data.');
      return;
    }
    if (wipeConfirmation.trim().toUpperCase() !== 'CLEAR MY DATA') {
      setWipeError('Type "CLEAR MY DATA" to confirm.');
      return;
    }
    setWipeConfirmOpen(true);
  };

  const runWipe = async () => {
    setWipeConfirmOpen(false);
    setWiping(true);
    try {
      const response = await api.clearMyData(wipePassword, wipeConfirmation);
      const summary = `${response.message} Rows deleted: ${Object.values(response.deleted_rows).reduce((acc, n) => acc + n, 0)}. Files deleted: ${response.deleted_files}.`;
      setWipeMessage(summary);
      toast.success('Your data has been cleared.');
      setWipePassword('');
      setWipeConfirmation('');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Could not clear user data.';
      setWipeError(message);
      toast.error(message);
    } finally {
      setWiping(false);
    }
  };

  return (
    <div className="hc-page">
      <ConfirmDialog
        open={wipeConfirmOpen}
        title="Permanently delete all your data?"
        description="This removes every transaction, statement, PDF, and local LLM memory tied to your account. There is no undo."
        confirmLabel="Yes, wipe everything"
        cancelLabel="Cancel"
        variant="destructive"
        onConfirm={() => void runWipe()}
        onCancel={() => setWipeConfirmOpen(false)}
      />
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

          <div style={{ marginTop: '1.2rem', borderTop: '1px solid var(--hc-border)', paddingTop: '1rem' }}>
            <h3 className="hc-panel-title" style={{ color: 'var(--hc-danger, #dc2626)' }}>
              Danger Zone
            </h3>
            <p className="hc-panel-sub" style={{ marginTop: '0.35rem' }}>
              Permanently removes all your user data from database, local PDFs, and local LLM knowledge memory.
            </p>

            {wipeError && <div className="hc-msg hc-msg-danger" style={{ marginTop: '0.8rem' }}>{wipeError}</div>}
            {wipeMessage && <div className="hc-msg hc-msg-ok" style={{ marginTop: '0.8rem' }}>{wipeMessage}</div>}

            <form onSubmit={handleWipeData} className="space-y-4" style={{ marginTop: '0.8rem' }}>
              <div>
                <label htmlFor="wipe-password" className="hc-label">
                  Current Password
                </label>
                <input
                  id="wipe-password"
                  type="password"
                  value={wipePassword}
                  onChange={(e) => setWipePassword(e.target.value)}
                  className="hc-input"
                  autoComplete="current-password"
                  required
                />
              </div>
              <div>
                <label htmlFor="wipe-confirmation" className="hc-label">
                  Type CLEAR MY DATA
                </label>
                <input
                  id="wipe-confirmation"
                  type="text"
                  value={wipeConfirmation}
                  onChange={(e) => setWipeConfirmation(e.target.value)}
                  className="hc-input"
                  placeholder="CLEAR MY DATA"
                  required
                />
              </div>
              <button
                type="submit"
                disabled={wiping}
                className="hc-btn hc-btn-outline"
                style={{ width: '100%', borderColor: '#dc2626', color: '#dc2626' }}
              >
                {wiping ? 'Clearing All Data...' : 'Delete All My Data'}
              </button>
            </form>
          </div>
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
