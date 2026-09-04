<script lang="ts">
  interface Props {
    label?: string;
    inline?: boolean;
  }
  let { label = 'Loading…', inline = false }: Props = $props();
</script>

<div class="spinner-wrap" class:inline>
  <span class="spinner" aria-hidden="true"></span>
  <span class="label">{label}</span>
</div>

<style>
  .spinner-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 36px 0;
    color: var(--color-muted-foreground);
    font-size: 0.85rem;
  }
  .spinner-wrap.inline {
    padding: 4px 0;
    justify-content: flex-start;
  }
  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid var(--color-border);
    border-top-color: var(--color-foreground);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation-duration: 2.5s;
    }
  }
</style>
