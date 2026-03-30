import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2,
  FileText,
  Loader2,
  Sparkles,
  Upload,
  XCircle,
} from 'lucide-react';
import { api } from '../api/client';

const BANK_OPTIONS = [
  { value: '', label: 'Auto Detect' },
  { value: 'SBI', label: 'State Bank of India' },
  { value: 'HDFC', label: 'HDFC Bank' },
  { value: 'ICICI', label: 'ICICI Bank' },
  { value: 'AXIS', label: 'Axis Bank' },
  { value: 'KOTAK', label: 'Kotak Mahindra Bank' },
  { value: 'PNB', label: 'Punjab National Bank' },
  { value: 'BOB', label: 'Bank of Baroda' },
  { value: 'CANARA', label: 'Canara Bank' },
  { value: 'UNION', label: 'Union Bank of India' },
  { value: 'INDIAN', label: 'Indian Bank' },
  { value: 'BOI', label: 'Bank of India' },
  { value: 'IDBI', label: 'IDBI Bank' },
  { value: 'INDUSIND', label: 'IndusInd Bank' },
  { value: 'YES', label: 'Yes Bank' },
  { value: 'FEDERAL', label: 'Federal Bank' },
] as const;

const DOCUMENT_TYPE_OPTIONS = [
  { value: 'auto', label: 'Auto Detect (Bank/Tax)' },
  { value: 'bank_statement', label: 'Bank account statement' },
  { value: 'credit_card_statement', label: 'Credit card statement' },
  { value: 'demat_holdings', label: 'Demat holdings / balance statement' },
  { value: 'demat_trade_report', label: 'Demat trade report / contract notes' },
  { value: 'demat_tax_report', label: 'Demat P&L / capital gains report' },
  { value: 'dividend_report', label: 'Dividend report' },
  { value: 'interest_certificate', label: 'Interest certificate' },
  { value: 'fd_report', label: 'FD list/report' },
  { value: 'tax_challan', label: 'Income-tax challan / direct tax ack' },
  { value: 'ppf_statement', label: 'PPF statement' },
  { value: 'tax_form', label: 'Tax form (Form-16/12BB)' },
] as const;

type DocumentTypeHint = (typeof DOCUMENT_TYPE_OPTIONS)[number]['value'];
const SUPPORTED_UPLOAD_EXTS = ['.pdf', '.xlsx', '.xls', '.csv'];

type UploadItem = {
  id: string;
  file: File;
  fileLabel: string;
  password: string;
  bankHint: string;
  documentTypeHint: DocumentTypeHint;
  forceReprocess?: boolean;
};

type UploadNotification = {
  id: string;
  fileName: string;
  status: 'queued' | 'reviewing' | 'success' | 'error';
  message: string;
  bankName?: string | null;
  accountType?: string | null;
  canReprocess?: boolean;
};

type SelectionStats = {
  picked: number;
  acceptedSupported: number;
  skippedUnsupported: number;
};

export default function UploadPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [notifications, setNotifications] = useState<UploadNotification[]>([]);
  const [selectionStats, setSelectionStats] = useState<SelectionStats | null>(null);

  const queuedCount = useMemo(
    () => notifications.filter((item) => item.status === 'reviewing' || item.status === 'queued').length,
    [notifications],
  );
  const successCount = useMemo(
    () => notifications.filter((item) => item.status === 'success').length,
    [notifications],
  );
  const errorCount = useMemo(
    () => notifications.filter((item) => item.status === 'error').length,
    [notifications],
  );

  useEffect(() => {
    let cancelled = false;
    const loadRecentUploads = async () => {
      try {
        const recent = await api.getRecentUploads(100);
        if (cancelled) return;
        setNotifications((current) => {
          const liveIds = new Set(current.map((item) => item.id));
          const recentNotifications = recent
            .filter((item) => !liveIds.has(item.pdf_id))
            .map((item) => ({
              id: item.pdf_id,
              fileName: item.file_name,
              status: normalizeReviewStatus(item.status),
              message: item.message,
              bankName: item.bank_name,
              accountType: item.account_type,
            }));
          return [...current, ...recentNotifications];
        });
      } catch (err) {
        console.error('Failed to load recent uploads', err);
      }
    };
    void loadRecentUploads();
    return () => {
      cancelled = true;
    };
  }, []);

  const addFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const selected = Array.from(fileList);
    const nextItems = selected
      .filter((file) => isSupportedUploadFile(file))
      .map((file) => {
        const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || '';
        return {
          id: `${file.name}-${file.lastModified}-${file.size}-${crypto.randomUUID()}`,
          file,
          fileLabel: relativePath || file.name,
          password: '',
          bankHint: '',
          documentTypeHint: 'auto' as DocumentTypeHint,
        };
      });
    setSelectionStats({
      picked: selected.length,
      acceptedSupported: nextItems.length,
      skippedUnsupported: Math.max(0, selected.length - nextItems.length),
    });
    if (nextItems.length === 0) return;
    setItems((current) => [...current, ...nextItems]);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    addFiles(e.dataTransfer.files);
  };

  const updateItem = (id: string, patch: Partial<UploadItem>) => {
    setItems((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };

  const removeItem = (id: string) => {
    setItems((current) => current.filter((item) => item.id !== id));
  };

  const updateNotification = (id: string, patch: Partial<UploadNotification>) => {
    setNotifications((current) =>
      current.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)),
    );
  };

  const remapNotificationId = (fromId: string, toId: string, fileName: string) => {
    if (!toId || toId === fromId) return;
    setNotifications((current) => {
      const source = current.find((entry) => entry.id === fromId);
      const retained = current.filter((entry) => entry.id !== fromId && entry.id !== toId);
      if (!source) return retained;
      return [{ ...source, id: toId, fileName }, ...retained];
    });
  };

  const isReviewingStatus = (status: string) =>
    ['reviewing', 'queued', 'uploaded', 'classifying', 'extracting', 'validating'].includes(
      status.toLowerCase(),
    );

  const startNotification = (item: UploadItem) => {
    setNotifications((current) => [
      {
        id: item.id,
        fileName: item.fileLabel,
        status: 'reviewing',
        message: 'Document is under review by the local LLM. Please wait. We will notify you once it completes.',
      },
      ...current.filter((entry) => entry.id !== item.id),
    ]);
  };

  const executeUploadQueue = async () => {
    if (items.length === 0 || uploading) return;
    setUploading(true);
    const queueSnapshot = [...items];
    const batchSize = 20;
    for (const item of queueSnapshot) {
      startNotification(item);
    }
    try {
      for (let start = 0; start < queueSnapshot.length; start += batchSize) {
        const batch = queueSnapshot.slice(start, start + batchSize);
        let response;
        try {
          // eslint-disable-next-line no-await-in-loop
          response = await api.uploadPdfs(
            batch.map((item) => ({
              file: item.file,
              password: item.password || undefined,
              bank_hint: item.bankHint || undefined,
              account_type_hint: toAccountTypeHint(item.documentTypeHint),
              document_type_hint: item.documentTypeHint,
              force_reprocess: item.forceReprocess ?? false,
            })),
          );
        } catch (batchErr: unknown) {
          const message = batchErr instanceof Error ? batchErr.message : 'Upload failed.';
          batch.forEach((item) => {
            updateNotification(item.id, { status: 'error', message });
          });
          continue;
        }

        response.items.forEach((serverItem, index) => {
          const localItem = batch[index];
          if (!localItem) return;
          const serverId = serverItem.document_id || serverItem.pdf_id || localItem.id;
          remapNotificationId(localItem.id, serverId, localItem.fileLabel);

          if (serverItem.status === 'duplicate') {
            updateNotification(serverId, {
              status: 'error',
              message: serverItem.message || 'This document already exists. Enable reprocess.',
              canReprocess: true,
              bankName: serverItem.bank_name,
              accountType: serverItem.account_type,
            });
            updateItem(localItem.id, { forceReprocess: true });
            return;
          }
          if (isReviewingStatus(serverItem.status)) {
            updateNotification(serverId, {
              status: 'reviewing',
              message: serverItem.message,
              bankName: serverItem.bank_name,
              accountType: serverItem.account_type,
            });
            removeItem(localItem.id);
            return;
          }
          if (serverItem.status === 'success' || serverItem.status === 'parsed') {
            updateNotification(serverId, {
              status: 'success',
              message: serverItem.message,
              bankName: serverItem.bank_name,
              accountType: serverItem.account_type,
              canReprocess: false,
            });
            removeItem(localItem.id);
            return;
          }
          updateNotification(serverId, {
            status: 'error',
            message: serverItem.message || 'Upload failed.',
            bankName: serverItem.bank_name,
            accountType: serverItem.account_type,
          });
        });
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Upload failed.';
      queueSnapshot.forEach((item) => {
        updateNotification(item.id, { status: 'error', message });
      });
    } finally {
      setUploading(false);
    }
  };

  const notificationIcon = (status: UploadNotification['status']) => {
    if (status === 'reviewing' || status === 'queued') {
      return <Loader2 size={16} className="hc-animate-spin" strokeWidth={1.5} />;
    }
    if (status === 'success') {
      return <CheckCircle2 size={16} strokeWidth={1.5} />;
    }
    return <XCircle size={16} strokeWidth={1.5} />;
  };

  return (
    <div className="hc-page" style={{ maxWidth: '1120px' }}>
      <div className="hc-page-header">
        <div>
          <p className="hc-kicker">Statement Intake</p>
          <h1 className="hc-page-title">Upload Documents</h1>
          <p className="hc-page-subtitle">
            Queue one or more documents, choose bank or tax document type per file, and let the local
            LLM route each document.
          </p>
        </div>
      </div>

      <div className="hc-grid-2" style={{ alignItems: 'start' }}>
        <section className="hc-panel hc-stagger">
          <div
            className="hc-panel"
            style={{
              marginBottom: '1rem',
              background: 'transparent',
              borderColor: 'var(--hc-border)',
              padding: '1rem',
            }}
          >
            <h2 className="hc-panel-title">Upload Whole Directory (Client Side)</h2>
            <p className="hc-panel-sub" style={{ marginTop: '0.25rem' }}>
              Select a folder from your device. Browser picks files recursively (root to all nested subfolders).
            </p>
            {selectionStats ? (
              <p className="hc-panel-sub" style={{ marginTop: '0.4rem' }}>
                Last selection: picked {selectionStats.picked} file(s), accepted {selectionStats.acceptedSupported} supported file(s),
                skipped {selectionStats.skippedUnsupported} unsupported file(s).
              </p>
            ) : null}

            <div className="hc-inline-actions" style={{ marginTop: '0.75rem' }}>
              <button
                type="button"
                className="hc-btn hc-btn-outline"
                onClick={() => folderRef.current?.click()}
              >
                <Upload size={16} strokeWidth={1.5} />
                Pick Folder (Recursive)
              </button>
            </div>

            <input
              ref={folderRef}
              type="file"
              accept=".pdf,.xlsx,.xls,.csv"
              multiple
              className="hidden"
              onChange={(e) => addFiles(e.target.files)}
              {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
            />
            <p className="hc-panel-sub" style={{ marginTop: '0.5rem' }}>
              Works on Windows/macOS/Linux browsers without entering filesystem paths manually.
            </p>
          </div>

          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => fileRef.current?.click()}
            className="cursor-pointer"
            style={{
              border: '1px dashed var(--hc-border)',
              padding: '2rem 1rem',
              textAlign: 'center',
              transition: 'border-color 150ms var(--hc-ease)',
              background: 'color-mix(in srgb, var(--hc-muted) 25%, transparent)',
            }}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.xlsx,.xls,.csv"
              multiple
              className="hidden"
              onChange={(e) => addFiles(e.target.files)}
            />

            <Upload className="mx-auto" size={40} strokeWidth={1.5} color="var(--hc-muted-fg)" />
            <p style={{ marginTop: '0.6rem', fontWeight: 600 }}>Drop one or more supported files here</p>
            <p className="hc-panel-sub" style={{ marginTop: '0.2rem' }}>
              Supports PDF, XLSX, XLS, and CSV
            </p>
          </div>

          {items.length > 0 ? (
            <div className="space-y-4" style={{ marginTop: '1rem' }}>
              {items.map((item, index) => (
                <article
                  key={item.id}
                  className="hc-panel"
                  style={{ background: 'transparent', padding: '1rem', borderColor: 'var(--hc-border)' }}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <FileText size={20} strokeWidth={1.5} color="var(--hc-accent)" />
                      <div>
                        <p style={{ fontWeight: 600 }}>{item.fileLabel}</p>
                        <p className="hc-panel-sub">
                          File {index + 1} · {(item.file.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="hc-btn hc-btn-ghost"
                      onClick={() => removeItem(item.id)}
                      disabled={uploading}
                    >
                      Remove
                    </button>
                  </div>

                  <div className="hc-grid-2" style={{ marginTop: '1rem' }}>
                    <div>
                      <label htmlFor={`doc-type-${item.id}`} className="hc-label">
                        Document Type
                      </label>
                      <select
                        id={`doc-type-${item.id}`}
                        value={item.documentTypeHint}
                        onChange={(e) =>
                          updateItem(item.id, {
                            documentTypeHint: e.target.value as DocumentTypeHint,
                          })
                        }
                        className="hc-select"
                      >
                        {DOCUMENT_TYPE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label htmlFor={`bank-hint-${item.id}`} className="hc-label">
                        Bank
                      </label>
                      <select
                        id={`bank-hint-${item.id}`}
                        value={item.bankHint}
                        onChange={(e) => updateItem(item.id, { bankHint: e.target.value })}
                        className="hc-select"
                      >
                        {BANK_OPTIONS.map((option) => (
                          <option key={option.value || 'auto'} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div style={{ gridColumn: '1 / -1' }}>
                      <label htmlFor={`pdf-password-${item.id}`} className="hc-label">
                        PDF Password (PDF only)
                      </label>
                      <input
                        id={`pdf-password-${item.id}`}
                        type="password"
                        name={`statement-password-${item.id}`}
                        autoComplete="off"
                        autoCapitalize="off"
                        autoCorrect="off"
                        spellCheck={false}
                        inputMode="text"
                        aria-autocomplete="none"
                        data-lpignore="true"
                        data-1p-ignore="true"
                        data-form-type="other"
                        value={item.password}
                        onChange={(e) => updateItem(item.id, { password: e.target.value })}
                        placeholder="Leave empty if this PDF is not encrypted"
                        className="hc-input"
                      />
                      <p className="hc-panel-sub" style={{ marginTop: '0.35rem' }}>
                        Auto mode lets the local LLM classify bank statements and tax documents.
                      </p>
                    </div>
                  </div>
                </article>
              ))}

              <div className="hc-inline-actions">
                <button type="button" disabled={uploading} className="hc-btn hc-btn-solid" onClick={executeUploadQueue}>
                  {uploading ? (
                    <>
                      <Loader2 size={16} className="hc-animate-spin" strokeWidth={1.5} />
                      Reviewing with local LLM...
                    </>
                  ) : (
                    <>
                      <Upload size={16} strokeWidth={1.5} />
                      Upload Queue
                    </>
                  )}
                </button>

                <button
                  type="button"
                  disabled={uploading}
                  onClick={() => setItems([])}
                  className="hc-btn hc-btn-outline"
                >
                  Clear Queue
                </button>
              </div>
            </div>
          ) : (
            <div className="hc-msg" style={{ marginTop: '1rem' }}>
              <Sparkles size={18} strokeWidth={1.5} />
              <span>No upload queue yet. Add supported files to start local review.</span>
            </div>
          )}
        </section>

        <aside className="hc-panel">
          <div className="hc-panel-head">
            <div>
              <h2 className="hc-panel-title">Review Notifications</h2>
              <p className="hc-panel-sub">
                {queuedCount > 0
                  ? `${queuedCount} document${queuedCount > 1 ? 's are' : ' is'} under local review`
                  : 'Completed and failed uploads appear here.'}
              </p>
            </div>
          </div>

          {notifications.length === 0 ? (
            <div className="hc-msg" style={{ marginTop: '0.9rem' }}>
              <Sparkles size={18} strokeWidth={1.5} />
              <span>
                Document review notifications will appear here while the local LLM checks each upload.
              </span>
            </div>
          ) : (
            <div className="space-y-3" style={{ marginTop: '0.9rem' }}>
              <p className="hc-panel-sub">
                Total {notifications.length} · Reviewing {queuedCount} · Success {successCount} · Error {errorCount}
              </p>
              {notifications.map((item) => (
                <div
                  key={item.id}
                  className={`hc-msg ${
                    item.status === 'success'
                      ? 'hc-msg-ok'
                      : item.status === 'error'
                        ? 'hc-msg-danger'
                        : ''
                  }`}
                  style={{ alignItems: 'flex-start' }}
                >
                  {notificationIcon(item.status)}
                  <div>
                    <p style={{ fontWeight: 600 }}>{item.fileName}</p>
                    <p>{item.message}</p>
                    {(item.bankName || item.accountType) && (
                      <p className="hc-panel-sub" style={{ marginTop: '0.35rem' }}>
                        {(item.bankName || 'Auto-detected')} · {item.accountType || 'type pending'}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function normalizeReviewStatus(status: string): UploadNotification['status'] {
  if (
    status === 'reviewing' ||
    status === 'queued' ||
    status === 'pending' ||
    status === 'parsing' ||
    status === 'uploaded' ||
    status === 'classifying' ||
    status === 'extracting' ||
    status === 'validating'
  ) {
    return 'reviewing';
  }
  if (status === 'success' || status === 'parsed') {
    return 'success';
  }
  return 'error';
}

function isSupportedUploadFile(file: File): boolean {
  const lowerName = file.name.toLowerCase();
  if (SUPPORTED_UPLOAD_EXTS.some((ext) => lowerName.endsWith(ext))) return true;
  const mime = (file.type || '').toLowerCase();
  if (mime === 'application/pdf' || mime === 'text/csv') return true;
  return (
    mime === 'application/vnd.ms-excel' ||
    mime === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  );
}

function toAccountTypeHint(documentTypeHint: DocumentTypeHint): string | undefined {
  if (documentTypeHint === 'credit_card_statement') return 'credit_card';
  if (documentTypeHint === 'bank_statement') return 'bank_account';
  return undefined;
}
