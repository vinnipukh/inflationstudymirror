export type Theme = 'auto' | 'light' | 'dark';

const STORAGE_KEY = 'inflation-dashboard-theme';

function initialTheme(): Theme {
  if (typeof localStorage === 'undefined') return 'auto';
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === 'light' || stored === 'dark' || stored === 'auto' ? stored : 'auto';
}

export const themeState = $state({ mode: initialTheme() as Theme });

export function effectiveTheme(): 'light' | 'dark' {
  const mode = themeState.mode;
  if (mode === 'light' || mode === 'dark') return mode;
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}

export function setTheme(next: Theme): void {
  themeState.mode = next;
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, next);
  }
}

export function toggleTheme(): void {
  setTheme(effectiveTheme() === 'dark' ? 'light' : 'dark');
}
