import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
  View,
  FlatList,
  Text,
  StyleSheet,
  RefreshControl,
} from 'react-native';
import { Searchbar, Chip, ActivityIndicator } from 'react-native-paper';
import { useQuery } from '@tanstack/react-query';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import * as api from '../api/client';
import type { Transaction } from '../api/types';
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

  const handleTransactionPress = useCallback(
    (transaction: Transaction) => {
      navigation.navigate('TransactionDetail', { id: transaction.id });
    },
    [navigation],
  );

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
