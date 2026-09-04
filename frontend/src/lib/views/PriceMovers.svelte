<script lang="ts">
  import SearchableSelect from '$lib/components/SearchableSelect.svelte';
  import DataTable, { type Column } from '$lib/components/DataTable.svelte';
  import ApiAlert from '$lib/components/ApiAlert.svelte';
  import Spinner from '$lib/components/Spinner.svelte';
  import { fetchApi } from '$lib/api/client';
  import { AsyncResource } from '$lib/utils/async.svelte';
  import { formatCurrency, formatPercent, formatDate } from '$lib/utils/format';
  import type { MoversData, MoversMeta } from '$lib/types/api';
  import { filters, buildQueryMap } from '$lib/stores/filters.svelte';

  const resource = new AsyncResource<MoversData, MoversMeta>();

  let scopeRetailer = $state<string>('All retailers');
  let limit = $state(10);

  const scopeOptions = $derived.by<string[]>(() => {
    const selected = filters.selectedRetailers.filter((name) => filters.retailerOptions.includes(name));
    return ['All retailers', ...selected];
  });

  const queryKey = $derived(JSON.stringify(buildQueryMap()));

  $effect(() => {
    void queryKey;
    const next = scopeOptions;
    if (!next.includes(scopeRetailer)) {
      scopeRetailer = next[0] ?? 'All retailers';
    }
  });

  $effect(() => {
    if (scopeRetailer === null) return;
    const query = { ...buildQueryMap(), scope_retailer: scopeRetailer, limit };
    resource.run(() => fetchApi<MoversData, MoversMeta>('/api/movers', query));
  });

  const drops = $derived(resource.value?.biggest_drops ?? []);
  const gains = $derived(resource.value?.biggest_gains ?? []);
  const hasResults = $derived(drops.length > 0 || gains.length > 0);

  const dropColumns: Column[] = [
    { key: 'retailer', label: 'Retailer' },
    { key: 'product_name', label: 'Product' },
    { key: 'latest_price', label: 'Latest', align: 'right', monospace: true, format: (v) => formatCurrency(Number(v)) },
    { key: 'max_price', label: 'Peak', align: 'right', monospace: true, format: (v) => formatCurrency(Number(v)) },
    { key: 'savings_vs_peak', label: 'Saved ₺', align: 'right', monospace: true, format: (v) => formatCurrency(Number(v)) },
    { key: 'drop_from_peak_pct', label: 'Drop %', align: 'right', monospace: true, format: (v) => formatPercent(Number(v)) },
    { key: 'last_seen', label: 'Last seen', format: (v) => formatDate(String(v)) }
  ];

  const gainColumns: Column[] = [
    { key: 'retailer', label: 'Retailer' },
    { key: 'product_name', label: 'Product' },
    { key: 'first_price', label: 'First', align: 'right', monospace: true, format: (v) => formatCurrency(Number(v)) },
    { key: 'latest_price', label: 'Latest', align: 'right', monospace: true, format: (v) => formatCurrency(Number(v)) },
    { key: 'change_since_first_pct', label: 'Change %', align: 'right', monospace: true, format: (v) => formatPercent(Number(v)) },
    { key: 'first_seen', label: 'First seen', format: (v) => formatDate(String(v)) },
    { key: 'last_seen', label: 'Last seen', format: (v) => formatDate(String(v)) }
  ];
</script>

<section class="view">
  <h2 class="view-title">3. Biggest price movers</h2>

  <div class="controls">
    <SearchableSelect
      label="Retailer scope"
      options={scopeOptions}
      value={scopeRetailer}
      placeholder="All retailers"
      onSelect={(value) => (scopeRetailer = value)}
    />
    <div class="slider-field">
      <label class="field-label" for="mover-count">
        Rows to show: <strong class="value">{limit}</strong>
      </label>
      <input id="mover-count" type="range" min="5" max="30" step="1" bind:value={limit} />
    </div>
  </div>

  {#if resource.error}
    <ApiAlert message={resource.error} errorMeta={resource.errorMeta} />
  {:else if resource.loading && !resource.value}
    <Spinner label="Loading price movers from /api/movers…" />
  {:else if hasResults}
    {#if (resource.meta?.warnings ?? []).length > 0}
      <div class="warnings">
        {#each resource.meta!.warnings! as warning (warning)}
          <ApiAlert message={warning} role="warning" />
        {/each}
      </div>
    {/if}
    <div class="mover-columns">
      <div class="mover-card">
        <h3>Biggest drops vs. peak</h3>
        <DataTable
          columns={dropColumns}
          rows={drops as unknown as Record<string, unknown>[]}
          emptyMessage="No price drops were returned for this selection."
          maxHeight={520}
        />
      </div>
      <div class="mover-card">
        <h3>Biggest gains since first observation</h3>
        <DataTable
          columns={gainColumns}
          rows={gains as unknown as Record<string, unknown>[]}
          emptyMessage="No price gains were returned for this selection."
          maxHeight={520}
        />
      </div>
    </div>
    {#if (resource.meta?.eligible_product_count ?? 0) > 0}
      <p class="hint">
        Based on {resource.meta!.eligible_product_count!.toLocaleString('tr-TR')} eligible products with repeated observations.
      </p>
    {/if}
  {:else}
    <p class="empty">Not enough repeated product observations for this selection.</p>
  {/if}
</section>


<style>
  .view {
    display: flex;
    flex-direction: column;
    gap: 22px;
  }
  .view-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }
  .controls {
    display: grid;
    grid-template-columns: minmax(220px, 1fr) minmax(220px, 0.8fr);
    gap: 32px;
    align-items: end;
    max-width: 720px;
  }
  .slider-field {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .field-label {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--color-foreground);
  }
  .value {
    font-family: var(--font-mono);
    color: var(--color-foreground);
  }
  input[type='range'] {
    width: 100%;
    accent-color: var(--color-foreground);
    cursor: pointer;
  }
  .mover-columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 40px;
  }
  .mover-columns > div {
    min-width: 0;
  }
  .mover-card h3 {
    margin: 0 0 10px;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--color-foreground);
  }
  .warnings {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .empty {
    color: var(--color-muted-foreground);
    font-size: 0.9rem;
  }
  .hint {
    color: var(--color-muted-foreground);
    font-size: 0.8rem;
    margin: 0;
  }
  @media (max-width: 960px) {
    .controls,
    .mover-columns {
      grid-template-columns: 1fr;
    }
  }
</style>
