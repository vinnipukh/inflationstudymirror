import { effectiveTheme } from '$lib/themes.svelte';

export interface ChartTheme {
  dark: boolean;
  text: string;
  axisLine: string;
  splitLine: string;
  tooltipBg: string;
  tooltipText: string;
  border: string;
  /** Categorical series palette: ink + gold + quiet grays (Swiss minimalism). */
  palette: string[];
}

/**
 * Current chart theme. Reads the effective color theme, so calling this inside
 * a component (derived/effect) keeps charts reactive to theme changes.
 */
export function getChartTheme(): ChartTheme {
  const dark = effectiveTheme() === 'dark';
  return dark
    ? {
        dark,
        text: '#a1a1aa',
        axisLine: '#3f3f46',
        splitLine: '#1e1e1e',
        tooltipBg: '#1b1b1b',
        tooltipText: '#ededed',
        border: '#3f3f46',
        palette: ['#ededed', '#e0b13c', '#a1a1aa', '#71717a', '#d4d4d8', '#9ca3af', '#78716c', '#b45309']
      }
    : {
        dark,
        text: '#71717a',
        axisLine: '#d4d4d8',
        splitLine: '#f0f0f0',
        tooltipBg: '#ffffff',
        tooltipText: '#171717',
        border: '#e5e5e5',
        palette: ['#171717', '#a16207', '#8b8b93', '#c8c8ce', '#4b4b52', '#b0b0b8', '#6b6b72', '#9a6b1f']
      };
}

/** Base grid/tooltip/axis options shared by all charts. */
export function baseChartOption(theme: ChartTheme) {
  return {
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: theme.tooltipBg,
      borderColor: theme.border,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      confine: true
    },
    textStyle: { color: theme.text, fontFamily: "'Fira Sans', system-ui, sans-serif" },
    axisPointer: { lineStyle: { color: theme.splitLine } },
    valueAxis: {
      axisLabel: { color: theme.text, fontSize: 11 },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: theme.splitLine, width: 1 } }
    },
    categoryAxis: {
      axisLabel: { color: theme.text, fontSize: 11 },
      axisLine: { lineStyle: { color: theme.axisLine, width: 1 } },
      axisTick: { show: false }
    }
  };
}
