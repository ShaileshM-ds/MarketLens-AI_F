import { useTheme } from '../lib/theme';
import { MoonIcon, SunIcon } from './Icons';

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === 'light' ? 'dark' : 'light';
  return (
    <button type="button" className="icon-button pill" onClick={toggle} aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      {theme === 'light' ? <MoonIcon /> : <SunIcon />}
    </button>
  );
}
