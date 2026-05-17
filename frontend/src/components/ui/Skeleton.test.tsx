import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Skeleton, SkeletonPanel } from './Skeleton';

describe('<Skeleton />', () => {
  it('renders with default dimensions', () => {
    const { container } = render(<Skeleton />);
    const skeleton = container.firstChild as HTMLElement;
    expect(skeleton).toHaveClass('hc-skeleton');
    expect(skeleton).toHaveAttribute('aria-busy', 'true');
    expect(skeleton).toHaveAttribute('aria-hidden', 'true');
  });

  it('honors custom width/height/rounded', () => {
    const { container } = render(<Skeleton width={120} height={24} rounded={8} />);
    const skeleton = container.firstChild as HTMLElement;
    expect(skeleton.style.width).toBe('120px');
    expect(skeleton.style.height).toBe('24px');
    expect(skeleton.style.borderRadius).toBe('8px');
  });

  it('SkeletonPanel renders N rows with decreasing width', () => {
    const { container } = render(<SkeletonPanel rows={4} />);
    const skeletons = container.querySelectorAll('.hc-skeleton');
    expect(skeletons).toHaveLength(4);
  });
});
