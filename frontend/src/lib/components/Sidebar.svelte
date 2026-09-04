<script lang="ts">
  import SearchableMultiSelect from '$lib/components/SearchableMultiSelect.svelte';
  import ApiAlert from '$lib/components/ApiAlert.svelte';
  import { filters, buildQueryMap } from '$lib/stores/filters.svelte';
  import { API_BASE_URL } from '$lib/api/client';

  interface Props {
    onApplyApiUrl: (url: string) => void;
    inventoryWarnings: string[];
  }
  let { onApplyApiUrl, inventoryWarnings }: Props = $props();

  let urlDraft = $state(filters.apiBaseUrl);

  // Local drafts for inputs; apply on change so the UI stays responsive.
  let startDraft = $state(filters.startDate);
  let endDraft = $state(filters.endDate);
  let maxFilesDraft = $state(filters.maxFiles);
  let allHistoryDraft = $state(filters.allHistory);

  $effect(() => {
    startDraft = filters.startDate;
  });
  $effect(() => {
    endDraft = filters.endDate;
  });
  $effect(() => {
    maxFilesDraft = filters.maxFiles;
  });
  $effect(() => {
    allHistoryDraft = filters.allHistory;
  });

  let queryCount = $derived(Object.keys(buildQueryMap()).length);

  function applyStart(): void {
    if (startDraft !== filters.startDate) filters.startDate = startDraft;
  }
  function applyEnd(): void {
    if (endDraft !== filters.endDate) filters.endDate = endDraft;
  }
  function applyMaxFiles(): void {
    if (maxFilesDraft !== filters.maxFiles) filters.maxFiles = maxFilesDraft;
  }
  function applyAllHistory(): void {
    if (allHistoryDraft !== filters.allHistory) filters.allHistory = allHistoryDraft;
  }
</script>



<aside class="sidebar" aria-label="Dashboard settings">
  <section class="section">
    <h2 class="section-title">API settings</h2>
    <div class="field">
      <label class="field-label" for="api-url">Falcon API base URL</label>
      <div class="url-row">
        <input
          id="api-url"
          type="text"
          bind:value={urlDraft}
          spellcheck="false"
          placeholder="http://localhost:8000"
        />
        <button
          type="button"
          class="apply"
          onclick={() => onApplyApiUrl(urlDraft.trim() || 'http://localhost:8000')}
          disabled={urlDraft.trim() === filters.apiBaseUrl}
        >
          Apply
        </button>
      </div>
      {#if filters.apiBaseUrl !== API_BASE_URL}
        <p class="hint">Build default: {API_BASE_URL}</p>
      {/if}
    </div>

    {#if inventoryWarnings.length > 0}
      <div class="warnings">
        {#each inventoryWarnings as warning (warning)}
          <ApiAlert message={warning} role="warning" />
        {/each}
      </div>
    {/if}

    {#if filters.inventoryReady}
      <dl class="inventory-meta">
        <div><dt>Inventory files</dt><dd>{filters.inventoryFileCount?.toLocaleString('tr-TR') ?? '-'}</dd></div>
        <div><dt>Earliest date</dt><dd>{filters.inventoryMinDate?.slice(0, 10) ?? '-'}</dd></div>
        <div><dt>Latest date</dt><dd>{filters.inventoryMaxDate?.slice(0, 10) ?? '-'}</dd></div>
      </dl>
    {/if}
  </section>

  {#if filters.inventoryReady}
    <section class="section">
      <h2 class="section-title">Load settings</h2>

      <SearchableMultiSelect
        label="Retailers to load"
        options={filters.retailerOptions}
        value={filters.selectedRetailers}
        placeholder="Type a few letters; misspellings are okay"
        help="Loading fewer retailers is much faster. Add the large datasets only when needed."
        onChange={(next) => { filters.selectedRetailers.length = 0; filters.selectedRetailers.push(...next); }}
      />

      <div class="dates">
        <div class="field">
          <label class="field-label" for="start-date">Start date</label>
          <input
            id="start-date"
            type="date"
            min={filters.inventoryMinDate?.slice(0, 10) ?? undefined}
            max={filters.inventoryMaxDate?.slice(0, 10) ?? undefined}
            value={startDraft ?? ''}
            onchange={applyStart}
          />
        </div>
        <div class="field">
          <label class="field-label" for="end-date">End date</label>
          <input
            id="end-date"
            type="date"
            min={filters.inventoryMinDate?.slice(0, 10) ?? undefined}
            max={filters.inventoryMaxDate?.slice(0, 10) ?? undefined}
            value={endDraft ?? ''}
            onchange={applyEnd}
          />
        </div>
      </div>

      <div class="field">
        <label class="field-label" for="max-files">
          Max CSV files per retailer: <strong class="value">{maxFilesDraft}</strong>
        </label>
        <input
          id="max-files"
          type="range"
          min="10"
          max="160"
          step="5"
          value={maxFilesDraft}
          oninput={(event) => {
            maxFilesDraft = Number((event.currentTarget as HTMLInputElement).value);
            applyMaxFiles();
          }}
          disabled={allHistoryDraft}
        />
        <p class="hint">Uses the newest files in the selected date range. Raise this for deeper history; lower it for faster loading.</p>
      </div>

      <label class="checkbox">
        <input type="checkbox" checked={allHistoryDraft} onchange={applyAllHistory} />
        <span>Load all files in date range</span>
      </label>
      {#if allHistoryDraft}
        <p class="hint warn">All-history mode sends all_history=true and max_files=0 to the API.</p>
      {/if}
    </section>

    <footer class="sidebar-footer">
      <p>Prepared {queryCount} common query parameter{queryCount === 1 ? '' : 's'} for data endpoints.</p>
    </footer>
  {/if}
</aside>

<style>
  .sidebar {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .section {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 18px 0;
    border-bottom: 1px solid var(--color-border);
  }
  .section:first-child {
    padding-top: 0;
  }
  .section-title {
    margin: 0;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--color-muted-foreground);
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .field-label {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--color-foreground);
  }
  .url-row {
    display: flex;
    gap: 10px;
    align-items: center;
  }
  input[type='text'],
  input[type='date'] {
    width: 100%;
    box-sizing: border-box;
    padding: 7px 0;
    border: none;
    border-bottom: 1px solid var(--color-border);
    border-radius: 0;
    background: transparent;
    color: var(--color-card-foreground);
    font-size: 0.88rem;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    transition: border-color 200ms ease;
  }
  input[type='text']:focus,
  input[type='date']:focus {
    outline: none;
    border-bottom-color: var(--color-foreground);
  }
  .apply {
    flex: none;
    background: none;
    border: none;
    border-bottom: 1px solid var(--color-foreground);
    color: var(--color-foreground);
    border-radius: 0;
    padding: 6px 2px;
    font-weight: 600;
    font-size: 0.82rem;
    cursor: pointer;
    font-family: inherit;
    transition: opacity 200ms ease;
  }
  .apply:disabled {
    opacity: 0.35;
    cursor: default;
    border-bottom-color: var(--color-border);
  }
  .apply:not(:disabled):hover {
    opacity: 0.7;
  }
  .hint {
    margin: 0;
    font-size: 0.78rem;
    color: var(--color-muted-foreground);
  }
  .hint.warn {
    color: var(--color-accent);
  }
  .warnings {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .inventory-meta {
    margin: 0;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2px 16px;
  }
  .inventory-meta div {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 4px 0;
  }
  .inventory-meta dt {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--color-muted-foreground);
  }
  .inventory-meta dd {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 0.9rem;
    color: var(--color-foreground);
  }
  .dates {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  input[type='range'] {
    width: 100%;
    accent-color: var(--color-foreground);
    cursor: pointer;
  }
  .value {
    font-family: var(--font-mono);
    color: var(--color-foreground);
  }
  .checkbox {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.88rem;
    color: var(--color-card-foreground);
    cursor: pointer;
  }
  .checkbox input {
    accent-color: var(--color-foreground);
    width: 15px;
    height: 15px;
    cursor: pointer;
  }
  .sidebar-footer {
    padding-top: 14px;
    font-size: 0.78rem;
    color: var(--color-muted-foreground);
  }
  .sidebar-footer p {
    margin: 0;
  }
</style>
