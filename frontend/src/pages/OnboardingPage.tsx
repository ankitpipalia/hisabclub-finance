import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { Institution, OnboardingBank } from '../api/client';

type AccountDraft = {
  account_type: string;
  account_number_masked: string;
  nickname: string;
};

export default function OnboardingPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [selectedBanks, setSelectedBanks] = useState<string[]>([]);
  const [accountsByBank, setAccountsByBank] = useState<Record<string, AccountDraft[]>>({});
  const [profile, setProfile] = useState({
    first_name: '',
    last_name: '',
    date_of_birth: '',
    pan_number: '',
  });

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [me, status, institutionRows] = await Promise.all([
          api.getMe(),
          api.getOnboardingStatus(),
          api.getInstitutions(),
        ]);
        if (!active) return;
        setInstitutions(institutionRows);
        setProfile((current) => ({
          ...current,
          first_name: me.first_name ?? '',
          last_name: me.last_name ?? '',
        }));
        setStep(Math.max(1, status.current_step || 1));
        if (status.completed) {
          navigate('/');
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Could not load onboarding.');
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [navigate]);

  const selectedInstitutionRows = useMemo(
    () => institutions.filter((item) => selectedBanks.includes(item.name)),
    [institutions, selectedBanks],
  );

  const toggleBank = (name: string) => {
    setSelectedBanks((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
    );
    setAccountsByBank((current) => ({
      ...current,
      [name]:
        current[name] ?? [
          { account_type: 'savings', account_number_masked: '', nickname: '' },
        ],
    }));
  };

  const saveProfile = async () => {
    setSaving(true);
    setError('');
    try {
      await api.updateOnboardingProfile(profile);
      setMessage('Profile saved.');
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save profile.');
    } finally {
      setSaving(false);
    }
  };

  const saveBanks = async () => {
    setSaving(true);
    setError('');
    try {
      const banks: OnboardingBank[] = selectedBanks.map((bank) => ({
        institution_name: bank,
        accounts: (accountsByBank[bank] || [])
          .filter((item) => item.account_type)
          .map((item) => ({
            account_type: item.account_type,
            account_number_masked: item.account_number_masked || null,
            nickname: item.nickname || null,
          })),
      }));
      await api.saveOnboardingBanks({ banks });
      setMessage('Bank setup saved.');
      setStep(4);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save banks.');
    } finally {
      setSaving(false);
    }
  };

  const complete = async () => {
    setSaving(true);
    setError('');
    try {
      await api.completeOnboarding();
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not complete onboarding.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="hc-panel">Loading onboarding...</div>;
  }

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Phase 2 Setup</p>
          <h1 className="hc-page-title">Onboarding</h1>
          <p className="hc-page-subtitle">
            Register profile details and the account map the parser should link future statements to.
          </p>
        </div>
      </header>

      {error && <div className="hc-msg hc-msg-danger">{error}</div>}
      {message && <div className="hc-msg hc-msg-ok">{message}</div>}

      <section className="hc-grid-4">
        {[1, 2, 3, 4].map((index) => (
          <div key={index} className={`hc-badge ${step >= index ? 'hc-badge-accent' : ''}`}>
            Step {index}
          </div>
        ))}
      </section>

      {step <= 1 && (
        <section className="hc-panel space-y-4">
          <h2 className="hc-panel-title">Personal Info</h2>
          <div className="hc-grid-2">
            <div>
              <label className="hc-label">First Name</label>
              <input
                className="hc-input"
                value={profile.first_name}
                onChange={(e) => setProfile((p) => ({ ...p, first_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="hc-label">Last Name</label>
              <input
                className="hc-input"
                value={profile.last_name}
                onChange={(e) => setProfile((p) => ({ ...p, last_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="hc-label">Date Of Birth</label>
              <input
                className="hc-input"
                placeholder="DDMMYYYY"
                value={profile.date_of_birth}
                onChange={(e) => setProfile((p) => ({ ...p, date_of_birth: e.target.value }))}
              />
            </div>
            <div>
              <label className="hc-label">PAN</label>
              <input
                className="hc-input"
                placeholder="ABCDE1234F"
                value={profile.pan_number}
                onChange={(e) => setProfile((p) => ({ ...p, pan_number: e.target.value.toUpperCase() }))}
              />
            </div>
          </div>
          <button className="hc-btn hc-btn-solid" onClick={() => void saveProfile()} disabled={saving}>
            {saving ? 'Saving...' : 'Save And Continue'}
          </button>
        </section>
      )}

      {step === 2 && (
        <section className="hc-panel space-y-4">
          <h2 className="hc-panel-title">Select Institutions</h2>
          <div className="hc-grid-2">
            {institutions.map((institution) => (
              <button
                key={institution.id}
                type="button"
                className={`hc-btn ${selectedBanks.includes(institution.name) ? 'hc-btn-solid' : 'hc-btn-outline'}`}
                onClick={() => toggleBank(institution.name)}
              >
                {institution.name}
              </button>
            ))}
          </div>
          <button className="hc-btn hc-btn-solid" onClick={() => setStep(3)} disabled={selectedBanks.length === 0}>
            Continue To Accounts
          </button>
        </section>
      )}

      {step === 3 && (
        <section className="space-y-4">
          {selectedInstitutionRows.map((institution) => (
            <article key={institution.id} className="hc-panel">
              <div className="hc-panel-head">
                <div>
                  <h2 className="hc-panel-title">{institution.name}</h2>
                  <p className="hc-panel-sub">Add one or more accounts/cards for linking.</p>
                </div>
                <button
                  type="button"
                  className="hc-btn hc-btn-outline"
                  onClick={() =>
                    setAccountsByBank((current) => ({
                      ...current,
                      [institution.name]: [
                        ...(current[institution.name] || []),
                        { account_type: 'savings', account_number_masked: '', nickname: '' },
                      ],
                    }))
                  }
                >
                  Add Account
                </button>
              </div>
              <div className="space-y-3">
                {(accountsByBank[institution.name] || []).map((account, index) => (
                  <div key={`${institution.id}-${index}`} className="hc-grid-3">
                    <select
                      className="hc-select"
                      value={account.account_type}
                      onChange={(e) =>
                        setAccountsByBank((current) => ({
                          ...current,
                          [institution.name]: (current[institution.name] || []).map((item, itemIndex) =>
                            itemIndex === index ? { ...item, account_type: e.target.value } : item,
                          ),
                        }))
                      }
                    >
                      <option value="savings">Savings</option>
                      <option value="current">Current</option>
                      <option value="credit_card">Credit Card</option>
                      <option value="fd">FD</option>
                      <option value="demat">Demat</option>
                    </select>
                    <input
                      className="hc-input"
                      placeholder="Masked number"
                      value={account.account_number_masked}
                      onChange={(e) =>
                        setAccountsByBank((current) => ({
                          ...current,
                          [institution.name]: (current[institution.name] || []).map((item, itemIndex) =>
                            itemIndex === index ? { ...item, account_number_masked: e.target.value } : item,
                          ),
                        }))
                      }
                    />
                    <input
                      className="hc-input"
                      placeholder="Nickname"
                      value={account.nickname}
                      onChange={(e) =>
                        setAccountsByBank((current) => ({
                          ...current,
                          [institution.name]: (current[institution.name] || []).map((item, itemIndex) =>
                            itemIndex === index ? { ...item, nickname: e.target.value } : item,
                          ),
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            </article>
          ))}
          <div className="flex gap-3">
            <button className="hc-btn hc-btn-outline" onClick={() => setStep(2)}>
              Back
            </button>
            <button className="hc-btn hc-btn-solid" onClick={() => void saveBanks()} disabled={saving}>
              {saving ? 'Saving...' : 'Save Accounts'}
            </button>
          </div>
        </section>
      )}

      {step >= 4 && (
        <section className="hc-panel">
          <h2 className="hc-panel-title">Confirmation</h2>
          <p className="hc-panel-sub" style={{ marginTop: '0.6rem' }}>
            Profile and bank map are saved. Future statement uploads will attach to this hierarchy.
          </p>
          <div className="hc-grid-2" style={{ marginTop: '1rem' }}>
            <div className="hc-badge">Banks: {selectedBanks.length}</div>
            <div className="hc-badge">
              Accounts: {Object.values(accountsByBank).reduce((sum, items) => sum + items.length, 0)}
            </div>
          </div>
          <button className="hc-btn hc-btn-solid" style={{ marginTop: '1rem' }} onClick={() => void complete()} disabled={saving}>
            {saving ? 'Finishing...' : 'Go To Dashboard'}
          </button>
        </section>
      )}
    </div>
  );
}

