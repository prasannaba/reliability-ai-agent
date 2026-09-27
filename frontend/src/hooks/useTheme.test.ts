import { describe, expect, it } from 'vitest';
import { resolveTheme } from './useTheme';

describe('resolveTheme', () => {
  it('passes explicit choices through', () => {
    expect(resolveTheme('light')).toBe('light');
    expect(resolveTheme('dark')).toBe('dark');
  });

  it('resolves system to a valid theme', () => {
    expect(['light', 'dark']).toContain(resolveTheme('system'));
  });
});
