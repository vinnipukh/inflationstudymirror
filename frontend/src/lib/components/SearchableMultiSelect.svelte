<script lang="ts">
  import { normalizeSearchText, rankSearchOptions } from '$lib/utils/search';

  interface Props {
    label: string;
    options: string[];
    value: string[];
    placeholder?: string;
    help?: string;
    maxVisible?: number;
    onChange: (value: string[]) => void;
  }

  let {
    label,
    options,
    value,
    placeholder = 'Type to search…',
    help,
    maxVisible = 240,
    onChange
  }: Props = $props();

  let query = $state('');
  let open = $state(false);
  let activeIndex = $state(0);
  let inputEl: HTMLInputElement | undefined;

  const freeOptions = $derived(
    options.filter((option) => !value.includes(option)).slice(0, maxVisible)
  );
  const filtered = $derived(rankSearchOptions(query, freeOptions));
  const closestMatch = $derived.by<string | null>(() => {
    if (!query || filtered.length === 0) return null;
    const best = filtered[0];
    return normalizeSearchText(best) !== normalizeSearchText(query) ? best : null;
  });

  function toggle(option: string): void {
    const next = value.includes(option) ? value.filter((item) => item !== option) : [...value, option];
    onChange(next);
    query = '';
    activeIndex = 0;
    inputEl?.focus();
  }

  function remove(option: string): void {
    onChange(value.filter((item) => item !== option));
  }

  function clearAll(): void {
    onChange([]);
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      open = true;
      activeIndex = Math.min(activeIndex + 1, filtered.length - 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (open && filtered[activeIndex]) toggle(filtered[activeIndex]);
    } else if (event.key === 'Backspace' && !query && value.length) {
      remove(value[value.length - 1]);
    } else if (event.key === 'Escape') {
      open = false;
    }
  }

  $effect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (inputEl && !inputEl.closest('.multi')!.contains(target)) {
        open = false;
      }
    }
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  });
</script>

<div class="field multi" class:open>
  <div class="field-head">
    <label for="{label}-input" class="field-label">
      {label}
      {#if help}<span class="help" title={help}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></svg></span>{/if}
    </label>
    {#if value.length > 0}
      <button type="button" class="clear" onclick={clearAll}>Clear all</button>
    {/if}
  </div>

  <div class="control" class:open role="combobox" aria-expanded={open} aria-controls="{label}-listbox" aria-haspopup="listbox">
    <div class="chips">
      {#each value as selected (selected)}
        <span class="chip">
          {selected}
          <button type="button" class="chip-remove" aria-label={`Remove ${selected}`} onclick={() => remove(selected)}>×</button>
        </span>
      {/each}
      <input
        id="{label}-input"
        bind:this={inputEl}
        bind:value={query}
        oninput={() => (open = true)}
        onfocus={() => (open = true)}
        onkeydown={onKeydown}
        aria-autocomplete="list"
        aria-controls="{label}-listbox"
        aria-activedescendant={open && filtered[activeIndex] ? `{label}-opt-{activeIndex}` : undefined}
        placeholder={value.length ? '' : placeholder}
      />
    </div>

    {#if open}
      <ul id="{label}-listbox" class="listbox" role="listbox" aria-multiselectable="true">
        {#if query && filtered.length === 0}
          <li class="listbox-empty">No close matches found. Showing the current selection instead.</li>
          {#each freeOptions.slice(0, 80) as option, index (option)}
            <li
              role="option"
              aria-selected="false"
              id="{label}-opt-{index}"
              class:active={index === activeIndex}
              onmouseenter={() => (activeIndex = index)}
              tabindex="-1"
              onmousedown={(event) => event.preventDefault()}
              onclick={() => toggle(option)}
              onkeydown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  toggle(option);
                }
              }}
            >
              {option}
            </li>
          {/each}
        {:else}
          {#each filtered as option, index (option)}
            <li
              role="option"
              aria-selected="false"
              id="{label}-opt-{index}"
              class:active={index === activeIndex}
              onmouseenter={() => (activeIndex = index)}
              tabindex="-1"
              onmousedown={(event) => event.preventDefault()}
              onclick={() => toggle(option)}
              onkeydown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  toggle(option);
                }
              }}
            >
              {option}
              <span class="add">+</span>
            </li>
          {/each}
          {#if filtered.length === 0 && !query}
            <li class="listbox-empty">All options are already selected.</li>
          {/if}
          {#if query && closestMatch}
            <li class="listbox-hint">Closest match: {closestMatch}</li>
          {/if}
        {/if}
      </ul>
    {/if}
  </div>
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .field-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .field-label {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--color-foreground);
  }
  .help {
    cursor: help;
    opacity: 0.55;
  }
  .clear {
    background: none;
    border: none;
    color: var(--color-muted-foreground);
    font-size: 0.78rem;
    cursor: pointer;
    padding: 0;
    font-family: inherit;
  }
  .clear:hover {
    color: var(--color-foreground);
  }
  .control {
    position: relative;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    align-items: center;
    padding: 7px 0;
    border-bottom: 1px solid var(--color-border);
    min-height: 36px;
    cursor: text;
    transition: border-color 200ms ease;
  }
  .control.open .chips {
    border-bottom-color: var(--color-foreground);
  }
  input {
    flex: 1;
    min-width: 140px;
    border: none;
    outline: none;
    background: transparent;
    color: var(--color-card-foreground);
    font-size: 0.9rem;
    font-family: var(--font-mono);
    padding: 3px 0;
  }
  .chip {
    display: inline-flex;
    align-items: baseline;
    gap: 6px;
    color: var(--color-foreground);
    font-size: 0.84rem;
    font-family: var(--font-mono);
    border-bottom: 1px solid var(--color-border);
    padding: 1px 0 2px;
  }
  .chip-remove {
    background: none;
    border: none;
    color: var(--color-muted-foreground);
    font-size: 1rem;
    line-height: 1;
    cursor: pointer;
    padding: 0 2px;
  }
  .chip-remove:hover {
    color: var(--color-destructive);
  }
  .listbox {
    position: absolute;
    z-index: 30;
    top: calc(100% + 6px);
    left: 0;
    right: 0;
    max-height: 280px;
    overflow-y: auto;
    list-style: none;
    margin: 0;
    padding: 6px 0;
    background: var(--color-card);
    border: 1px solid var(--color-border);
    border-top: 2px solid var(--color-foreground);
    border-radius: 0;
    box-shadow: 0 14px 34px -18px rgba(0, 0, 0, 0.35);
  }
  .listbox li {
    padding: 7px 12px;
    font-size: 0.86rem;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    gap: 8px;
    color: var(--color-card-foreground);
    font-variant-numeric: tabular-nums;
    transition: background 200ms ease;
  }
  .listbox li.active,
  .listbox li:hover {
    background: var(--color-muted);
  }
  .listbox-empty {
    color: var(--color-muted-foreground);
    font-style: italic;
    cursor: default !important;
  }
  .listbox-hint {
    color: var(--color-accent);
    font-size: 0.8rem !important;
    cursor: default !important;
  }
  .add {
    font-weight: 700;
    color: var(--color-muted-foreground);
  }
</style>
