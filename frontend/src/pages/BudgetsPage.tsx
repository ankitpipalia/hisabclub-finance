import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { BudgetWithSpent, Category } from '../api/client';
import { Plus, Trash2, Wallet } from 'lucide-react';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';

const formatAmount = (amount: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);

function progressColor(percentage: number): string {
  if (percentage > 90) return 'var(--hc-danger)';
  if (percentage > 75) return 'var(--hc-warn)';
  return '#22c55e';
}

function progressBg(percentage: number): string {
  if (percentage > 90) return 'color-mix(in srgb, var(--hc-danger) 20%, transparent)';
  if (percentage > 75) return 'color-mix(in srgb, var(--hc-warn) 20%, transparent)';
  return 'color-mix(in srgb, #22c55e 20%, transparent)';
}

export default function BudgetsPage() {
  const [budgets, setBudgets] = useState<BudgetWithSpent[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formCategoryId, setFormCategoryId] = useState('');
  const [formAmount, setFormAmount] = useState('');
  const [formPeriod, setFormPeriod] = useState('monthly');
  const [submitting, setSubmitting] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const [budgetsRes, categoriesRes] = await Promise.all([api.getBudgets(), api.getCategories()]);
      setBudgets(budgetsRes);
      setCategories(categoriesRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load budgets');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formAmount) return;

    setSubmitting(true);
    try {
      await api.createBudget({
        category_id: formCategoryId || undefined,
        amount_limit: parseFloat(formAmount),
        period: formPeriod,
      });
      setShowForm(false);
      setFormCategoryId('');
      setFormAmount('');
      setFormPeriod('monthly');
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create budget');
    } finally {
      setSubmitting(false);
    }
  };

  const requestDelete = (id: string) => setPendingDeleteId(id);

  const cancelDelete = () => setPendingDeleteId(null);

  const confirmDelete = async () => {
    const id = pendingDeleteId;
    if (!id) return;
    setPendingDeleteId(null);
    try {
      await api.deleteBudget(id);
      setBudgets((prev) => prev.filter((b) => b.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete budget');
    }
  };

  if (loading) {
    return (
      <div className="hc-page">
        <div className="hc-panel">Loading budgets...</div>
      </div>
    );
  }

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Controls</p>
          <h1 className="hc-page-title">Budgets</h1>
          <p className="hc-page-subtitle">Set guardrails per category and monitor usage drift in real time.</p>
        </div>
        <button onClick={() => setShowForm((v) => !v)} className="hc-btn hc-btn-solid">
          <Plus size={16} strokeWidth={1.5} />
          {showForm ? 'Close' : 'Add Budget'}
        </button>
      </header>

      {error && (
        <div className="hc-msg hc-msg-danger">
          <span>{error}</span>
          <button type="button" className="hc-btn hc-btn-primary" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {showForm && (
        <section className="hc-panel">
          <h2 className="hc-panel-title">New Budget</h2>
          <form onSubmit={handleCreate} className="hc-grid-3" style={{ marginTop: '0.8rem' }}>
            <div>
              <label className="hc-label">Category</label>
              <select
                value={formCategoryId}
                onChange={(e) => setFormCategoryId(e.target.value)}
                className="hc-select"
              >
                <option value="">Overall (all categories)</option>
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="hc-label">Amount Limit</label>
              <input
                type="number"
                value={formAmount}
                onChange={(e) => setFormAmount(e.target.value)}
                placeholder="e.g. 10000"
                min="1"
                required
                className="hc-input"
              />
            </div>
            <div>
              <label className="hc-label">Period</label>
              <select
                value={formPeriod}
                onChange={(e) => setFormPeriod(e.target.value)}
                className="hc-select"
              >
                <option value="monthly">Monthly</option>
                <option value="weekly">Weekly</option>
                <option value="yearly">Yearly</option>
              </select>
            </div>
            <div className="hc-inline-actions" style={{ gridColumn: '1 / -1' }}>
              <button type="submit" disabled={submitting} className="hc-btn hc-btn-solid">
                {submitting ? 'Creating...' : 'Create Budget'}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="hc-btn hc-btn-outline">
                Cancel
              </button>
            </div>
          </form>
        </section>
      )}

      {budgets.length === 0 ? (
        <div className="hc-empty">
          <Wallet size={44} strokeWidth={1.5} color="var(--hc-muted-fg)" />
          <h2 style={{ marginTop: '0.7rem', fontSize: '1.35rem' }}>No budgets yet</h2>
          <p className="hc-page-subtitle" style={{ marginTop: '0.4rem' }}>
            Create your first spending guardrail.
          </p>
        </div>
      ) : (
        <div className="space-y-4 hc-stagger">
          {budgets.map((budget) => {
            const pct = Math.max(0, Math.min(budget.percentage_used, 100));
            const color = progressColor(budget.percentage_used);
            const bg = progressBg(budget.percentage_used);

            return (
              <section key={budget.id} className="hc-panel">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <h2 className="hc-panel-title">{budget.category_name || 'Overall'}</h2>
                    <p className="hc-panel-sub" style={{ textTransform: 'capitalize' }}>{budget.period}</p>
                  </div>
                  <div className="text-right">
                    <p style={{ fontWeight: 600 }}>
                      {formatAmount(budget.spent_amount)} / {formatAmount(budget.amount_limit)}
                    </p>
                    <p className="hc-panel-sub">{formatAmount(budget.remaining)} remaining</p>
                  </div>
                </div>

                <div style={{ marginTop: '0.7rem' }}>
                  <div style={{ height: 12, background: bg, position: 'relative' }}>
                    <div
                      style={{
                        height: '100%',
                        width: `${pct}%`,
                        background: color,
                        transition: 'width 200ms var(--hc-ease)',
                      }}
                    />
                  </div>
                  <p className="hc-panel-sub" style={{ marginTop: '0.35rem', color }}>
                    {budget.percentage_used.toFixed(0)}% used
                  </p>
                </div>

                <div className="hc-inline-actions" style={{ marginTop: '0.35rem' }}>
                  <button onClick={() => requestDelete(budget.id)} className="hc-btn hc-btn-ghost" title="Delete budget">
                    <Trash2 size={14} strokeWidth={1.5} />
                    Delete
                  </button>
                </div>
              </section>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title="Delete this budget?"
        description="The budget will be removed permanently. Spending history is unaffected."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={confirmDelete}
        onCancel={cancelDelete}
      />
    </div>
  );
}
