import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Calendar, CreditCard } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { ReviewTask, Statement, StatementIntegrityResponse } from '../api/client';

export default function StatementsPage() {
  const navigate = useNavigate();
  const [statements, setStatements] = useState<Statement[]>([]);
  const [integrityById, setIntegrityById] = useState<Record<string, StatementIntegrityResponse>>({});
  const [loading, setLoading] = useState(true);
  const [openingPdfId, setOpeningPdfId] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [resolvingTaskId, setResolvingTaskId] = useState<string | null>(null);
  const [reviewTaskByStatement, setReviewTaskByStatement] = useState<Record<string, ReviewTask>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    void refreshStatements();
  }, []);

  const refreshStatements = async () => {
    try {
      const res = await api.getStatements();
      setStatements(res.items);
      const creditCardStatements = res.items.filter((s) => s.account_type === 'credit_card');
      const entries = await Promise.all(
        creditCardStatements.map(async (s) => {
          try {
            const report = await api.getStatementIntegrity(s.id);
            return [s.id, report] as const;
          } catch {
            return [s.id, null] as const;
          }
        }),
      );
      const map: Record<string, StatementIntegrityResponse> = {};
      for (const [id, report] of entries) {
        if (report) map[id] = report;
      }
      setIntegrityById(map);
      const tasks = await api.getReviewTasks('open', 200);
      const taskMap: Record<string, ReviewTask> = {};
      for (const task of tasks) {
        taskMap[task.statement_id] = task;
      }
      setReviewTaskByStatement(taskMap);
    } catch (err) {
      console.error('Failed to fetch statements:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  };

  const formatAmount = (amount: number | null) => {
    if (amount === null) return '-';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const openStatementPdf = async (statement: Statement) => {
    try {
      setOpeningPdfId(statement.id);
      const blob = await api.getStatementPdf(statement.id);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      console.error('Failed to open statement PDF:', err);
    } finally {
      setOpeningPdfId(null);
    }
  };

  const handleRereview = async (statement: Statement) => {
    try {
      setActionError(null);
      setReviewingId(statement.id);
      const updated = await api.rereviewStatement(statement.id);
      setStatements((current) => current.map((item) => (item.id === statement.id ? updated : item)));
      if (updated.account_type === 'credit_card') {
        try {
          const report = await api.getStatementIntegrity(updated.id);
          setIntegrityById((current) => ({ ...current, [updated.id]: report }));
        } catch {
          setIntegrityById((current) => {
            const next = { ...current };
            delete next[updated.id];
            return next;
          });
        }
      }
      await refreshStatements();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Re-review failed.');
    } finally {
      setReviewingId(null);
    }
  };

  const handleDelete = async (statement: Statement) => {
    if (!window.confirm(`Delete ${statement.bank_name} statement and remove its local LLM memory?`)) {
      return;
    }
    try {
      setActionError(null);
      setDeletingId(statement.id);
      await api.deleteStatement(statement.id);
      setStatements((current) => current.filter((item) => item.id !== statement.id));
      setIntegrityById((current) => {
        const next = { ...current };
        delete next[statement.id];
        return next;
      });
    } catch (err) {
      const message =
        err instanceof ApiError || err instanceof Error ? err.message : 'Delete failed.';
      setActionError(message);
    } finally {
      setDeletingId(null);
    }
  };

  const handleResolveReview = async (statement: Statement, action: 'promote' | 'ignore') => {
    const task = reviewTaskByStatement[statement.id];
    if (!task) return;
    try {
      setActionError(null);
      setResolvingTaskId(task.id);
      await api.resolveReviewTask(task.id, action);
      await refreshStatements();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Review resolution failed.';
      setActionError(message);
    } finally {
      setResolvingTaskId(null);
    }
  };

  if (loading) {
    return (
      <div className="hc-page">
        <div className="hc-panel">Loading statements...</div>
      </div>
    );
  }

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Source Documents</p>
          <h1 className="hc-page-title">Statements</h1>
          <p className="hc-page-subtitle">Track parsed periods, due values, and processing health by account.</p>
        </div>
      </header>

      {actionError && (
        <div className="hc-msg hc-msg-danger" style={{ marginBottom: '1rem' }}>
          <span>{actionError}</span>
        </div>
      )}

      {statements.length === 0 ? (
        <div className="hc-empty">
          <FileText size={40} strokeWidth={1.5} color="var(--hc-muted-fg)" />
          <h2 style={{ marginTop: '0.7rem', fontSize: '1.35rem' }}>No statements yet</h2>
          <p className="hc-page-subtitle" style={{ marginTop: '0.4rem' }}>
            Upload a statement PDF to create a new source record.
          </p>
        </div>
      ) : (
        <div className="space-y-4 hc-stagger">
          {statements.map((stmt) => (
            <article key={stmt.id} className="hc-panel">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex items-start gap-3">
                  <CreditCard size={20} strokeWidth={1.5} color="var(--hc-accent)" />
                  <div>
                    <h2 className="hc-panel-title">
                      {stmt.bank_name} {stmt.account_type === 'credit_card' ? 'Credit Card' : 'Account'}
                    </h2>
                    {stmt.pdf_filename && <p className="hc-panel-sub">{stmt.pdf_filename}</p>}
                    {stmt.account_number_masked && <p className="hc-panel-sub">{stmt.account_number_masked}</p>}
                    <p className="hc-panel-sub" style={{ marginTop: '0.35rem', display: 'flex', gap: '0.7rem', flexWrap: 'wrap' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <Calendar size={13} strokeWidth={1.5} />
                        {formatDate(stmt.statement_period_start)} - {formatDate(stmt.statement_period_end)}
                      </span>
                      <span>{stmt.transaction_count ?? 0} transactions</span>
                      {stmt.yield_rate !== null && stmt.yield_rate !== undefined && (
                        <span>Yield {(stmt.yield_rate * 100).toFixed(1)}%</span>
                      )}
                      {(stmt.quarantined_row_count ?? 0) > 0 && (
                        <span>{stmt.quarantined_row_count} quarantined</span>
                      )}
                    </p>
                  </div>
                </div>

                <div className="text-right">
                  {stmt.total_amount_due !== null && (
                    <>
                      <p className="hc-panel-sub">Total Due</p>
                      <p style={{ fontWeight: 700, fontSize: '1.2rem' }}>{formatAmount(stmt.total_amount_due)}</p>
                    </>
                  )}
                  {stmt.due_date && <p className="hc-panel-sub">Due: {formatDate(stmt.due_date)}</p>}
                </div>
              </div>

              <div className="hc-inline-actions" style={{ marginTop: '0.7rem' }}>
                <span
                  className={`hc-badge ${
                    stmt.parse_status === 'parsed'
                      ? 'hc-badge-ok'
                      : stmt.parse_status === 'failed'
                      ? 'hc-badge-danger'
                      : 'hc-badge-warn'
                  }`}
                >
                  {stmt.parse_status}
                </span>
                {stmt.reprocess_count > 1 && (
                  <span className="hc-badge hc-badge-accent">
                    {stmt.is_reprocess ? 'Reprocessed' : 'Original'} · {stmt.reprocess_count} versions
                  </span>
                )}
                {integrityById[stmt.id] && (
                  <span
                    className={`hc-badge ${
                      integrityById[stmt.id].status === 'ok' ? 'hc-badge-ok' : 'hc-badge-warn'
                    }`}
                  >
                    Integrity {integrityById[stmt.id].status.toUpperCase()}
                  </span>
                )}
                <button
                  className="hc-btn hc-btn-outline"
                  onClick={() => openStatementPdf(stmt)}
                  disabled={openingPdfId === stmt.id}
                >
                  {openingPdfId === stmt.id ? 'Opening PDF...' : 'View PDF'}
                </button>
                <button
                  className="hc-btn hc-btn-solid"
                  onClick={() => navigate(`/statements/${stmt.id}/review`)}
                >
                  Review
                </button>
                <button
                  className="hc-btn hc-btn-outline"
                  onClick={() => handleRereview(stmt)}
                  disabled={reviewingId === stmt.id || deletingId === stmt.id}
                >
                  {reviewingId === stmt.id ? 'Re-reviewing...' : 'Re-review with LLM'}
                </button>
                <button
                  className="hc-btn hc-btn-ghost"
                  onClick={() => handleDelete(stmt)}
                  disabled={deletingId === stmt.id || reviewingId === stmt.id}
                  style={{ color: 'var(--hc-accent)' }}
                >
                  {deletingId === stmt.id ? 'Deleting...' : 'Delete'}
                </button>
                {stmt.parse_status === 'review_required' && reviewTaskByStatement[stmt.id] && (
                  <>
                    <button
                      className="hc-btn hc-btn-solid"
                      onClick={() => handleResolveReview(stmt, 'promote')}
                      disabled={resolvingTaskId === reviewTaskByStatement[stmt.id].id}
                    >
                      {resolvingTaskId === reviewTaskByStatement[stmt.id].id
                        ? 'Applying...'
                        : 'Promote Quarantine'}
                    </button>
                    <button
                      className="hc-btn hc-btn-outline"
                      onClick={() => handleResolveReview(stmt, 'ignore')}
                      disabled={resolvingTaskId === reviewTaskByStatement[stmt.id].id}
                    >
                      Ignore Quarantine
                    </button>
                  </>
                )}
              </div>

              {integrityById[stmt.id] && (
                <p className="hc-panel-sub" style={{ marginTop: '0.55rem' }}>
                  Net activity: {formatAmount(integrityById[stmt.id].net_activity)} ·
                  Due gap: {formatAmount(integrityById[stmt.id].due_gap ?? 0)} ·
                  {integrityById[stmt.id].llm_reason ? ` AI: ${integrityById[stmt.id].llm_reason}` : ' AI: not available'}
                </p>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
