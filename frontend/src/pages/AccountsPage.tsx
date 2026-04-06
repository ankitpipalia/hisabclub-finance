import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { AccountInstitutionGroup, Institution } from '../api/client';

const formatAmount = (amount: number | null) =>
  amount === null
    ? '—'
    : new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 0,
      }).format(amount);

export default function AccountsPage() {
  const navigate = useNavigate();
  const [tree, setTree] = useState<AccountInstitutionGroup[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    institution_name: '',
    account_type: 'savings',
    account_number_masked: '',
    nickname: '',
  });

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [treeData, institutionRows] = await Promise.all([api.getAccountsTree(), api.getInstitutions()]);
      setTree(treeData);
      setInstitutions(institutionRows);
      if (!form.institution_name && institutionRows[0]) {
        setForm((current) => ({ ...current, institution_name: institutionRows[0].name }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load accounts.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const create = async () => {
    await api.createAccount({
      institution_name: form.institution_name,
      account_type: form.account_type,
      account_number_masked: form.account_number_masked || undefined,
      nickname: form.nickname || undefined,
    });
    setShowCreate(false);
    setForm((current) => ({ ...current, account_number_masked: '', nickname: '' }));
    await load();
  };

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Hierarchy</p>
          <h1 className="hc-page-title">Accounts</h1>
          <p className="hc-page-subtitle">
            Institution → account → statements. This is the linking layer for uploads, tax checks, and review flows.
          </p>
        </div>
        <button className="hc-btn hc-btn-solid" onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? 'Close' : 'Add Account'}
        </button>
      </header>

      {error && <div className="hc-msg hc-msg-danger">{error}</div>}

      {showCreate && (
        <section className="hc-panel">
          <div className="hc-grid-4">
            <select
              className="hc-select"
              value={form.institution_name}
              onChange={(e) => setForm((current) => ({ ...current, institution_name: e.target.value }))}
            >
              {institutions.map((institution) => (
                <option key={institution.id} value={institution.name}>
                  {institution.name}
                </option>
              ))}
            </select>
            <select
              className="hc-select"
              value={form.account_type}
              onChange={(e) => setForm((current) => ({ ...current, account_type: e.target.value }))}
            >
              <option value="savings">Savings</option>
              <option value="current">Current</option>
              <option value="credit_card">Credit Card</option>
              <option value="fd">FD</option>
              <option value="demat">Demat</option>
            </select>
            <input
              className="hc-input"
              placeholder="Masked account/card"
              value={form.account_number_masked}
              onChange={(e) => setForm((current) => ({ ...current, account_number_masked: e.target.value }))}
            />
            <input
              className="hc-input"
              placeholder="Nickname"
              value={form.nickname}
              onChange={(e) => setForm((current) => ({ ...current, nickname: e.target.value }))}
            />
          </div>
          <button className="hc-btn hc-btn-solid" style={{ marginTop: '1rem' }} onClick={() => void create()}>
            Save Account
          </button>
        </section>
      )}

      {loading ? (
        <div className="hc-panel">Loading accounts...</div>
      ) : (
        <div className="space-y-4">
          {tree.map((group) => (
            <section key={group.institution_name} className="hc-panel">
              <div className="hc-panel-head">
                <div>
                  <h2 className="hc-panel-title">{group.institution_name}</h2>
                  <p className="hc-panel-sub">{group.accounts.length} linked accounts</p>
                </div>
              </div>
              <div className="space-y-3">
                {group.accounts.map((account) => (
                  <article key={account.id} className="hc-panel" style={{ background: 'transparent' }}>
                    <div className="flex items-start justify-between gap-4 flex-wrap">
                      <div>
                        <h3 className="hc-panel-title">
                          {account.account_type.replace('_', ' ')} {account.account_number_masked ? `· ${account.account_number_masked}` : ''}
                        </h3>
                        {account.nickname && <p className="hc-panel-sub">{account.nickname}</p>}
                        <p className="hc-panel-sub" style={{ marginTop: '0.35rem' }}>
                          {account.statement_count} statements · {account.total_transactions} transactions
                        </p>
                        {account.period_coverage.length > 0 && (
                          <p className="hc-panel-sub" style={{ marginTop: '0.2rem' }}>
                            Coverage:{' '}
                            {account.period_coverage
                              .map((item) => `${item.start ?? '—'} → ${item.end ?? '—'}`)
                              .join(' · ')}
                          </p>
                        )}
                      </div>
                      <div className="text-right">
                        <p className="hc-panel-sub">Latest balance / due</p>
                        <p className="hc-stat-value" style={{ fontSize: '1.1rem' }}>
                          {formatAmount(account.latest_balance)}
                        </p>
                        <button
                          className="hc-btn hc-btn-outline"
                          style={{ marginTop: '0.7rem' }}
                          onClick={() => navigate(`/statements?account=${account.id}`)}
                        >
                          View Statements
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

