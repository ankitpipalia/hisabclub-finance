import { Text, type TextStyle } from 'react-native';
import { formatAmount } from '../utils/formatters';
import { useAppTheme } from '../theme/AppThemeProvider';

interface Props {
  amount: number;
  direction: string;
  style?: TextStyle;
}

export default function AmountText({ amount, direction, style }: Props) {
  const { colors } = useAppTheme();
  const color = direction === 'credit' ? colors.credit : colors.debit;
  const prefix = direction === 'credit' ? '+' : '';

  return (
    <Text style={[{ color, fontWeight: '600', fontSize: 14 }, style]}>
      {prefix}{formatAmount(amount)}
    </Text>
  );
}
