import React, { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { useAppTheme } from '../theme/AppThemeProvider';

type Props = {
  size?: number;
};

export default function BrandMark({ size = 72 }: Props) {
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(size, colors.text, colors.primary), [size, colors.text, colors.primary]);

  return (
    <View style={styles.wrap}>
      <View style={styles.leftBar} />
      <View style={styles.midBar} />
      <View style={styles.crossBar} />
      <View style={styles.rightStem} />
      <View style={styles.rightTop} />
      <View style={styles.rightBottom} />
    </View>
  );
}

const createStyles = (size: number, ink: string, accent: string) => {
  const stroke = Math.max(3, Math.round(size * 0.08));
  return StyleSheet.create({
    wrap: {
      width: size,
      height: size,
      borderWidth: stroke,
      borderColor: ink,
      position: 'relative',
      backgroundColor: 'transparent',
      overflow: 'hidden',
    },
    leftBar: {
      position: 'absolute',
      left: size * 0.18,
      top: size * 0.2,
      width: stroke,
      height: size * 0.6,
      backgroundColor: ink,
    },
    midBar: {
      position: 'absolute',
      left: size * 0.45,
      top: size * 0.2,
      width: stroke,
      height: size * 0.6,
      backgroundColor: accent,
    },
    crossBar: {
      position: 'absolute',
      left: size * 0.18,
      top: size * 0.48,
      width: size * 0.28,
      height: stroke,
      backgroundColor: ink,
    },
    rightStem: {
      position: 'absolute',
      left: size * 0.63,
      top: size * 0.2,
      width: stroke,
      height: size * 0.6,
      backgroundColor: accent,
    },
    rightTop: {
      position: 'absolute',
      left: size * 0.63,
      top: size * 0.2,
      width: size * 0.16,
      height: stroke,
      backgroundColor: accent,
    },
    rightBottom: {
      position: 'absolute',
      left: size * 0.63,
      top: size * 0.8,
      width: size * 0.16,
      height: stroke,
      backgroundColor: accent,
    },
  });
};
