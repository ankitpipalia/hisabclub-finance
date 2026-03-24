import type { ThemeMode } from '../theme/ThemeProvider';
import { useTheme } from '../theme/ThemeProvider';

const MODES: Array<{ value: ThemeMode; label: string }> = [
  { value: 'auto', label: 'Auto' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

export default function ThemeModeSelect() {
  const { mode, setMode } = useTheme();

  return (
    <div>
      <p className="hc-label">Theme</p>
      <div className="hc-inline-actions" role="radiogroup" aria-label="Theme mode">
        {MODES.map((item) => {
          const selected = mode === item.value;
          return (
            <button
              key={item.value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => setMode(item.value)}
              className={`hc-btn ${selected ? 'hc-btn-solid' : 'hc-btn-ghost'}`}
            >
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
