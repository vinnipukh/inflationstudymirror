<script lang="ts">
  export interface Column {
    key: string;
    label: string;
    align?: 'left' | 'right' | 'center';
    format?: (value: unknown) => string;
    monospace?: boolean;
  }

  interface Props {
    columns: Column[];
    rows: Record<string, unknown>[];
    emptyMessage?: string;
    maxHeight?: number;
  }

  let { columns, rows, emptyMessage = 'No records returned.', maxHeight = 420 }: Props = $props();

  function rowKey(row: Record<string, unknown>, index: number): string {
    const first = columns[0]?.key;
    return first ? `${row[first]}-${index}` : String(index);
  }

  function cellAlign(column: Column): string {
    return column.align ?? 'left';
  }
</script>

{#if rows.length === 0}
  <p class="empty">{emptyMessage}</p>
{:else}
  <div class="table-wrap" style={`max-height: ${maxHeight}px`}>
    <table>
      <thead>
        <tr>
          {#each columns as column (column.key)}
            <th style={`text-align: ${cellAlign(column)}`}>{column.label}</th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each rows as row, index (rowKey(row, index))}
          <tr>
            {#each columns as column (column.key)}
              <td
                style={`text-align: ${cellAlign(column)}`}
                class:mono={column.monospace ?? false}
              >
                {column.format ? column.format(row[column.key]) : String(row[column.key] ?? '')}
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .empty {
    color: var(--color-muted-foreground);
    font-size: 0.88rem;
    padding: 8px 0;
  }
  .table-wrap {
    overflow: auto;
    border-top: 2px solid var(--color-foreground);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.84rem;
  }
  thead th {
    position: sticky;
    top: 0;
    background: var(--color-background);
    color: var(--color-muted-foreground);
    font-weight: 600;
    font-family: var(--font-mono);
    font-size: 0.74rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    padding: 10px 12px 8px 0;
    border-bottom: 1px solid var(--color-border);
    white-space: nowrap;
    z-index: 1;
  }
  tbody td {
    padding: 7px 12px 7px 0;
    border-bottom: 1px solid var(--color-muted);
    color: var(--color-card-foreground);
    vertical-align: top;
    font-variant-numeric: tabular-nums;
  }
  tbody tr:last-child td {
    border-bottom: none;
  }
  tbody tr:hover td {
    background: var(--color-muted);
  }
  td.mono {
    font-family: var(--font-mono);
  }
</style>
