import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { api } from '../api/client';
import type { StatementAnnotation, StatementReview, StatementReviewTransaction } from '../api/client';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

const formatAmount = (amount: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);

function getTransactionPageHint(txn: StatementReviewTransaction | null): number | null {
  if (!txn) return null;
  if (txn.page_number) return txn.page_number;
  const annotatedPage = [...txn.annotations]
    .reverse()
    .find((annotation) => typeof annotation.page_number === 'number' && annotation.page_number > 0)?.page_number;
  return annotatedPage ?? null;
}

export default function StatementReviewPage() {
  const { statementId } = useParams();
  const navigate = useNavigate();
  const [review, setReview] = useState<StatementReview | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [selectedTxnId, setSelectedTxnId] = useState<string | null>(null);
  const [annotationText, setAnnotationText] = useState('');
  const [annotationType, setAnnotationType] = useState('comment');
  const [annotationPageNumber, setAnnotationPageNumber] = useState('');
  const [applyChanges, setApplyChanges] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1.1);

  const selectedTxn = useMemo(
    () => review?.transactions.find((txn) => txn.id === selectedTxnId) ?? review?.transactions[0] ?? null,
    [review, selectedTxnId],
  );

  const load = async () => {
    if (!statementId) return;
    setLoading(true);
    setError('');
    try {
      const [reviewPayload, pdfBlob] = await Promise.all([
        api.getStatementReview(statementId),
        api.getStatementPdf(statementId),
      ]);
      setReview(reviewPayload);
      const firstTxnId = reviewPayload.transactions[0]?.id ?? null;
      setSelectedTxnId(firstTxnId);
      const hintedPage = getTransactionPageHint(reviewPayload.transactions[0] ?? null);
      setPageNumber(hintedPage ?? 1);
      setAnnotationPageNumber(hintedPage ? String(hintedPage) : '');
      const url = URL.createObjectURL(pdfBlob);
      setPdfUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return url;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load statement review.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  useEffect(() => {
    const hintedPage = getTransactionPageHint(selectedTxn);
    if (hintedPage) {
      setPageNumber(hintedPage);
      setAnnotationPageNumber(String(hintedPage));
    } else {
      setAnnotationPageNumber('');
    }
  }, [selectedTxn]);

  const submitAnnotation = async () => {
    if (!statementId || !selectedTxn || !annotationText.trim()) return;
    setBusy(true);
    try {
      const created = await api.annotateStatementTransaction(statementId, selectedTxn.id, {
        annotation_type: annotationType,
        content: annotationText.trim(),
        apply_changes: applyChanges,
        page_number: annotationPageNumber.trim() ? Number(annotationPageNumber) : undefined,
      });
      setReview((current) => {
        if (!current) return current;
        const nextTransactions = current.transactions.map((txn) =>
          txn.id === selectedTxn.id
            ? { ...txn, annotations: [...txn.annotations, created as StatementAnnotation] }
            : txn,
        );
        return {
          ...current,
          transactions: nextTransactions,
          annotations: [...current.annotations, created],
        };
      });
      setAnnotationText('');
      setApplyChanges(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save annotation.');
    } finally {
      setBusy(false);
    }
  };

  const verifyTxn = async (txn: StatementReviewTransaction) => {
    if (!statementId) return;
    setBusy(true);
    try {
      await api.verifyStatementTransaction(statementId, txn.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not verify transaction.');
    } finally {
      setBusy(false);
    }
  };

  const bulkVerify = async () => {
    if (!statementId) return;
    setBusy(true);
    try {
      await api.bulkVerifyStatement(statementId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not bulk verify statement.');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="hc-panel">Loading statement review...</div>;
  }

  if (!review) {
    return <div className="hc-msg hc-msg-danger">{error || 'Statement review not available.'}</div>;
  }

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Review</p>
          <h1 className="hc-page-title">{review.statement.bank_name} Statement</h1>
          <p className="hc-page-subtitle">
            {review.statement.pdf_filename ?? 'Source PDF'} · {review.transactions.length} parsed transactions
          </p>
        </div>
        <div className="flex gap-3">
          <button className="hc-btn hc-btn-outline" onClick={() => navigate('/statements')}>
            Back
          </button>
          <button className="hc-btn hc-btn-solid" onClick={() => void bulkVerify()} disabled={busy}>
            Bulk Verify
          </button>
        </div>
      </header>

      {error && <div className="hc-msg hc-msg-danger">{error}</div>}

      <section className="hc-grid-2" style={{ alignItems: 'start' }}>
        <div className="hc-panel" style={{ minHeight: '70vh' }}>
          <div className="flex items-center justify-between gap-3" style={{ marginBottom: '0.8rem', flexWrap: 'wrap' }}>
            <div className="flex gap-2">
              <button
                className="hc-btn hc-btn-outline"
                onClick={() => setPageNumber((current) => Math.max(1, current - 1))}
                disabled={pageNumber <= 1}
              >
                Prev Page
              </button>
              <button
                className="hc-btn hc-btn-outline"
                onClick={() => setPageNumber((current) => Math.min(numPages || current + 1, current + 1))}
                disabled={!numPages || pageNumber >= numPages}
              >
                Next Page
              </button>
            </div>
            <div className="flex gap-2 items-center">
              <button className="hc-btn hc-btn-outline" onClick={() => setZoom((current) => Math.max(0.8, current - 0.1))}>
                -
              </button>
              <div className="hc-badge">Page {pageNumber}{numPages ? ` / ${numPages}` : ''}</div>
              <div className="hc-badge">Zoom {(zoom * 100).toFixed(0)}%</div>
              <button className="hc-btn hc-btn-outline" onClick={() => setZoom((current) => Math.min(2, current + 0.1))}>
                +
              </button>
            </div>
          </div>

          {pdfUrl ? (
            <div style={{ display: 'flex', justifyContent: 'center', overflow: 'auto', maxHeight: '68vh' }}>
              <Document
                file={pdfUrl}
                loading={<p className="hc-panel-sub">Loading PDF…</p>}
                onLoadSuccess={({ numPages: loadedPages }) => {
                  setNumPages(loadedPages);
                  setPageNumber((current) => Math.min(Math.max(current, 1), loadedPages));
                }}
                onLoadError={(err) => setError(err.message || 'Could not render PDF.')}
              >
                <Page pageNumber={pageNumber} scale={zoom} />
              </Document>
            </div>
          ) : (
            <p className="hc-panel-sub">PDF preview unavailable.</p>
          )}
        </div>

        <div className="space-y-3">
          <section className="hc-panel" style={{ maxHeight: '38vh', overflowY: 'auto' }}>
            <div className="space-y-2">
              {review.transactions.map((txn) => (
                <button
                  key={txn.id}
                  type="button"
                  className="hc-panel"
                  style={{
                    width: '100%',
                    background: selectedTxn?.id === txn.id ? 'var(--hc-muted)' : 'transparent',
                    textAlign: 'left',
                  }}
                  onClick={() => setSelectedTxnId(txn.id)}
                >
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p style={{ fontWeight: 600 }}>{txn.description_raw}</p>
                      <p className="hc-panel-sub">
                        {txn.transaction_date} · {txn.direction} · confidence {(txn.confidence * 100).toFixed(0)}%
                      </p>
                    </div>
                    <div className={`hc-badge ${txn.is_quarantined ? 'hc-badge-warn' : 'hc-badge-ok'}`}>
                      {formatAmount(txn.amount)}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </section>

          {selectedTxn && (
            <section className="hc-panel">
              <div className="hc-panel-head">
                <div>
                  <h2 className="hc-panel-title">Transaction Detail</h2>
                  <p className="hc-panel-sub">{selectedTxn.description_raw}</p>
                </div>
                <div className="flex gap-2">
                  {getTransactionPageHint(selectedTxn) && (
                    <button
                      className="hc-btn hc-btn-outline"
                      onClick={() => setPageNumber(getTransactionPageHint(selectedTxn) || 1)}
                    >
                      Jump To Page
                    </button>
                  )}
                  <button className="hc-btn hc-btn-outline" onClick={() => void verifyTxn(selectedTxn)} disabled={busy}>
                    Verify
                  </button>
                </div>
              </div>
              <div className="hc-grid-2">
                <div className="hc-badge">{selectedTxn.transaction_date}</div>
                <div className="hc-badge">{formatAmount(selectedTxn.amount)}</div>
                <div className="hc-badge">
                  Page {getTransactionPageHint(selectedTxn) ?? 'not linked'}
                </div>
              </div>
              <div className="space-y-2" style={{ marginTop: '1rem' }}>
                {selectedTxn.annotations.map((annotation) => (
                  <div key={annotation.id} className="hc-panel" style={{ background: 'transparent' }}>
                    <div className="flex gap-2 items-center" style={{ flexWrap: 'wrap' }}>
                      <div className="hc-badge">{annotation.annotation_type}</div>
                      {annotation.page_number && <div className="hc-badge">Page {annotation.page_number}</div>}
                    </div>
                    <p style={{ marginTop: '0.4rem', whiteSpace: 'pre-wrap' }}>{annotation.content}</p>
                    {annotation.llm_response && (
                      <p className="hc-panel-sub" style={{ marginTop: '0.4rem', whiteSpace: 'pre-wrap' }}>
                        {annotation.llm_response}
                      </p>
                    )}
                  </div>
                ))}
              </div>
              <div className="space-y-3" style={{ marginTop: '1rem' }}>
                <select className="hc-select" value={annotationType} onChange={(e) => setAnnotationType(e.target.value)}>
                  <option value="comment">Comment</option>
                  <option value="flag">Flag</option>
                  <option value="correction_request">Ask LLM To Fix</option>
                  <option value="verification">Verification Note</option>
                </select>
                <input
                  className="hc-input"
                  value={annotationPageNumber}
                  onChange={(e) => setAnnotationPageNumber(e.target.value)}
                  placeholder="Linked page number (optional)"
                  inputMode="numeric"
                />
                <textarea
                  className="hc-textarea"
                  value={annotationText}
                  onChange={(e) => setAnnotationText(e.target.value)}
                  placeholder="Add a note or request a correction."
                  style={{ minHeight: '120px' }}
                />
                <label className="hc-panel-sub" style={{ display: 'inline-flex', gap: '0.5rem', alignItems: 'center' }}>
                  <input type="checkbox" checked={applyChanges} onChange={(e) => setApplyChanges(e.target.checked)} />
                  Apply LLM changes immediately
                </label>
                <button className="hc-btn hc-btn-solid" onClick={() => void submitAnnotation()} disabled={busy || !annotationText.trim()}>
                  {busy ? 'Saving...' : 'Save Annotation'}
                </button>
              </div>
            </section>
          )}
        </div>
      </section>
    </div>
  );
}
