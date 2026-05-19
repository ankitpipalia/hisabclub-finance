import React, { useEffect, useMemo, useState } from 'react';
import { Alert, FlatList, StyleSheet, Text, View } from 'react-native';
import { ActivityIndicator, Button, Card, Chip, TextInput } from 'react-native-paper';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/client';
import type { ConversationMessage, ConversationThread } from '../api/types';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import { useToast } from '../components/ui/Toast';

export default function AssistantScreen() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [newThreadTitle, setNewThreadTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [applyChanges, setApplyChanges] = useState(false);
  const [busy, setBusy] = useState(false);

  const threadsQuery = useQuery({
    queryKey: ['conversations'],
    queryFn: api.getConversations,
  });

  const messagesQuery = useQuery({
    queryKey: ['conversation-messages', selectedThreadId],
    queryFn: () => api.getConversationMessages(selectedThreadId!),
    enabled: !!selectedThreadId,
  });

  useEffect(() => {
    if (!selectedThreadId && threadsQuery.data?.[0]) {
      setSelectedThreadId(threadsQuery.data[0].id);
    }
  }, [selectedThreadId, threadsQuery.data]);

  const createThread = async () => {
    if (!newThreadTitle.trim()) return;
    setBusy(true);
    try {
      const thread = await api.createConversation({ title: newThreadTitle.trim() });
      setNewThreadTitle('');
      setSelectedThreadId(thread.id);
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
    } catch (err: any) {
      toast.error(err?.message || 'Could not create thread');
    } finally {
      setBusy(false);
    }
  };

  const sendReply = async () => {
    if (!selectedThreadId || !prompt.trim()) return;
    setBusy(true);
    try {
      await api.replyConversation(selectedThreadId, {
        message: prompt.trim(),
        apply_changes: applyChanges,
      });
      setPrompt('');
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
      await queryClient.invalidateQueries({ queryKey: ['conversation-messages', selectedThreadId] });
    } catch (err: any) {
      toast.error(err?.message || 'Could not send reply');
    } finally {
      setBusy(false);
    }
  };

  const resolveThread = async () => {
    if (!selectedThreadId) return;
    setBusy(true);
    try {
      await api.resolveConversation(selectedThreadId);
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
      await queryClient.invalidateQueries({ queryKey: ['conversation-messages', selectedThreadId] });
    } catch (err: any) {
      toast.error(err?.message || 'Could not resolve thread');
    } finally {
      setBusy(false);
    }
  };

  if (threadsQuery.isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  const threads = threadsQuery.data ?? [];
  const messages = messagesQuery.data ?? [];

  return (
    <View style={styles.container}>
      <FlatList
        data={messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.content}
        ListHeaderComponent={(
          <View style={styles.header}>
            <Text style={styles.kicker}>Persistent Assistant</Text>
            <Text style={styles.title}>Threads</Text>
            <Text style={styles.subtitle}>Grouped correction and clarification conversations.</Text>
            <Card style={styles.card}>
              <Card.Content>
                <Text style={styles.sectionTitle}>Create Thread</Text>
                <TextInput label="Thread title" mode="outlined" value={newThreadTitle} onChangeText={setNewThreadTitle} style={styles.input} />
                <Button mode="contained" onPress={createThread} loading={busy} disabled={busy || !newThreadTitle.trim()}>
                  Create
                </Button>
              </Card.Content>
            </Card>
            <ScrollThreadList
              threads={threads}
              selectedThreadId={selectedThreadId}
              onSelect={setSelectedThreadId}
              colors={colors}
            />
            {selectedThreadId ? (
              <View style={styles.threadActions}>
                <Button mode="outlined" onPress={resolveThread} disabled={busy}>
                  Resolve
                </Button>
              </View>
            ) : null}
          </View>
        )}
        renderItem={({ item }) => <MessageCard message={item} colors={colors} />}
        ListFooterComponent={selectedThreadId ? (
          <Card style={styles.card}>
            <Card.Content>
              <Text style={styles.sectionTitle}>Reply</Text>
              <TextInput
                label="Message"
                mode="outlined"
                multiline
                value={prompt}
                onChangeText={setPrompt}
                style={styles.input}
              />
              <Chip selected={applyChanges} onPress={() => setApplyChanges((v) => !v)} style={styles.inlineChip}>
                Apply changes immediately
              </Chip>
              <Button mode="contained" onPress={sendReply} loading={busy} disabled={busy || !prompt.trim()}>
                Send
              </Button>
            </Card.Content>
          </Card>
        ) : (
          <Card style={styles.card}>
            <Card.Content>
              <Text style={styles.subtitle}>Create or select a thread to start.</Text>
            </Card.Content>
          </Card>
        )}
      />
    </View>
  );
}

function ScrollThreadList({
  threads,
  selectedThreadId,
  onSelect,
  colors,
}: {
  threads: ConversationThread[];
  selectedThreadId: string | null;
  onSelect: (id: string) => void;
  colors: AppThemeColors;
}) {
  const styles = useMemo(() => createStyles(colors), [colors]);
  return (
    <View style={styles.threadList}>
      {threads.map((thread) => (
        <Chip
          key={thread.id}
          selected={selectedThreadId === thread.id}
          onPress={() => onSelect(thread.id)}
          style={styles.threadChip}
        >
          {thread.title}{thread.pending_question_count ? ` (${thread.pending_question_count})` : ''}
        </Chip>
      ))}
    </View>
  );
}

function MessageCard({ message, colors }: { message: ConversationMessage; colors: AppThemeColors }) {
  const styles = useMemo(() => createStyles(colors), [colors]);
  return (
    <Card style={styles.card}>
      <Card.Content>
        <Text style={styles.messageRole}>{message.role}</Text>
        <Text style={styles.messageText}>{message.content}</Text>
        {message.metadata_json?.actions ? (
          <Text style={styles.messageMeta}>
            Actions: {Array.isArray(message.metadata_json.actions) ? message.metadata_json.actions.length : 0}
          </Text>
        ) : null}
      </Card.Content>
    </Card>
  );
}

const createStyles = (colors: AppThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
    content: { padding: 16, gap: 12 },
    header: { gap: 12, marginBottom: 8 },
    kicker: { color: colors.primary, textTransform: 'uppercase', letterSpacing: 1, fontWeight: '700' },
    title: { fontSize: 28, fontWeight: '800', color: colors.text },
    subtitle: { color: colors.textSecondary },
    card: { backgroundColor: colors.surface, marginBottom: 12 },
    sectionTitle: { fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 10 },
    input: { marginBottom: 12, backgroundColor: colors.surface },
    threadList: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    threadChip: { backgroundColor: colors.surface },
    inlineChip: { alignSelf: 'flex-start', marginBottom: 12 },
    threadActions: { flexDirection: 'row', justifyContent: 'flex-end' },
    messageRole: { color: colors.primary, fontWeight: '700', textTransform: 'capitalize', marginBottom: 6 },
    messageText: { color: colors.text },
    messageMeta: { color: colors.textSecondary, marginTop: 8 },
  });
