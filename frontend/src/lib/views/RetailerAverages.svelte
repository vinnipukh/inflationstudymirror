<script lang="ts">
  import SearchableMultiSelect from '$lib/components/SearchableMultiSelect.svelte';
  import Chart from '$lib/components/Chart.svelte';
  import DataTable, { type Column } from '$lib/components/DataTable.svelte';
  import ApiAlert from '$lib/components/ApiAlert.svelte';
  import Spinner from '$lib/components/Spinner.svelte';
  import { fetchApi } from '$lib/api/client';
  import { AsyncResource } from '$lib/utils/async.svelte';
  import { formatCurrency, formatDate } from '$lib/utils/format';
  import { retailerAverageOption } from '$lib/utils/chartOptions.svelte';
  import type { RetailerAveragesData, RetailerAveragesMeta } from '$lib/types/api';
  import { filters, buildQueryMap } from '$lib/stores/filters.svelte';

  type Aggregation = 'Average' | 'Median';

  const resource = new AsyncResource<RetailerAveragesData, RetailerAveragesMeta>();

  let localRetailers = $state<string[]>([]);
  let aggregation = $state<Aggregation>('Average');

  const records = $derived(resource.value?.records ?? []);
  const chartOption = $derived(retailerAverageOption(records, `${aggregation} scraped price by retailer`));
  const queryKey = $derived(JSON.stringify(buildQueryMap()));

  // Reset the local retailer selection whenever the global load settings change.
  $effect(() => {
    void queryKey;
    void filters.retailerOptions.length;
    const next = filters.selectedRetailers.slice(0, Math.min(4, filters.selectedRetailers.length));
    if (JSON.stringify(next) !== JSON.stringify(localRetailers)) {
      localRetailers.length = 0;
      localRetailers.push(...next);
    }
  });

  $effect(() => {
    if (localRetailers.length === 0) return;
    const query = {
      retailer: [...localRetailers],
      start_date: buildQueryMap().start_date,
      end_date: buildQueryMap().end_date,
      max_files: buildQueryMap().max_files,
      all_history: buildQueryMap().all_history,
      aggregation
    };
    resource.run(() => fetchApi<RetailerAveragesData, RetailerAveragesMeta>('/api/retailer-averages', query));
  });

  const averageColumns: Column[] = [
    { key: 'date', label: 'Date', format: (v) => formatDate(String(v)) },
    { key: 'retailer', label: 'Retailer' },
    { key: 'price', label: 'Price (TRY)', align: 'right', monospace: true, format: (v) => formatCurrency(Number(v)) }
  ];
</script>

<section class="view">
  <h2 class="view-title">2. Retailer average price chart</h2>

  <div class="controls">
    <SearchableMultiSelect
      label="Retailers"
      options={filters.retailerOptions}
      value={localRetailers}
      placeholder="Type a few letters; misspellings are okay"
      help="Search supports close matches before choosing one or more retailers."
      onChange={(next) => {
        localRetailers.length = 0;
        localRetailers.push(...next);
      }}
    />

    <div class="radio-row" role="radiogroup" aria-label="Aggregation">
      {#each ['Average', 'Median'] as option (option)}
        <label class="radio">
          <input
            type="radio"
            name="aggregation"
            value={option}
            checked={aggregation === option}
            onchange={() => (aggregation = option as Aggregation)}
          />
          <span>{option}</span>
        </label>
      {/each}
    </div>
  </div>

  {#if localRetailers.length === 0}
    <p class="empty">Select at least one retailer to load retailer averages.</p>
  {:else if resource.error}
    <ApiAlert message={resource.error} errorMeta={resource.errorMeta} />
  {:else if resource.loading && !resource.value}
    <Spinner label="Loading retailer averages from /api/retailer-averages…" />
  {:else if records.length > 0}
    <Chart option={chartOption} loading={resource.loading} ariaLabel="Retailer average price chart" />
    <DataTable
      columns={averageColumns}
      rows={records as unknown as Record<string, unknown>[]}
      emptyMessage="No retailer average records were returned for this filter selection."
    />
    {#if (resource.meta?.warnings ?? []).length > 0}
      <div class="warnings">
        {#each resource.meta!.warnings! as warning (warning)}
          <ApiAlert message={warning} role="warning" />
        {/each}
      </div>
    {/if}
  {:else}
    <p class="empty">No retailer average records were returned for this filter selection.</p>
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
    display: flex;
    flex-direction: column;
    gap: 16px;
    max-width: 720px;
  }
  .radio-row {
    display: flex;
    gap: 24px;
    align-items: center;
    border-bottom: 1px solid var(--color-border);
    padding-bottom: 2px;
  }
  .radio {
    display: inline-flex;
    align-items: baseline;
    gap: 7px;
    font-size: 0.88rem;
    font-family: var(--font-mono);
    color: var(--color-muted-foreground);
    cursor: pointer;
    padding: 4px 0 6px;
    border-bottom: 2px solid transparent;
    margin-bottom: -3px;
    transition: color 200ms ease, border-color 200ms ease;
  }
  .radio:has(input:checked) {
    color: var(--color-foreground);
    border-bottom-color: var(--color-foreground);
  }
  .radio input {
    accent-color: var(--color-foreground);
    cursor: pointer;
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
</style>
