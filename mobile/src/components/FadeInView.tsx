import React, { useEffect, useRef } from 'react';
import { Animated, type ViewStyle } from 'react-native';

type Props = {
  children: React.ReactNode;
  duration?: number;
  delay?: number;
  fromY?: number;
  style?: ViewStyle | ViewStyle[];
};

export default function FadeInView({
  children,
  duration = 340,
  delay = 0,
  fromY = 14,
  style,
}: Props) {
  const anim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const timing = Animated.timing(anim, {
      toValue: 1,
      duration,
      delay,
      useNativeDriver: true,
    });
    timing.start();
    return () => {
      timing.stop();
    };
  }, [anim, delay, duration]);

  return (
    <Animated.View
      style={[
        style,
        {
          opacity: anim,
          transform: [
            {
              translateY: anim.interpolate({
                inputRange: [0, 1],
                outputRange: [fromY, 0],
              }),
            },
          ],
        },
      ]}
    >
      {children}
    </Animated.View>
  );
}
