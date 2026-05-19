import { useFY } from '../contexts/FYContext';

/** Compact FY dropdown rendered in the global app header. */
export function FYSelector() {
  const { currentFY, setCurrentFY, supportedFYs } = useFY();
  return (
    <label
      className="hc-panel-sub"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: '0.78rem',
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
      }}
      data-testid="fy-selector"
    >
      FY
      <select
        value={currentFY}
        onChange={(e) => setCurrentFY(e.target.value)}
        className="hc-select"
        style={{ padding: '4px 8px', fontSize: '0.85rem' }}
        aria-label="Financial year"
      >
        {supportedFYs.map((fy) => (
          <option key={fy} value={fy}>
            {fy}
          </option>
        ))}
      </select>
    </label>
  );
}
