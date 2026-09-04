<script lang="ts">
  import Chart from '$lib/components/Chart.svelte';
  import MetricCard from '$lib/components/MetricCard.svelte';
  import DataTable, { type Column } from '$lib/components/DataTable.svelte';
  import ApiAlert from '$lib/components/ApiAlert.svelte';
  import Spinner from '$lib/components/Spinner.svelte';
  import { fetchApi } from '$lib/api/client';
  import { AsyncResource } from '$lib/utils/async.svelte';
  import { formatInt, formatDate } from '$lib/utils/format';
  import { coverageAreaOption, categoryBarOption } from '$lib/utils/chartOptions.svelte';
  import type { CoverageData, CoverageMeta } from '$lib/types/api';
  import { buildQueryMap } from '$lib/stores/filters.svelte';

  const resource = new AsyncResource<CoverageData, CoverageMeta>();

  const queryKey = $derived(JSON.stringify(buildQueryMap()));

  $effect(() => {
    void queryKey;
    resource.run(() =>
      fetchApi<CoverageData, CoverageMeta>('/api/coverage', { ...buildQueryMap(), category_limit: 20 })
    );
  });

  const data = $derived(resource.value);
  const summary = $derived(data?.summary ?? null);
  const overTime = $derived(data?.coverage_over_time ?? []);
  const categories = $derived(data?.category_coverage ?? []);
  const skipped = $derived(data?.skipped_files ?? []);

  const areaOption = $derived(coverageAreaOption(overTime, 'Tracked products over time'));
  const barOption = $derived(categoryBarOption(categories, 'Top categories by tracked products'));

  const dateRange = $derived.by<string>(() => {
    const raw = summary?.date_range as string | string[] | null | undefined;
    if (typeof raw === 'string') return raw;
    if (Array.isArray(raw)) return raw.filter(Boolean).join(' → ');
    return '-';
  });

  const skippedCount = $derived(
    summary?.skipped_file_count ?? (resource.meta?.skipped_file_count as number | undefined) ?? skipped.length
  );

  const overTimeColumns: Column[] = [
    { key: 'date', label: 'Date', format: (v) => formatDate(String(v)) },
    { key: 'retailer', label: 'Retailer' },
    { key: 'tracked_products', label: 'Tracked products', align: 'right', monospace: true, format: (v) => formatInt(Number(v)) }
  ];
  const categoryColumns: Column[] = [
    { key: 'retailer', label: 'Retailer' },
    { key: 'category', label: 'Category' },
    { key: 'products', label: 'Products', align: 'right', monospace: true, format: (v) => formatInt(Number(v)) }
  ];
  const skippedColumns: Column[] = [
    { key: 'file', label: 'File' },
    { key: 'reason', label: 'Reason' }
  ];
</script>

<section class="view">
  <h2 class="view-title">4. Dataset coverage overview</h2>

  {#if resource.error}
    <ApiAlert message={resource.error} errorMeta={resource.errorMeta} />
  {:else if resource.loading && !resource.value}
    <Spinner label="Loading coverage from /api/coverage…" />
  {:else if data}
    {#if (resource.meta?.warnings ?? []).length > 0}
      <div class="warnings">
        {#each resource.meta!.warnings! as warning (warning)}
          <ApiAlert message={warning} role="warning" />
        {/each}
      </div>
    {/if}

    <div class="metrics">
      <MetricCard label="Retailers" value={formatInt(summary?.retailer_count ?? null)} />
      <MetricCard label="Products" value={formatInt(summary?.product_count ?? null)} />
      <MetricCard label="Observations" value={formatInt(summary?.observation_count ?? null)} />
      <MetricCard label="Date range" value={dateRange} />
    </div>

    {#if overTime.length > 0}
      <div class="panel">
        <Chart option={areaOption} loading={resource.loading} ariaLabel="Tracked products over time chart" />
        <DataTable
          columns={overTimeColumns}
          rows={overTime as unknown as Record<string, unknown>[]}
          emptyMessage="No coverage-over-time records were returned for this filter selection."
        />
      </div>
    {:else}
      <p class="empty">No coverage-over-time records were returned for this filter selection.</p>
    {/if}

    {#if categories.length > 0}
      <div class="panel">
        <Chart option={barOption} loading={resource.loading} ariaLabel="Top categories by tracked products chart" />
        <DataTable
          columns={categoryColumns}
          rows={categories as unknown as Record<string, unknown>[]}
          emptyMessage="No category coverage records were returned for this filter selection."
        />
      </div>
    {:else}
      <p class="empty">No category coverage records were returned for this filter selection.</p>
    {/if}

    <div class="skipped">
      {#if skippedCount > 0}
        <ApiAlert message={`${formatInt(skippedCount)} files were skipped while loading this selection.`} role="warning" />
      {/if}
      <details>
        <summary>Skipped file diagnostics</summary>
        {#if skipped.length > 0}
          <DataTable
            columns={skippedColumns}
            rows={skipped as unknown as Record<string, unknown>[]}
            emptyMessage="No skipped file diagnostics were returned by the API."
          />
        {:else}
          <p class="empty">No skipped file diagnostics were returned by the API.</p>
        {/if}
      </details>
    </div>
  {/if}
</section>


<style>
  .view {
    display: flex;
    flex-direction: column;
    gap: 30px;
  }
  .view-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }
  .metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 20px 28px;
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .warnings {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .skipped {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .skipped details {
    border-top: 2px solid var(--color-foreground);
    padding-top: 12px;
  }
  .skipped summary {
    cursor: pointer;
    font-weight: 600;
    font-size: 0.9rem;
    font-family: var(--font-mono);
    color: var(--color-foreground);
    transition: color 200ms ease;
  }
  .skipped summary:hover {
    color: var(--color-accent);
  }
  .empty {
    color: var(--color-muted-foreground);
    font-size: 0.9rem;
  }
</style>
