import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import { useAppTheme } from '../theme/AppThemeProvider';

type Props = {
  compact?: boolean;
};

export default function AnimatedOrbs({ compact = false }: Props) {
  const { colors } = useAppTheme();
  const float1 = useRef(new Animated.Value(0)).current;
  const float2 = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loopA = Animated.loop(
      Animated.sequence([
        Animated.timing(float1, {
          toValue: 1,
          duration: 3200,
          useNativeDriver: true,
        }),
        Animated.timing(float1, {
          toValue: 0,
          duration: 3200,
          useNativeDriver: true,
        }),
      ]),
    );
    const loopB = Animated.loop(
      Animated.sequence([
        Animated.timing(float2, {
          toValue: 1,
          duration: 4300,
          useNativeDriver: true,
        }),
        Animated.timing(float2, {
          toValue: 0,
          duration: 4300,
          useNativeDriver: true,
        }),
      ]),
    );
    loopA.start();
    loopB.start();
    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 1800,
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: 1800,
          useNativeDriver: true,
        }),
      ]),
    );
    pulseLoop.start();
    return () => {
      loopA.stop();
      loopB.stop();
      pulseLoop.stop();
    };
  }, [float1, float2, pulse]);

  return (
    <View pointerEvents="none" style={[styles.wrap, compact && styles.compactWrap]}>
      <Animated.View
        style={[
          styles.orbLarge,
          {
            backgroundColor: colors.tintOverlay,
            transform: [
              {
                translateY: float1.interpolate({
                  inputRange: [0, 1],
                  outputRange: [0, -12],
                }),
              },
            ],
          },
        ]}
      />
      <Animated.View
        style={[
          styles.orbSmall,
          {
            backgroundColor: colors.tintOverlay,
            transform: [
              {
                translateY: float2.interpolate({
                  inputRange: [0, 1],
                  outputRange: [0, 16],
                }),
              },
            ],
          },
        ]}
      />
      <Animated.View
        style={[
          styles.bar,
          {
            backgroundColor: colors.primary,
            opacity: pulse.interpolate({
              inputRange: [0, 1],
              outputRange: [0.35, 0.85],
            }),
          },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    ...StyleSheet.absoluteFillObject,
    overflow: 'hidden',
  },
  compactWrap: {
    borderRadius: 0,
  },
  orbLarge: {
    position: 'absolute',
    width: 150,
    height: 150,
    borderRadius: 0,
    right: -36,
    top: -44,
    transform: [{ rotate: '18deg' }],
  },
  orbSmall: {
    position: 'absolute',
    width: 96,
    height: 96,
    borderRadius: 0,
    left: -22,
    bottom: -22,
    transform: [{ rotate: '-12deg' }],
  },
  bar: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 10,
    height: 3,
  },
});
