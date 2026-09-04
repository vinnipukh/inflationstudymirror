<script lang="ts">
  import { themeState, effectiveTheme, toggleTheme } from '$lib/themes.svelte';

  interface Props {
    connected: boolean | null;
    checking: boolean;
    onRetry: () => void;
  }
  let { connected, checking, onRetry }: Props = $props();

  let themeLabel = $derived(themeState.mode === 'auto' ? 'Auto' : themeState.mode === 'dark' ? 'Dark' : 'Light');
</script>

<header class="header">
  <div class="brand">
    <h1 class="wordmark">Inflation Study</h1>
    <p class="subtitle">Price tracking across Turkish retailers — Falcon API</p>
  </div>

  <div class="actions">
    <div class="status">
      {#if checking}
        <span class="dot checking" aria-hidden="true"></span>
        <span class="status-text">Checking API…</span>
      {:else if connected === true}
        <span class="dot ok" aria-hidden="true"></span>
        <span class="status-text">API connected</span>
      {:else if connected === false}
        <span class="dot bad" aria-hidden="true"></span>
        <button type="button" class="retry" onclick={onRetry}>API unreachable — retry</button>
      {:else}
        <span class="dot" aria-hidden="true"></span>
        <span class="status-text">Not checked</span>
      {/if}
    </div>

    <button type="button" class="theme-toggle" onclick={toggleTheme} aria-label="Toggle color theme">
      {#if effectiveTheme() === 'dark'}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
      {:else}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
      {/if}
      <span class="theme-name">{themeLabel}</span>
    </button>
  </div>
</header>

<style>
  .header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    padding-bottom: 18px;
    border-bottom: 1px solid var(--color-border);
    margin-bottom: 28px;
  }
  .brand {
    min-width: 0;
  }
  .wordmark {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  .subtitle {
    margin: 4px 0 0;
    font-size: 0.85rem;
    color: var(--color-muted-foreground);
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 18px;
    flex-wrap: wrap;
  }
  .status {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 0.82rem;
    color: var(--color-muted-foreground);
    font-variant-numeric: tabular-nums;
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--color-muted-foreground);
  }
  .dot.ok {
    background: var(--color-positive);
  }
  .dot.bad {
    background: var(--color-destructive);
  }
  .dot.checking {
    background: var(--color-accent);
    animation: pulse 1s ease-in-out infinite;
  }
  @keyframes pulse {
    50% {
      opacity: 0.3;
    }
  }
  .retry {
    background: none;
    border: none;
    color: var(--color-destructive);
    font-weight: 500;
    cursor: pointer;
    font-size: 0.82rem;
    font-family: inherit;
    padding: 0;
  }
  .retry:hover {
    text-decoration: underline;
  }
  .theme-toggle {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: none;
    border: none;
    color: var(--color-muted-foreground);
    cursor: pointer;
    padding: 4px 0;
    font-size: 0.82rem;
    font-family: inherit;
    font-weight: 500;
    transition: color 200ms ease;
  }
  .theme-toggle:hover {
    color: var(--color-foreground);
  }
</style>
