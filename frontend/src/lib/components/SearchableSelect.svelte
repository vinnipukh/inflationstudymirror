<script lang="ts">
  import { normalizeSearchText, rankSearchOptions } from '$lib/utils/search';

  interface Props {
    label: string;
    options: string[];
    value?: string | null;
    placeholder?: string;
    help?: string;
    onSelect: (value: string) => void;
  }

  let { label, options, value = null, placeholder = 'Type to search…', help, onSelect }: Props = $props();

  let query = $state('');
  let open = $state(false);
  let activeIndex = $state(0);
  let inputEl: HTMLInputElement | undefined;

  const filtered = $derived(rankSearchOptions(query, options));
  const closestMatch = $derived.by<string | null>(() => {
    if (!query || filtered.length === 0) return null;
    const best = filtered[0];
    return normalizeSearchText(best) !== normalizeSearchText(query) ? best : null;
  });

  function onFocus(): void {
    if (query === '' && value) query = '';
    open = true;
    activeIndex = 0;
  }

  function onBlur(): void {
    open = false;
    query = value ?? '';
  }

  function onInput(): void {
    open = true;
    activeIndex = 0;
  }

  function pick(option: string): void {
    query = option;
    open = false;
    activeIndex = 0;
    onSelect(option);
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      open = true;
      activeIndex = Math.min(activeIndex + 1, Math.max(filtered.length - 1, 0));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (open && filtered[activeIndex]) pick(filtered[activeIndex]);
    } else if (event.key === 'Escape') {
      open = false;
      query = value ?? '';
    }
  }

  function onOptionKeydown(event: KeyboardEvent, option: string): void {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      pick(option);
    }
  }

  $effect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (inputEl && !inputEl.closest('.combobox')!.contains(target)) {
        open = false;
      }
    }
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  });
</script>

<div class="field">
  <label for="{label}-input" class="field-label">
    {label}
    {#if help}<span class="help" title={help}><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></svg></span>{/if}
  </label>
  <div class="combobox">
    <input
      id="{label}-input"
      bind:this={inputEl}
      bind:value={query}
      oninput={onInput}
      onfocus={onFocus}
      onblur={onBlur}
      onkeydown={onKeydown}
      role="combobox"
      aria-expanded={open}
      aria-controls="{label}-listbox"
      aria-autocomplete="list"
      aria-activedescendant={open && filtered[activeIndex] ? `{label}-opt-{activeIndex}` : undefined}
      placeholder={placeholder}
    />
    {#if open}
      <ul id="{label}-listbox" class="listbox" role="listbox">
        {#if query && filtered.length === 0}
          <li class="listbox-empty" role="presentation">No close matches found. Showing the full list instead.</li>
          {#each options.slice(0, 80) as option, index (option)}
            <li
              role="option"
              aria-selected={option === value}
              id="{label}-opt-{index}"
              tabindex="-1"
              class:active={index === activeIndex}
              onmouseenter={() => (activeIndex = index)}
              onmousedown={(event) => event.preventDefault()}
              onclick={() => pick(option)}
              onkeydown={(event) => onOptionKeydown(event, option)}
            >
              {option}
              {#if option === value}<span class="check">✓</span>{/if}
            </li>
          {/each}
        {:else}
          {#each filtered as option, index (option)}
            <li
              role="option"
              aria-selected={option === value}
              id="{label}-opt-{index}"
              tabindex="-1"
              class:active={index === activeIndex}
              onmouseenter={() => (activeIndex = index)}
              onmousedown={(event) => event.preventDefault()}
              onclick={() => pick(option)}
              onkeydown={(event) => onOptionKeydown(event, option)}
            >
              {option}
              {#if option === value}<span class="check">✓</span>{/if}
            </li>
          {/each}
          {#if query && closestMatch}
            <li class="listbox-hint" role="presentation">Closest match: {closestMatch}</li>
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
  .field-label {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--color-foreground);
  }
  .help {
    cursor: help;
    opacity: 0.55;
  }
  .combobox {
    position: relative;
  }
  input {
    width: 100%;
    box-sizing: border-box;
    padding: 7px 0;
    border: none;
    border-bottom: 1px solid var(--color-border);
    border-radius: 0;
    background: transparent;
    color: var(--color-card-foreground);
    font-size: 0.9rem;
    font-family: var(--font-mono);
    transition: border-color 200ms ease;
  }
  input:focus {
    outline: none;
    border-bottom-color: var(--color-foreground);
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
  .listbox li.active {
    background: var(--color-muted);
  }
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
  .check {
    font-weight: 700;
  }
</style>
