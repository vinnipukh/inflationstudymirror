<script lang="ts">
  import { onMount } from 'svelte';
  import Header from '$lib/components/Header.svelte';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import ApiAlert from '$lib/components/ApiAlert.svelte';
  import Spinner from '$lib/components/Spinner.svelte';
  import ProductExplorer from '$lib/views/ProductExplorer.svelte';
  import RetailerAverages from '$lib/views/RetailerAverages.svelte';
  import PriceMovers from '$lib/views/PriceMovers.svelte';
  import CoverageOverview from '$lib/views/CoverageOverview.svelte';
  import { fetchApi } from '$lib/api/client';
  import { resetFilters, initInventory, filters } from '$lib/stores/filters.svelte';
  import type { InventoryData, InventoryMeta } from '$lib/types/api';

  type Tab = 'product' | 'retailer' | 'movers' | 'coverage';

  let tab = $state<Tab>('product');
  let inventoryError = $state<string | null>(null);
  let inventoryErrorMeta = $state<Record<string, unknown> | null>(null);
  let inventoryLoading = $state(false);
  const inventoryWarnings = $state<string[]>([]);
  let connected = $state<boolean | null>(null);
  let checking = $state(false);

  const tabs: { id: Tab; label: string }[] = [
    { id: 'product', label: 'Product explorer' },
    { id: 'retailer', label: 'Retailer averages' },
    { id: 'movers', label: 'Price movers' },
    { id: 'coverage', label: 'Coverage overview' }
  ];

  async function loadInventory(): Promise<void> {
    inventoryError = null;
    inventoryErrorMeta = null;
    inventoryLoading = true;
    inventoryWarnings.length = 0;
    try {
      const response = await fetchApi<InventoryData, InventoryMeta>('/api/inventory');
      initInventory(response.data.retailers, response.data.min_date, response.data.max_date);
      filters.inventoryFileCount = Number(response.meta.inventory_file_count ?? response.meta.file_count ?? null);
      for (const warning of response.meta.warnings ?? []) inventoryWarnings.push(warning);
      connected = true;
    } catch (err) {
      resetFilters();
      connected = false;
      inventoryError = err instanceof Error ? err.message : String(err);
      inventoryErrorMeta = err && typeof err === 'object' && 'meta' in err ? (err as { meta?: Record<string, unknown> }).meta ?? null : null;
    } finally {
      inventoryLoading = false;
    }
  }

  async function checkHealth(): Promise<void> {
    checking = true;
    try {
      await fetchApi('/api/health');
      connected = true;
    } catch {
      connected = false;
    } finally {
      checking = false;
    }
  }

  function handleApiUrl(url: string): void {
    filters.apiBaseUrl = url;
    void loadInventory();
    void checkHealth();
  }

  function selectTab(id: Tab): void {
    tab = id;
  }

  function onKeydownTab(event: KeyboardEvent): void {
    const index = tabs.findIndex((t) => t.id === tab);
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      tab = tabs[(index + 1) % tabs.length].id;
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      tab = tabs[(index - 1 + tabs.length) % tabs.length].id;
    } else if (event.key === 'Home') {
      event.preventDefault();
      tab = tabs[0].id;
    } else if (event.key === 'End') {
      event.preventDefault();
      tab = tabs[tabs.length - 1].id;
    }
  }

  onMount(() => {
    void loadInventory();
    void checkHealth();
  });
</script>

<svelte:head>
  <title>Inflation Study Dashboard</title>
</svelte:head>

<div class="shell">
  <Header {connected} {checking} onRetry={() => void checkHealth()} />

  {#if inventoryLoading && !filters.inventoryReady}
    <div class="boot-state">
      <Spinner label="Loading inventory from the Falcon API…" />
    </div>
  {:else if inventoryError}
    <div class="boot-state">
      <ApiAlert message={inventoryError} errorMeta={inventoryErrorMeta} />
      <p class="boot-hint">
        Make sure the Falcon API is running (see <code>docs/GETTING-STARTED.md</code>) and that the base URL above is
        reachable from the browser.
      </p>
    </div>
  {:else if filters.inventoryReady}
    <div class="layout">
      <Sidebar onApplyApiUrl={handleApiUrl} {inventoryWarnings} />

      <main class="main">
        <div class="tabs" role="tablist" aria-label="Dashboard sections" tabindex="0" onkeydown={onKeydownTab}>
          {#each tabs as item (item.id)}
            <button
              type="button"
              role="tab"
              id={`tab-${item.id}`}
              aria-selected={tab === item.id}
              aria-controls={`panel-${item.id}`}
              class:active={tab === item.id}
              onclick={() => selectTab(item.id)}
            >
              {item.label}
            </button>
          {/each}
        </div>

        <div class="tab-panels">
          <div role="tabpanel" id="panel-product" aria-labelledby="tab-product" hidden={tab !== 'product'}>
            {#if tab === 'product'}<ProductExplorer />{/if}
          </div>
          <div role="tabpanel" id="panel-retailer" aria-labelledby="tab-retailer" hidden={tab !== 'retailer'}>
            {#if tab === 'retailer'}<RetailerAverages />{/if}
          </div>
          <div role="tabpanel" id="panel-movers" aria-labelledby="tab-movers" hidden={tab !== 'movers'}>
            {#if tab === 'movers'}<PriceMovers />{/if}
          </div>
          <div role="tabpanel" id="panel-coverage" aria-labelledby="tab-coverage" hidden={tab !== 'coverage'}>
            {#if tab === 'coverage'}<CoverageOverview />{/if}
          </div>
        </div>
      </main>
    </div>
  {/if}
</div>

<style>
  .shell {
    max-width: 1280px;
    margin: 0 auto;
    padding: 44px 40px 72px;
  }
  .boot-state {
    display: flex;
    flex-direction: column;
    gap: 14px;
    align-items: flex-start;
    padding: 24px 0;
    max-width: 720px;
  }
  .boot-hint {
    color: var(--color-muted-foreground);
    font-size: 0.88rem;
    margin: 0;
  }
  .boot-hint code {
    font-family: var(--font-mono);
    font-size: 0.82rem;
    background: var(--color-muted);
    padding: 1px 5px;
  }
  .layout {
    display: grid;
    grid-template-columns: 300px minmax(0, 1fr);
    gap: 56px;
    align-items: start;
  }
  .main {
    min-width: 0;
  }
  .tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    margin-bottom: 30px;
    border-bottom: 1px solid var(--color-border);
  }
  .tabs button {
    appearance: none;
    background: none;
    border: none;
    cursor: pointer;
    padding: 8px 0 10px;
    font-size: 0.88rem;
    font-weight: 500;
    font-family: var(--font-mono);
    color: var(--color-muted-foreground);
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    transition: color 200ms ease, border-color 200ms ease;
  }
  .tabs button:hover {
    color: var(--color-foreground);
  }
  .tabs button.active {
    color: var(--color-foreground);
    border-bottom-color: var(--color-foreground);
  }
  .tab-panels {
    min-width: 0;
  }
  .tab-panels > div[role='tabpanel'] {
    min-width: 0;
  }
  @media (max-width: 1024px) {
    .layout {
      grid-template-columns: 1fr;
      gap: 34px;
    }
  }
  @media (max-width: 640px) {
    .shell {
      padding: 28px 18px 48px;
    }
  }
</style>
