import { useMemo, useState } from 'react';
import { Bot, SendHorizontal, Sparkles } from 'lucide-react';
import { api } from '../api/client';
import type { AssistantActionResult } from '../api/client';
import type { FormEvent } from 'react';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  warnings?: string[];
  actions?: AssistantActionResult[];
};

function formatAction(action: AssistantActionResult) {
  const before = action.before ? ` [${action.before}]` : '';
  const after = action.after ? ` -> [${action.after}]` : '';
  return `${action.action}: ${action.detail}${before}${after}`;
}

export default function AssistantPage() {
  const [prompt, setPrompt] = useState('');
  const [applyChanges, setApplyChanges] = useState(true);
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  const stats = useMemo(() => {
    let proposed = 0;
    let applied = 0;
    let skipped = 0;
    for (const message of messages) {
      if (message.role !== 'assistant' || !message.actions) continue;
      for (const action of message.actions) {
        if (action.status === 'proposed') proposed += 1;
        if (action.status === 'applied') applied += 1;
        if (action.status === 'skipped') skipped += 1;
      }
    }
    return { proposed, applied, skipped };
  }, [messages]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setMessages((prev) => [
      ...prev,
      {
        id: `u-${Date.now()}`,
        role: 'user',
        text,
      },
    ]);
    setPrompt('');
    try {
      const result = await api.assistantChat({
        message: text,
        apply_changes: applyChanges,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          text: result.reply,
          warnings: result.warnings,
          actions: result.actions,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Assistant request failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="hc-page-header">
        <div>
          <p className="hc-kicker">Local LLM</p>
          <h1 className="hc-page-title">AI Correction Chat</h1>
          <p className="hc-page-subtitle">
            Ask the assistant to fix categorization, transaction nature, notes, or include/exclude
            decisions from your ledger.
          </p>
        </div>
      </div>

      <section className="hc-grid-3">
        <div className="hc-panel">
          <p className="hc-stat-label">Proposed</p>
          <p className="hc-stat-value">{stats.proposed}</p>
        </div>
        <div className="hc-panel">
          <p className="hc-stat-label">Applied</p>
          <p className="hc-stat-value">{stats.applied}</p>
        </div>
        <div className="hc-panel">
          <p className="hc-stat-label">Skipped</p>
          <p className="hc-stat-value">{stats.skipped}</p>
        </div>
      </section>

      <section className="hc-panel">
        <form onSubmit={onSubmit} className="space-y-3">
          <label htmlFor="assistant-prompt" className="hc-label">
            Prompt
          </label>
          <textarea
            id="assistant-prompt"
            className="hc-textarea"
            style={{ minHeight: '120px' }}
            placeholder="Example: mark all TELE TRANSFER CREDIT entries from Kotak Savings as credit card payments and set nature to transfer_internal."
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            disabled={busy}
          />
          <div className="flex flex-wrap items-center gap-3">
            <label
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.55rem',
                fontSize: '0.82rem',
                color: 'var(--hc-muted-fg)',
              }}
            >
              <input
                type="checkbox"
                checked={applyChanges}
                onChange={(event) => setApplyChanges(event.target.checked)}
                disabled={busy}
              />
              Apply changes immediately
            </label>
            <button type="submit" className="hc-btn hc-btn-primary" disabled={busy || !prompt.trim()}>
              <SendHorizontal size={16} />
              {busy ? 'Running...' : 'Run Assistant'}
            </button>
          </div>
          {error && (
            <p className="hc-msg hc-msg-danger" style={{ marginTop: '0.5rem' }}>
              {error}
            </p>
          )}
        </form>
      </section>

      <section className="space-y-3">
        {messages.length === 0 ? (
          <div className="hc-panel">
            <p className="hc-panel-sub">
              No chat activity yet. Start with a correction prompt and the local LLM will return a
              safe action plan.
            </p>
          </div>
        ) : (
          messages.map((message) => (
            <article key={message.id} className="hc-panel">
              <div className="flex items-center gap-2">
                {message.role === 'assistant' ? <Bot size={16} /> : <Sparkles size={16} />}
                <p className="hc-panel-title">
                  {message.role === 'assistant' ? 'Assistant' : 'You'}
                </p>
              </div>
              <p className="hc-panel-sub" style={{ marginTop: '0.5rem', whiteSpace: 'pre-wrap' }}>
                {message.text}
              </p>
              {message.warnings && message.warnings.length > 0 && (
                <div style={{ marginTop: '0.65rem' }}>
                  {message.warnings.map((warning, idx) => (
                    <p key={`${message.id}-warn-${idx}`} className="hc-msg hc-msg-warn">
                      {warning}
                    </p>
                  ))}
                </div>
              )}
              {message.actions && message.actions.length > 0 && (
                <div className="space-y-2" style={{ marginTop: '0.7rem' }}>
                  {message.actions.map((action, idx) => (
                    <div key={`${message.id}-action-${idx}`} className="hc-badge">
                      {formatAction(action)}
                    </div>
                  ))}
                </div>
              )}
            </article>
          ))
        )}
      </section>
    </div>
  );
}
