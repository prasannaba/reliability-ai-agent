import Button from 'react-bootstrap/Button';
import ButtonGroup from 'react-bootstrap/ButtonGroup';
import type { ThemeChoice } from '../hooks/useTheme';
import { Icon, type IconName } from './Icon';

const OPTIONS: { value: ThemeChoice; label: string; icon: IconName }[] = [
  { value: 'system', label: 'System', icon: 'system' },
  { value: 'light', label: 'Light', icon: 'sun' },
  { value: 'dark', label: 'Dark', icon: 'moon' },
];

interface ThemeToggleProps {
  choice: ThemeChoice;
  onChange: (choice: ThemeChoice) => void;
}

/** Light / dark / system theme switcher shown in the sidebar footer. */
export function ThemeToggle({ choice, onChange }: ThemeToggleProps) {
  return (
    <div className="theme-switch">
      <span className="theme-label" id="theme-switch-label">
        Theme
      </span>
      <ButtonGroup size="sm" role="group" aria-labelledby="theme-switch-label">
        {OPTIONS.map((opt) => (
          <Button
            key={opt.value}
            variant="outline-secondary"
            active={choice === opt.value}
            onClick={() => onChange(opt.value)}
            title={`${opt.label} theme${opt.value === 'system' ? ' (follows your OS setting)' : ''}`}
            aria-pressed={choice === opt.value}
          >
            <Icon name={opt.icon} size={14} /> {opt.label}
          </Button>
        ))}
      </ButtonGroup>
    </div>
  );
}
