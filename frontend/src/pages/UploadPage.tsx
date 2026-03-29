import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2,
  FileText,
  Loader2,
  Sparkles,
  Upload,
  XCircle,
} from 'lucide-react';
import { api, ApiError } from '../api/client';

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
  { value: 'auto', label: 'Auto via local LLM' },
  { value: 'bank_account', label: 'Bank account statement' },
  { value: 'credit_card', label: 'Credit card statement' },
] as const;

type DocumentTypeHint = (typeof DOCUMENT_TYPE_OPTIONS)[number]['value'];

type UploadItem = {
  id: string;
  file: File;
  password: string;
  bankHint: string;
  accountTypeHint: DocumentTypeHint;
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

export default function UploadPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [notifications, setNotifications] = useState<UploadNotification[]>([]);

  const queuedCount = useMemo(
    () => notifications.filter((item) => item.status === 'reviewing' || item.status === 'queued').length,
    [notifications],
  );

  useEffect(() => {
    let cancelled = false;
    const loadRecentUploads = async () => {
      try {
        const recent = await api.getRecentUploads(12);
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
    const nextItems = Array.from(fileList)
      .filter((file) => file.type === 'application/pdf')
      .map((file) => ({
        id: `${file.name}-${file.lastModified}-${file.size}-${crypto.randomUUID()}`,
        file,
        password: '',
        bankHint: '',
        accountTypeHint: 'auto' as DocumentTypeHint,
      }));
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
        fileName: item.file.name,
        status: 'reviewing',
        message: 'Document is under review by the local LLM. Please wait. We will notify you once it completes.',
      },
      ...current.filter((entry) => entry.id !== item.id),
    ]);
  };

  const runUpload = async (item: UploadItem) => {
    startNotification(item);
    try {
      const res = await api.uploadPdf(
        item.file,
        item.password || undefined,
        item.bankHint || undefined,
        item.accountTypeHint,
        item.forceReprocess ?? false,
      );
      const serverId = res.document_id || res.pdf_id || item.id;
      remapNotificationId(item.id, serverId, item.file.name);
      if (res.status === 'duplicate') {
        updateNotification(serverId, {
          status: 'error',
          message: res.message || 'This statement already exists. Choose Reprocess to parse it again.',
          canReprocess: true,
        });
        updateItem(item.id, { forceReprocess: true });
        return;
      }
      if (isReviewingStatus(res.status)) {
        updateNotification(serverId, {
          status: 'reviewing',
          message:
            res.message ||
            'Document is under review by the local LLM. Please wait. We will notify you once it completes.',
          bankName: res.bank_name,
          accountType: res.account_type,
        });
        removeItem(item.id);
        return;
      }
      if (res.status !== 'success' && res.status !== 'parsed') {
        updateNotification(serverId, {
          status: 'error',
          message: res.message || 'Upload review failed.',
          bankName: res.bank_name,
          accountType: res.account_type,
        });
        return;
      }
      updateNotification(serverId, {
        status: 'success',
        message: res.message,
        bankName: res.bank_name,
        accountType: res.account_type,
        canReprocess: false,
      });
      removeItem(item.id);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        updateNotification(item.id, {
          status: 'error',
          message: 'This statement already exists. Choose Reprocess to parse it again.',
          canReprocess: true,
        });
        updateItem(item.id, { forceReprocess: true });
        return;
      }
      const message = err instanceof Error ? err.message : 'Upload failed.';
      updateNotification(item.id, { status: 'error', message });
    }
  };

  const executeUploadQueue = async () => {
    if (items.length === 0 || uploading) return;
    setUploading(true);
    try {
      for (const item of items) {
        // eslint-disable-next-line no-await-in-loop
        await runUpload(item);
      }
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
            Queue one or more PDFs, choose the statement type per document, and let the local LLM
            resolve the rest.
          </p>
        </div>
      </div>

      <div className="hc-grid-2" style={{ alignItems: 'start' }}>
        <section className="hc-panel hc-stagger">
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
              accept=".pdf"
              multiple
              className="hidden"
              onChange={(e) => addFiles(e.target.files)}
            />

            <Upload className="mx-auto" size={40} strokeWidth={1.5} color="var(--hc-muted-fg)" />
            <p style={{ marginTop: '0.6rem', fontWeight: 600 }}>Drop one or more PDF statements here</p>
            <p className="hc-panel-sub" style={{ marginTop: '0.2rem' }}>
              or click to browse local files
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
                        <p style={{ fontWeight: 600 }}>{item.file.name}</p>
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
                        Statement Type
                      </label>
                      <select
                        id={`doc-type-${item.id}`}
                        value={item.accountTypeHint}
                        onChange={(e) =>
                          updateItem(item.id, {
                            accountTypeHint: e.target.value as DocumentTypeHint,
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
                        PDF Password
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
                        Auto mode lets the local LLM decide whether this is a bank account or
                        credit card statement.
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
              <span>No upload queue yet. Add one or more PDFs to start local review.</span>
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
