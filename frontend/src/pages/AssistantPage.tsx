import { useEffect, useMemo, useState } from 'react';
import { Bot, MessageSquareText, Plus, SendHorizontal } from 'lucide-react';
import { api } from '../api/client';
import type { ConversationMessage, ConversationThread } from '../api/client';

export default function AssistantPage() {
  const [threads, setThreads] = useState<ConversationThread[]>([]);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState('');
  const [newThreadTitle, setNewThreadTitle] = useState('');
  const [applyChanges, setApplyChanges] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const selectedThread = useMemo(
    () => threads.find((thread) => thread.id === selectedThreadId) ?? null,
    [threads, selectedThreadId],
  );

  const loadThreads = async () => {
    const items = await api.getConversations();
    setThreads(items);
    if (!selectedThreadId && items[0]) {
      setSelectedThreadId(items[0].id);
    }
    return items;
  };

  const loadMessages = async (threadId: string) => {
    const items = await api.getConversationMessages(threadId);
    setMessages(items);
  };

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const items = await api.getConversations();
        if (!active) return;
        setThreads(items);
        if (items[0]) {
          setSelectedThreadId(items[0].id);
          const threadMessages = await api.getConversationMessages(items[0].id);
          if (active) setMessages(threadMessages);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Could not load assistant threads.');
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedThreadId) return;
    void loadMessages(selectedThreadId);
  }, [selectedThreadId]);

  const createThread = async () => {
    if (!newThreadTitle.trim()) return;
    setBusy(true);
    setError('');
    try {
      const thread = await api.createConversation({ title: newThreadTitle.trim() });
      setNewThreadTitle('');
      await loadThreads();
      setSelectedThreadId(thread.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create thread.');
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    if (!selectedThreadId || !prompt.trim()) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.replyConversation(selectedThreadId, {
        message: prompt.trim(),
        apply_changes: applyChanges,
      });
      setPrompt('');
      setThreads((current) =>
        current.map((thread) => (thread.id === result.thread.id ? result.thread : thread)),
      );
      await loadMessages(selectedThreadId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send message.');
    } finally {
      setBusy(false);
    }
  };

  const resolveThread = async () => {
    if (!selectedThreadId) return;
    setBusy(true);
    try {
      await api.resolveConversation(selectedThreadId);
      await loadThreads();
      if (selectedThreadId) {
        await loadMessages(selectedThreadId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not resolve thread.');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="hc-panel">Loading assistant...</div>;
  }

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Persistent Assistant</p>
          <h1 className="hc-page-title">Conversation Threads</h1>
          <p className="hc-page-subtitle">
            Track correction dialogs over time and keep ambiguous statement questions grouped instead of single-shot.
          </p>
        </div>
      </header>

      {error && <div className="hc-msg hc-msg-danger">{error}</div>}

      <section className="hc-grid-2" style={{ alignItems: 'start' }}>
        <aside className="hc-panel space-y-3">
          <div className="hc-panel-head">
            <div>
              <h2 className="hc-panel-title">Threads</h2>
              <p className="hc-panel-sub">{threads.length} total</p>
            </div>
          </div>
          <div className="hc-grid-2">
            <input
              className="hc-input"
              placeholder="New thread title"
              value={newThreadTitle}
              onChange={(e) => setNewThreadTitle(e.target.value)}
            />
            <button className="hc-btn hc-btn-solid" onClick={() => void createThread()} disabled={busy}>
              <Plus size={16} />
              Create
            </button>
          </div>
          <div className="space-y-2">
            {threads.map((thread) => (
              <button
                key={thread.id}
                type="button"
                className="hc-panel"
                style={{
                  width: '100%',
                  textAlign: 'left',
                  background: selectedThreadId === thread.id ? 'var(--hc-muted)' : 'transparent',
                }}
                onClick={() => setSelectedThreadId(thread.id)}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p style={{ fontWeight: 600 }}>{thread.title}</p>
                    <p className="hc-panel-sub">{thread.summary ?? thread.status}</p>
                  </div>
                  {!!thread.pending_question_count && (
                    <span className="hc-badge hc-badge-warn">{thread.pending_question_count}</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="hc-panel">
          {selectedThread ? (
            <>
              <div className="hc-panel-head">
                <div>
                  <h2 className="hc-panel-title">{selectedThread.title}</h2>
                  <p className="hc-panel-sub">Status: {selectedThread.status}</p>
                </div>
                <button className="hc-btn hc-btn-outline" onClick={() => void resolveThread()} disabled={busy}>
                  Resolve
                </button>
              </div>

              <div className="space-y-3" style={{ minHeight: '40vh', marginTop: '1rem' }}>
                {messages.map((message) => (
                  <article key={message.id} className="hc-panel" style={{ background: 'transparent' }}>
                    <div className="flex items-center gap-2">
                      {message.role === 'assistant' ? <Bot size={16} /> : <MessageSquareText size={16} />}
                      <p className="hc-panel-title" style={{ textTransform: 'capitalize' }}>{message.role}</p>
                    </div>
                    <p className="hc-panel-sub" style={{ marginTop: '0.5rem', whiteSpace: 'pre-wrap' }}>
                      {message.content}
                    </p>
                    {message.metadata_json && 'actions' in message.metadata_json && (
                      <pre className="hc-panel-sub" style={{ marginTop: '0.5rem', whiteSpace: 'pre-wrap' }}>
                        {JSON.stringify((message.metadata_json as Record<string, unknown>).actions ?? null, null, 2)}
                      </pre>
                    )}
                  </article>
                ))}
              </div>

              <div className="space-y-3" style={{ marginTop: '1rem' }}>
                <textarea
                  className="hc-textarea"
                  style={{ minHeight: '120px' }}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Reply to this thread or ask for a correction."
                />
                <label className="hc-panel-sub" style={{ display: 'inline-flex', gap: '0.5rem', alignItems: 'center' }}>
                  <input type="checkbox" checked={applyChanges} onChange={(e) => setApplyChanges(e.target.checked)} />
                  Apply changes immediately
                </label>
                <button className="hc-btn hc-btn-solid" onClick={() => void send()} disabled={busy || !prompt.trim()}>
                  <SendHorizontal size={16} />
                  {busy ? 'Sending...' : 'Send'}
                </button>
              </div>
            </>
          ) : (
            <p className="hc-panel-sub">Create a thread to start a persistent assistant conversation.</p>
          )}
        </section>
      </section>
    </div>
  );
}
