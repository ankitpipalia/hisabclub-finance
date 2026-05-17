import type { CSSProperties } from 'react';

type Props = {
  width?: number | string;
  height?: number | string;
  rounded?: number | string;
  className?: string;
  style?: CSSProperties;
};

export function Skeleton({
  width = '100%',
  height = 16,
  rounded = 4,
  className,
  style,
}: Props) {
  return (
    <span
      className={`hc-skeleton${className ? ` ${className}` : ''}`}
      style={{ width, height, borderRadius: rounded, ...style }}
      aria-busy="true"
      aria-hidden="true"
    />
  );
}

export function SkeletonPanel({
  rows = 3,
  rowHeight = 18,
}: {
  rows?: number;
  rowHeight?: number;
}) {
  return (
    <div className="hc-skeleton-panel">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton
          key={i}
          height={rowHeight}
          width={`${100 - i * 12}%`}
          style={{ display: 'block', marginBottom: 8 }}
        />
      ))}
    </div>
  );
}
