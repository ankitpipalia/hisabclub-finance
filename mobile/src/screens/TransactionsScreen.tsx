import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
  View,
  FlatList,
  Text,
  StyleSheet,
  RefreshControl,
  ScrollView,
  Alert,
} from 'react-native';
import { Searchbar, Chip, ActivityIndicator, Button, TextInput } from 'react-native-paper';
import { useQuery } from '@tanstack/react-query';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import * as api from '../api/client';
import type { Category, Transaction } from '../api/types';
import type { RootStackParamList } from '../navigation/types';
import TransactionRow from '../components/TransactionRow';
import EmptyState from '../components/EmptyState';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import FadeInView from '../components/FadeInView';
import AnimatedOrbs from '../components/AnimatedOrbs';

type NavProp = NativeStackNavigationProp<RootStackParamList>;

type FilterType = 'all' | 'debit' | 'credit';
type TimelinePreset = 'all' | '30d' | '90d' | 'fy';

const PER_PAGE = 20;

type BulkEditorState = {
  category_id: string;
  transaction_nature: string;
  notes: string;
  tagsText: string;
  is_excluded: boolean;
};

const emptyBulkEditor = (): BulkEditorState => ({
  category_id: '',
  transaction_nature: '',
  notes: '',
  tagsText: '',
  is_excluded: false,
});

function toDateInput(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function getTimelineRange(timeline: TimelinePreset): { from?: string; to?: string } {
  if (timeline === 'all') return {};
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const to = toDateInput(today);

  if (timeline === '30d') {
    const from = new Date(today);
    from.setDate(from.getDate() - 29);
    return { from: toDateInput(from), to };
  }
  if (timeline === '90d') {
    const from = new Date(today);
    from.setDate(from.getDate() - 89);
    return { from: toDateInput(from), to };
  }

  const fyStartYear = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
  return { from: `${fyStartYear}-04-01`, to };
}

export default function TransactionsScreen() {
  const navigation = useNavigation<NavProp>();
  const { colors } = useAppTheme();
  const COLORS = colors;
  const styles = useMemo(() => createStyles(COLORS), [COLORS]);

  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<FilterType>('all');
  const [timeline, setTimeline] = useState<TimelinePreset>('90d');
  const [page, setPage] = useState(1);
  const [allItems, setAllItems] = useState<Transaction[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [autoCategorizeChecked, setAutoCategorizeChecked] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkEditor, setBulkEditor] = useState<BulkEditorState>(emptyBulkEditor());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkInfo, setBulkInfo] = useState('');
  const [categories, setCategories] = useState<Category[]>([]);

  const direction = filter === 'all' ? undefined : filter;
  const timelineRange = useMemo(() => getTimelineRange(timeline), [timeline]);

  const { isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['transactions', search, direction, timelineRange.from, timelineRange.to, page],
    queryFn: async () => {
      const result = await api.getTransactions({
        search: search || undefined,
        direction,
        from: timelineRange.from,
        to: timelineRange.to,
        page,
        per_page: PER_PAGE,
      });
      if (page === 1) {
        setAllItems(result.items);
      } else {
        setAllItems((prev) => [...prev, ...result.items]);
      }
      setHasMore(result.items.length === PER_PAGE);
      return result;
    },
  });

  useEffect(() => {
    if (autoCategorizeChecked) return;
    if (!allItems.some((item) => !item.category_name)) return;
    setAutoCategorizeChecked(true);
    (async () => {
      try {
        const result = await api.autoCategorizeUncategorized(500);
        if (result.updated > 0) {
          refetch();
        }
      } catch {
        // non-blocking best-effort
      }
    })();
  }, [allItems, autoCategorizeChecked, refetch]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const result = await api.getCategories();
        if (active) setCategories(result);
      } catch {
        // best effort
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const handleSearch = useCallback((query: string) => {
    setSearch(query);
    setPage(1);
    setAllItems([]);
    setHasMore(true);
  }, []);

  const handleFilterChange = useCallback((newFilter: FilterType) => {
    setFilter(newFilter);
    setPage(1);
    setAllItems([]);
    setHasMore(true);
  }, []);

  const handleTimelineChange = useCallback((nextTimeline: TimelinePreset) => {
    setTimeline(nextTimeline);
    setPage(1);
    setAllItems([]);
    setHasMore(true);
  }, []);

  const handleLoadMore = useCallback(() => {
    if (!isLoading && hasMore) {
      setPage((p) => p + 1);
    }
  }, [isLoading, hasMore]);

  const handleRefresh = useCallback(() => {
    setPage(1);
    setAllItems([]);
    setHasMore(true);
    refetch();
  }, [refetch]);

  const clearSelection = useCallback(() => {
    setSelectionMode(false);
    setSelectedIds([]);
    setBulkEditor(emptyBulkEditor());
    setBulkInfo('');
  }, []);

  const handleTransactionPress = useCallback(
    (transaction: Transaction) => {
      if (selectionMode) {
        setSelectedIds((current) =>
          current.includes(transaction.id)
            ? current.filter((id) => id !== transaction.id)
            : [...current, transaction.id],
        );
        return;
      }
      navigation.navigate('TransactionDetail', { id: transaction.id });
    },
    [navigation, selectionMode],
  );

  const handleTransactionLongPress = useCallback((transaction: Transaction) => {
    setSelectionMode(true);
    setSelectedIds((current) => (current.includes(transaction.id) ? current : [...current, transaction.id]));
  }, []);

  const handleBulkApply = useCallback(async () => {
    if (!selectedIds.length) return;
    const payload: {
      transaction_ids: string[];
      category_id?: string | null;
      transaction_nature?: string | null;
      notes?: string | null;
      tags?: string[] | null;
      is_excluded?: boolean;
    } = { transaction_ids: selectedIds };
    if (bulkEditor.category_id) payload.category_id = bulkEditor.category_id;
    if (bulkEditor.transaction_nature) payload.transaction_nature = bulkEditor.transaction_nature;
    if (bulkEditor.notes.trim()) payload.notes = bulkEditor.notes.trim();
    if (bulkEditor.tagsText.trim()) {
      payload.tags = bulkEditor.tagsText
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
    }
    payload.is_excluded = bulkEditor.is_excluded;

    setBulkBusy(true);
    try {
      const result = await api.bulkUpdateTransactions(payload);
      Alert.alert('Bulk update complete', `Updated ${result.updated_count} transaction(s).`);
      clearSelection();
      handleRefresh();
    } catch (err: any) {
      setBulkInfo(err.message || 'Bulk update failed.');
    } finally {
      setBulkBusy(false);
    }
  }, [bulkEditor, clearSelection, handleRefresh, selectedIds]);

  const renderFooter = () => {
    if (!isLoading || page === 1) return null;
    return (
      <View style={styles.footer}>
        <ActivityIndicator size="small" color={COLORS.primary} />
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <FadeInView>
        <View style={styles.hero}>
          <AnimatedOrbs compact />
          <Text style={styles.kicker}>Ledger</Text>
          <Text style={styles.title}>Transactions</Text>
          <Text style={styles.subtitle}>Search and filter by direction and timeline across all accounts.</Text>
        </View>
      </FadeInView>

      <FadeInView delay={80}>
        <View style={styles.searchSection}>
          <View style={styles.selectionHeader}>
            <Text style={styles.selectionTitle}>
              {selectionMode ? `${selectedIds.length} selected` : 'Tap to open. Long-press to select.'}
            </Text>
            <View style={styles.selectionActions}>
              {!selectionMode ? (
                <Button mode="outlined" compact onPress={() => setSelectionMode(true)}>
                  Select
                </Button>
              ) : (
                <>
                  <Button mode="outlined" compact onPress={() => setSelectedIds(allItems.map((item) => item.id))}>
                    Select page
                  </Button>
                  <Button mode="text" compact onPress={clearSelection}>
                    Cancel
                  </Button>
                </>
              )}
            </View>
          </View>
          <Searchbar
            placeholder="Search transactions..."
            value={search}
            onChangeText={handleSearch}
            style={styles.searchbar}
            inputStyle={styles.searchInput}
          />
          <View style={styles.chipRow}>
            <Chip
              selected={filter === 'all'}
              onPress={() => handleFilterChange('all')}
              style={styles.chip}
              selectedColor={COLORS.primary}
            >
              All
            </Chip>
            <Chip
              selected={filter === 'debit'}
              onPress={() => handleFilterChange('debit')}
              style={styles.chip}
              selectedColor={COLORS.primary}
            >
              Debits
            </Chip>
            <Chip
              selected={filter === 'credit'}
              onPress={() => handleFilterChange('credit')}
              style={styles.chip}
              selectedColor={COLORS.primary}
            >
              Credits
            </Chip>
          </View>
          <View style={styles.chipRow}>
            <Chip
              selected={timeline === '30d'}
              onPress={() => handleTimelineChange('30d')}
              style={styles.chip}
              selectedColor={COLORS.primary}
            >
              Last 30D
            </Chip>
            <Chip
              selected={timeline === '90d'}
              onPress={() => handleTimelineChange('90d')}
              style={styles.chip}
              selectedColor={COLORS.primary}
            >
              Last 90D
            </Chip>
            <Chip
              selected={timeline === 'fy'}
              onPress={() => handleTimelineChange('fy')}
              style={styles.chip}
              selectedColor={COLORS.primary}
            >
              Current FY
            </Chip>
            <Chip
              selected={timeline === 'all'}
              onPress={() => handleTimelineChange('all')}
              style={styles.chip}
              selectedColor={COLORS.primary}
            >
              All
            </Chip>
          </View>

          {selectionMode && selectedIds.length > 0 ? (
            <View style={styles.bulkPanel}>
              <Text style={styles.bulkTitle}>Bulk Update</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.categoryScroll}>
                <View style={styles.categoryChipRow}>
                  <Chip
                    selected={bulkEditor.category_id === ''}
                    onPress={() => setBulkEditor((current) => ({ ...current, category_id: '' }))}
                    style={styles.chip}
                  >
                    Keep category
                  </Chip>
                  {categories.slice(0, 24).map((category) => (
                    <Chip
                      key={category.id}
                      selected={bulkEditor.category_id === category.id}
                      onPress={() => setBulkEditor((current) => ({ ...current, category_id: category.id }))}
                      style={styles.chip}
                    >
                      {category.name}
                    </Chip>
                  ))}
                </View>
              </ScrollView>

              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.categoryScroll}>
                <View style={styles.categoryChipRow}>
                  <Chip
                    selected={bulkEditor.transaction_nature === ''}
                    onPress={() => setBulkEditor((current) => ({ ...current, transaction_nature: '' }))}
                    style={styles.chip}
                  >
                    Keep nature
                  </Chip>
                  {['expense', 'income', 'transfer_internal', 'refund', 'investment', 'tax'].map((nature) => (
                    <Chip
                      key={nature}
                      selected={bulkEditor.transaction_nature === nature}
                      onPress={() => setBulkEditor((current) => ({ ...current, transaction_nature: nature }))}
                      style={styles.chip}
                    >
                      {nature}
                    </Chip>
                  ))}
                </View>
              </ScrollView>

              <TextInput
                label="Notes"
                value={bulkEditor.notes}
                onChangeText={(notes) => setBulkEditor((current) => ({ ...current, notes }))}
                mode="outlined"
                style={styles.bulkInput}
              />
              <TextInput
                label="Tags"
                value={bulkEditor.tagsText}
                onChangeText={(tagsText) => setBulkEditor((current) => ({ ...current, tagsText }))}
                mode="outlined"
                style={styles.bulkInput}
                placeholder="comma,separated,tags"
              />
              <View style={styles.selectionActions}>
                <Chip
                  selected={!bulkEditor.is_excluded}
                  onPress={() => setBulkEditor((current) => ({ ...current, is_excluded: false }))}
                  style={styles.chip}
                >
                  Keep included
                </Chip>
                <Chip
                  selected={bulkEditor.is_excluded}
                  onPress={() => setBulkEditor((current) => ({ ...current, is_excluded: true }))}
                  style={styles.chip}
                >
                  Exclude selected
                </Chip>
              </View>
              {bulkInfo ? <Text style={styles.bulkInfo}>{bulkInfo}</Text> : null}
              <View style={styles.selectionActions}>
                <Button
                  mode="contained"
                  onPress={handleBulkApply}
                  loading={bulkBusy}
                  disabled={bulkBusy || !selectedIds.length}
                >
                  Apply to {selectedIds.length}
                </Button>
                {selectedIds.length === 1 ? (
                  <Button
                    mode="outlined"
                    onPress={() => navigation.navigate('TransactionDetail', { id: selectedIds[0] })}
                  >
                    Split / Detail
                  </Button>
                ) : null}
              </View>
            </View>
          ) : null}
        </View>
      </FadeInView>

      {isLoading && page === 1 ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={COLORS.primary} />
        </View>
      ) : allItems.length === 0 ? (
        <EmptyState
          title="No transactions found"
          subtitle={search ? 'Try a different search term' : 'Upload a statement to see transactions'}
        />
      ) : (
        <FlatList
          data={allItems}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <TransactionRow
              transaction={item}
              onPress={() => handleTransactionPress(item)}
              onLongPress={() => handleTransactionLongPress(item)}
              selectionMode={selectionMode}
              selected={selectedIds.includes(item.id)}
            />
          )}
          onEndReached={handleLoadMore}
          onEndReachedThreshold={0.3}
          ListFooterComponent={renderFooter}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={handleRefresh} />
          }
        />
      )}
    </View>
  );
}

const createStyles = (COLORS: AppThemeColors) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  searchSection: {
    marginTop: 12,
    backgroundColor: COLORS.surface,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
  },
  selectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  selectionTitle: {
    color: COLORS.textSecondary,
    fontSize: 12,
    flex: 1,
    marginRight: 12,
  },
  selectionActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
  bulkPanel: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    gap: 10,
  },
  bulkTitle: {
    color: COLORS.text,
    fontWeight: '700',
    fontSize: 14,
  },
  categoryScroll: {
    marginTop: 2,
  },
  categoryChipRow: {
    flexDirection: 'row',
    gap: 8,
    paddingRight: 16,
  },
  bulkInput: {
    backgroundColor: COLORS.surface,
  },
  bulkInfo: {
    color: COLORS.textSecondary,
    fontSize: 12,
  },
  hero: {
    margin: 16,
    marginBottom: 0,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    paddingHorizontal: 16,
    paddingVertical: 14,
    overflow: 'hidden',
  },
  kicker: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 1.2,
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    color: COLORS.text,
    letterSpacing: -1.1,
  },
  subtitle: {
    fontSize: 12,
    color: COLORS.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  searchbar: {
    backgroundColor: COLORS.background,
    elevation: 0,
  },
  searchInput: {
    fontSize: 14,
  },
  chipRow: {
    flexDirection: 'row',
    marginTop: 8,
    gap: 8,
  },
  chip: {
    backgroundColor: COLORS.background,
    borderRadius: 0,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  footer: {
    padding: 16,
    alignItems: 'center',
  },
});
