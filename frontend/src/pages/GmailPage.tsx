import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { Mail, Plus, Trash2, RefreshCw, Link as LinkIcon, AlertCircle } from 'lucide-react';
import type { GmailAllowlistAccount, GmailSyncResult } from '../api/client';

export default function GmailPage() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [accounts, setAccounts] = useState<GmailAllowlistAccount[]>([]);
  const [activeAccountId, setActiveAccountId] = useState<string | null>(null);
  const [allowlist, setAllowlist] = useState<string[]>([]);
  const [newSender, setNewSender] = useState('');
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<GmailSyncResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastSync, setLastSync] = useState<string | null>(null);

  const activeAccount = useMemo(
    () => accounts.find((a) => a.account_id === activeAccountId) ?? null,
    [accounts, activeAccountId]
  );

  const loadAccounts = async () => {
    setLoading(true);
    try {
      const res = await api.getGmailAllowlist();
      const accountList = Array.isArray(res) ? res : [];
      setAccounts(accountList);

      if (accountList.length === 0) {
        setConnected(false);
        setActiveAccountId(null);
        setAllowlist([]);
      } else {
        setConnected(true);
        setActiveAccountId((prev) => {
          if (prev && accountList.some((a) => a.account_id === prev)) return prev;
          return accountList[0].account_id;
        });
      }
    } catch {
      setConnected(false);
      setAccounts([]);
      setActiveAccountId(null);
      setAllowlist([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAccounts();
  }, []);

  useEffect(() => {
    if (!activeAccount) {
      setAllowlist([]);
      return;
    }
    setAllowlist(Array.isArray(activeAccount.senders) ? activeAccount.senders : []);
  }, [activeAccount]);

  const handleConnect = async () => {
    try {
      setError(null);
      const res = await api.connectGmail();
      window.open(res.auth_url, '_blank');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect Gmail');
    }
  };

  const updateAllowlist = async (senders: string[]) => {
    if (!activeAccountId) return;

    const res = await api.updateGmailAllowlist(activeAccountId, senders);
    setAllowlist(res.senders);
    setAccounts((prev) => prev.map((a) => (a.account_id === activeAccountId ? { ...a, senders: res.senders } : a)));
  };

  const handleAddSender = async () => {
    if (!newSender.trim()) return;
    const updated = [...allowlist, newSender.trim()];
    try {
      setError(null);
      await updateAllowlist(updated);
      setNewSender('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update allowlist');
    }
  };

  const handleRemoveSender = async (sender: string) => {
    const updated = allowlist.filter((s) => s !== sender);
    try {
      setError(null);
      await updateAllowlist(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update allowlist');
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    setError(null);
    try {
      const res = await api.syncGmail();
      setSyncResult(res);
      setLastSync(new Date().toLocaleString('en-IN'));
      await loadAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync Gmail');
    } finally {
      setSyncing(false);
    }
  };

  if (loading) {
    return (
      <div className="hc-page">
        <div className="hc-panel">Loading Gmail settings...</div>
      </div>
    );
  }

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Integrations</p>
          <h1 className="hc-page-title">Gmail</h1>
          <p className="hc-page-subtitle">Fetch statement emails and import PDFs from approved senders.</p>
        </div>
      </header>

      {error && (
        <div className="hc-msg hc-msg-danger">
          <AlertCircle size={16} strokeWidth={1.5} />
          <span>{error}</span>
          <button type="button" className="hc-btn hc-btn-primary" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      <section className="hc-panel">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <Mail size={20} strokeWidth={1.5} color={connected ? '#22c55e' : 'var(--hc-muted-fg)'} />
            <div>
              <h2 className="hc-panel-title">Gmail Connection</h2>
              <p className="hc-panel-sub" style={{ color: connected ? '#22c55e' : 'var(--hc-muted-fg)' }}>
                {connected ? 'Connected' : 'Not connected'}
              </p>
            </div>
          </div>
          <button onClick={handleConnect} className="hc-btn hc-btn-solid">
            <LinkIcon size={16} strokeWidth={1.5} />
            {connected ? 'Reconnect' : 'Connect Gmail'}
          </button>
        </div>
      </section>

      {connected && (
        <>
          <section className="hc-panel">
            <h2 className="hc-panel-title">Connected Accounts</h2>
            {accounts.length === 0 ? (
              <p className="hc-panel-sub" style={{ marginTop: '0.6rem' }}>No connected Gmail accounts found.</p>
            ) : (
              <select
                value={activeAccountId ?? ''}
                onChange={(e) => setActiveAccountId(e.target.value)}
                className="hc-select"
                style={{ marginTop: '0.7rem', maxWidth: 440 }}
              >
                {accounts.map((a) => (
                  <option key={a.account_id} value={a.account_id}>
                    {a.provider_email || a.account_id}
                  </option>
                ))}
              </select>
            )}
          </section>

          <section className="hc-panel">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <h2 className="hc-panel-title">Sync Emails</h2>
                <p className="hc-panel-sub">Fetch statement emails and save matching PDFs for parsing.</p>
                {lastSync && <p className="hc-panel-sub">Last sync: {lastSync}</p>}
              </div>
              <button onClick={handleSync} disabled={syncing} className="hc-btn hc-btn-solid">
                <RefreshCw size={16} strokeWidth={1.5} className={syncing ? 'hc-animate-spin' : undefined} />
                {syncing ? 'Syncing...' : 'Sync Now'}
              </button>
            </div>
            {syncResult && (
              <div className="hc-msg hc-msg-ok" style={{ marginTop: '0.8rem' }}>
                Sync complete: {syncResult.emails_found} email(s) found, {syncResult.pdfs_saved} PDF(s) saved.
              </div>
            )}
          </section>

          <section className="hc-panel">
            <div className="hc-panel-head">
              <div>
                <h2 className="hc-panel-title">Sender Allowlist</h2>
                <p className="hc-panel-sub">Only approved senders are scanned for statement attachments.</p>
              </div>
            </div>

            <div className="hc-inline-actions" style={{ width: '100%' }}>
              <input
                type="email"
                value={newSender}
                onChange={(e) => setNewSender(e.target.value)}
                placeholder="e.g. alerts@hdfcbank.net"
                className="hc-input"
                style={{ flex: 1, minWidth: 260 }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddSender();
                  }
                }}
              />
              <button onClick={handleAddSender} disabled={!newSender.trim()} className="hc-btn hc-btn-solid">
                <Plus size={16} strokeWidth={1.5} />
                Add
              </button>
            </div>

            {allowlist.length === 0 ? (
              <p className="hc-panel-sub" style={{ marginTop: '0.9rem' }}>No senders in allowlist yet.</p>
            ) : (
              <div style={{ marginTop: '0.7rem' }}>
                {allowlist.map((sender, idx) => (
                  <div
                    key={sender}
                    style={{
                      padding: '0.6rem 0',
                      borderTop: idx ? '1px solid var(--hc-border)' : 'none',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '0.7rem',
                    }}
                  >
                    <span>{sender}</span>
                    <button onClick={() => handleRemoveSender(sender)} className="hc-btn hc-btn-ghost" title="Remove sender">
                      <Trash2 size={15} strokeWidth={1.5} />
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {!connected && (
        <div className="hc-empty">
          <Mail size={44} strokeWidth={1.5} color="var(--hc-muted-fg)" />
          <h2 style={{ marginTop: '0.7rem', fontSize: '1.35rem' }}>Connect your Gmail</h2>
          <p className="hc-page-subtitle" style={{ marginTop: '0.4rem' }}>
            Connect Gmail to auto-ingest statement PDFs from bank notification emails.
          </p>
        </div>
      )}
    </div>
  );
}
