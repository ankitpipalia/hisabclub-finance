import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { DocumentArtifact, FolderImportResponse, ParserSupportQueueItem } from '../api/client';

function parsePasswordMap(raw: string): Record<string, string> | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;

  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, string>;
    }
  } catch {
    // Fall through to key=value parsing.
  }

  const out: Record<string, string> = {};
  for (const line of trimmed.split('\n')) {
    const idx = line.indexOf('=');
    if (idx <= 0) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    if (key && value) out[key] = value;
  }
  return Object.keys(out).length ? out : undefined;
}

export default function ImportsPage() {
  const [folderPath, setFolderPath] = useState('/data/imports');
  const [maxFiles, setMaxFiles] = useState<number | ''>('');
  const [parseSupported, setParseSupported] = useState(true);
  const [dryRun, setDryRun] = useState(false);
  const [forceReprocess, setForceReprocess] = useState(false);
  const [passwordMapRaw, setPasswordMapRaw] = useState('');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<FolderImportResponse | null>(null);
  const [artifacts, setArtifacts] = useState<DocumentArtifact[]>([]);
  const [queue, setQueue] = useState<ParserSupportQueueItem[]>([]);
  const [openingArtifactId, setOpeningArtifactId] = useState<string | null>(null);
  const getErrorMessage = (err: unknown, fallback: string) =>
    err instanceof Error ? err.message : fallback;

  const loadArtifacts = async () => {
    try {
      const res = await api.getDocumentArtifacts({ limit: 200 });
      setArtifacts(res.items);
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to load artifacts'));
    }
  };

  const loadQueue = async () => {
    try {
      const res = await api.getParserSupportQueue(300);
      setQueue(res.items);
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to load parser queue'));
    }
  };

  useEffect(() => {
    loadArtifacts();
    loadQueue();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runImport = async () => {
    setError('');
    setRunning(true);
    try {
      const response = await api.importFolder({
        folder_path: folderPath.trim(),
        parse_supported: parseSupported,
        dry_run: dryRun,
        force_reprocess: forceReprocess,
        max_files: maxFiles === '' ? undefined : Number(maxFiles),
        password_map: parsePasswordMap(passwordMapRaw),
      });
      setResult(response);
      await loadArtifacts();
      await loadQueue();
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Import failed'));
    } finally {
      setRunning(false);
    }
  };

  const openArtifactPdf = async (artifact: DocumentArtifact) => {
    try {
      setOpeningArtifactId(artifact.id);
      const blob = await api.getArtifactPdf(artifact.id);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to open artifact PDF'));
    } finally {
      setOpeningArtifactId(null);
    }
  };

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Bulk Intake</p>
          <h1 className="hc-page-title">Local Document Import</h1>
          <p className="hc-page-subtitle">
            Scan a local folder, register every file, and parse supported statements without uploading data externally.
          </p>
        </div>
      </header>

      <section className="hc-panel">
        {error && <div className="hc-msg hc-msg-danger">{error}</div>}

        <div style={{ marginTop: error ? '0.8rem' : 0 }}>
          <label className="hc-label">Folder Path</label>
          <input
            type="text"
            value={folderPath}
            onChange={(e) => setFolderPath(e.target.value)}
            className="hc-input"
            placeholder="/data/imports"
          />
        </div>

        <div className="hc-grid-2" style={{ marginTop: '0.8rem' }}>
          <div>
            <label className="hc-label">Max Files (optional)</label>
            <input
              type="number"
              value={maxFiles}
              onChange={(e) => setMaxFiles(e.target.value ? Number(e.target.value) : '')}
              className="hc-input"
              placeholder="e.g. 50"
            />
          </div>
          <div>
            <label className="hc-label">Password Map (optional)</label>
            <textarea
              value={passwordMapRaw}
              onChange={(e) => setPasswordMapRaw(e.target.value)}
              className="hc-textarea"
              placeholder='JSON {"hdfc":"ANKI1076"} or lines: hdfc=ANKI1076'
            />
          </div>
        </div>

        <div className="hc-inline-actions" style={{ marginTop: '0.8rem' }}>
          <label className="hc-badge">
            <input type="checkbox" checked={parseSupported} onChange={(e) => setParseSupported(e.target.checked)} />
            Parse supported statements
          </label>
          <label className="hc-badge">
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
            Dry run
          </label>
          <label className="hc-badge">
            <input type="checkbox" checked={forceReprocess} onChange={(e) => setForceReprocess(e.target.checked)} />
            Force reprocess duplicates
          </label>
        </div>

        <div className="hc-inline-actions" style={{ marginTop: '0.8rem' }}>
          <button onClick={runImport} disabled={running || !folderPath.trim()} className="hc-btn hc-btn-solid">
            {running ? 'Running...' : 'Run Intake'}
          </button>
          <button
            onClick={() => {
              loadArtifacts();
              loadQueue();
            }}
            className="hc-btn hc-btn-outline"
          >
            Refresh
          </button>
        </div>
      </section>

      {result && (
        <section className="hc-panel">
          <h2 className="hc-panel-title">Last Run Summary</h2>
          <div className="hc-grid-4" style={{ marginTop: '0.8rem' }}>
            <div className="hc-badge">Discovered: {result.discovered}</div>
            <div className="hc-badge">Ingested: {result.ingested}</div>
            <div className="hc-badge">Parsed: {result.parsed}</div>
            <div className="hc-badge">Skipped: {result.skipped}</div>
          </div>
          <div className="hc-badge" style={{ marginTop: '0.6rem' }}>Failed: {result.failed}</div>

          <pre
            style={{
              marginTop: '0.8rem',
              overflowX: 'auto',
              background: 'var(--hc-muted)',
              border: '1px solid var(--hc-border)',
              padding: '0.7rem',
              fontSize: '0.75rem',
            }}
          >
            {JSON.stringify(result.by_doc_type, null, 2)}
          </pre>

          {result.messages.length > 0 && (
            <div className="hc-msg hc-msg-danger" style={{ marginTop: '0.8rem' }}>
              <div>
                {result.messages.slice(0, 20).map((m) => (
                  <div key={m}>{m}</div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      <section className="hc-panel">
        <div className="hc-panel-head">
          <div>
            <h2 className="hc-panel-title">Parser Support Queue</h2>
            <p className="hc-panel-sub">Unsupported or unknown statement formats grouped for parser backlog.</p>
          </div>
        </div>

        <div className="hc-table-wrap">
          <table className="hc-table" style={{ minWidth: 850 }}>
            <thead>
              <tr>
                <th>Bank</th>
                <th>Doc Type</th>
                <th>Reason</th>
                <th>Count</th>
                <th>Sample Files</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((q) => (
                <tr key={`${q.bank_hint || 'unknown'}-${q.doc_type}-${q.reason}`}>
                  <td>{q.bank_hint || 'UNKNOWN'}</td>
                  <td>{q.doc_type}</td>
                  <td>{q.reason}</td>
                  <td style={{ fontWeight: 600 }}>{q.count}</td>
                  <td style={{ fontSize: '0.75rem' }}>{q.sample_files.join(', ') || '-'}</td>
                </tr>
              ))}
              {queue.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center' }}>No parser backlog items.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="hc-panel">
        <div className="hc-panel-head">
          <h2 className="hc-panel-title">Document Registry</h2>
        </div>

        <div className="hc-table-wrap">
          <table className="hc-table" style={{ minWidth: 950 }}>
            <thead>
              <tr>
                <th>File</th>
                <th>Type</th>
                <th>Bank</th>
                <th>Status</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map((a) => (
                <tr key={a.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{a.file_name}</div>
                    <div className="hc-panel-sub" style={{ maxWidth: 420, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {a.file_path}
                    </div>
                    {a.file_ext.toLowerCase() === 'pdf' && (
                      <div style={{ marginTop: '0.4rem' }}>
                        <button
                          className="hc-btn hc-btn-outline"
                          onClick={() => openArtifactPdf(a)}
                          disabled={openingArtifactId === a.id}
                        >
                          {openingArtifactId === a.id ? 'Opening...' : 'View PDF'}
                        </button>
                      </div>
                    )}
                  </td>
                  <td>{a.doc_subtype ? `${a.doc_type}/${a.doc_subtype}` : a.doc_type}</td>
                  <td>{a.bank_hint || '-'}</td>
                  <td><span className="hc-badge">{a.status}</span></td>
                  <td style={{ fontSize: '0.75rem' }}>{a.parse_message || '-'}</td>
                </tr>
              ))}
              {artifacts.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center' }}>No documents registered yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
