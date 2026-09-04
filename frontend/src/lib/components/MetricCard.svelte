<script lang="ts">
  type Tone = 'default' | 'positive' | 'negative' | 'accent';

  interface Props {
    label: string;
    value: string;
    hint?: string;
    tone?: Tone;
  }

  let { label, value, hint, tone = 'default' }: Props = $props();

  const toneColor = $derived(
    tone === 'positive'
      ? 'var(--color-positive)'
      : tone === 'negative'
        ? 'var(--color-destructive)'
        : tone === 'accent'
          ? 'var(--color-accent)'
          : 'var(--color-foreground)'
  );
</script>

<div class="metric" style={`--tone-color: ${toneColor}`}>
  <div class="metric-value">{value}</div>
  <div class="metric-label">{label}</div>
  {#if hint}<div class="metric-hint">{hint}</div>{/if}
</div>

<style>
  .metric {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 0 0 14px;
    border-bottom: 1px solid var(--color-border);
    min-width: 0;
  }
  .metric-value {
    font-family: var(--font-mono);
    font-size: 1.7rem;
    font-weight: 600;
    color: var(--tone-color);
    line-height: 1.15;
    letter-spacing: -0.02em;
    overflow-wrap: anywhere;
    font-variant-numeric: tabular-nums;
  }
  .metric-label {
    font-size: 0.78rem;
    font-weight: 500;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--color-muted-foreground);
  }
  .metric-hint {
    font-size: 0.78rem;
    color: var(--color-muted-foreground);
  }
</style>
