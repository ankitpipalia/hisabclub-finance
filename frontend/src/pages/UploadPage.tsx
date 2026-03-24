import { useRef, useState } from 'react';
import { Upload, FileText, CheckCircle2, XCircle, Loader2, ArrowUpRight } from 'lucide-react';
import { api, ApiError } from '../api/client';

const BANKS = ['HDFC', 'AXIS', 'SBI', 'ICICI', 'KOTAK'];

export default function UploadPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState('');
  const [bankHint, setBankHint] = useState('');
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{
    status: string;
    message: string;
    canReprocess?: boolean;
  } | null>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f?.type === 'application/pdf') setFile(f);
  };

  const executeUpload = async (forceReprocess = false) => {
    if (!file) return;
    setUploading(true);
    setResult(null);

    try {
      const res = await api.uploadPdf(file, password || undefined, bankHint || undefined, forceReprocess);
      setResult({ status: res.status, message: res.message });
      if (res.status === 'success') {
        setFile(null);
        setPassword('');
        setBankHint('');
      }
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setResult({
          status: 'error',
          message: 'This statement already exists. Click Reprocess to parse it again.',
          canReprocess: true,
        });
      } else {
        const message = err instanceof Error ? err.message : 'Upload failed.';
        setResult({ status: 'error', message });
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="hc-page" style={{ maxWidth: '980px' }}>
      <div className="hc-page-header">
        <div>
          <p className="hc-kicker">Statement Intake</p>
          <h1 className="hc-page-title">Upload Documents</h1>
          <p className="hc-page-subtitle">
            Parse statement PDFs directly on your local system. Encrypted files are supported.
          </p>
        </div>
      </div>

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
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />

          {file ? (
            <div className="flex items-center justify-center gap-3">
              <FileText size={24} strokeWidth={1.5} color="var(--hc-accent)" />
              <div className="text-left">
                <p style={{ fontWeight: 600 }}>{file.name}</p>
                <p className="hc-panel-sub">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
              </div>
            </div>
          ) : (
            <>
              <Upload className="mx-auto" size={40} strokeWidth={1.5} color="var(--hc-muted-fg)" />
              <p style={{ marginTop: '0.6rem', fontWeight: 600 }}>Drop your PDF statement here</p>
              <p className="hc-panel-sub" style={{ marginTop: '0.2rem' }}>
                or click to browse local files
              </p>
            </>
          )}
        </div>

        {file && (
          <form
            className="hc-grid-2"
            style={{ marginTop: '1rem' }}
            onSubmit={(e) => {
              e.preventDefault();
              executeUpload(false);
            }}
            autoComplete="off"
          >
            <div>
              <label htmlFor="pdf-password" className="hc-label">
                PDF Password (optional)
              </label>
              <input
                id="pdf-password"
                type="password"
                name="statement-password"
                autoComplete="off"
                data-lpignore="true"
                data-1p-ignore="true"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Leave empty if not protected"
                className="hc-input"
              />
            </div>

            <div>
              <label htmlFor="bank-hint" className="hc-label">
                Bank Hint (optional)
              </label>
              <select
                id="bank-hint"
                value={bankHint}
                onChange={(e) => setBankHint(e.target.value)}
                className="hc-select"
              >
                <option value="">Auto-detect</option>
                {BANKS.map((bank) => (
                  <option key={bank} value={bank}>
                    {bank}
                  </option>
                ))}
              </select>
            </div>

            <div className="hc-inline-actions" style={{ gridColumn: '1 / -1' }}>
              <button type="submit" disabled={uploading} className="hc-btn hc-btn-solid">
                {uploading ? (
                  <>
                    <Loader2 size={16} className="hc-animate-spin" strokeWidth={1.5} />
                    Parsing statement...
                  </>
                ) : (
                  <>
                    <Upload size={16} strokeWidth={1.5} />
                    Upload & Parse
                  </>
                )}
              </button>

              <button
                type="button"
                disabled={!file || uploading}
                onClick={() => {
                  setFile(null);
                  setPassword('');
                  setBankHint('');
                  setResult(null);
                }}
                className="hc-btn hc-btn-outline"
              >
                Clear
              </button>
            </div>
          </form>
        )}
      </section>

      {result && (
        <div className={`hc-msg ${result.status === 'success' ? 'hc-msg-ok' : 'hc-msg-danger'}`}>
          {result.status === 'success' ? <CheckCircle2 size={18} strokeWidth={1.5} /> : <XCircle size={18} strokeWidth={1.5} />}
          <span>{result.message}</span>
        </div>
      )}

      {result?.status === 'error' && result.canReprocess && file && (
        <button
          type="button"
          onClick={() => executeUpload(true)}
          disabled={uploading}
          className="hc-btn hc-btn-primary"
        >
          Reprocess Existing PDF
          <ArrowUpRight size={16} strokeWidth={1.5} />
        </button>
      )}
    </div>
  );
}
