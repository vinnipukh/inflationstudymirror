<script lang="ts">
  import * as echarts from 'echarts/core';
  import { LineChart, BarChart } from 'echarts/charts';
  import {
    GridComponent,
    TooltipComponent,
    LegendComponent,
    DatasetComponent,
    MarkLineComponent,
    MarkPointComponent
  } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';
  import type { EChartsCoreOption } from 'echarts/core';

  echarts.use([
    LineChart,
    BarChart,
    GridComponent,
    TooltipComponent,
    LegendComponent,
    DatasetComponent,
    MarkLineComponent,
    MarkPointComponent,
    CanvasRenderer
  ]);

  interface Props {
    option: EChartsCoreOption;
    height?: number;
    loading?: boolean;
    ariaLabel?: string;
  }

  let { option, height = 420, loading = false, ariaLabel = 'Chart' }: Props = $props();

  let container: HTMLDivElement;
  let chart: echarts.ECharts | undefined;

  $effect(() => {
    if (!container) return;
    if (!chart) {
      chart = echarts.init(container, undefined, { renderer: 'canvas' });
      const observer = new ResizeObserver(() => chart?.resize());
      observer.observe(container);
      return () => {
        observer.disconnect();
        chart?.dispose();
        chart = undefined;
      };
    }
  });

  $effect(() => {
    if (chart) chart.setOption(option, { notMerge: true, lazyUpdate: true });
  });

  $effect(() => {
    if (!chart) return;
    if (loading) {
      chart.showLoading('default', { text: 'Loading…', color: '#1E40AF', textColor: '#64748B' });
    } else {
      chart.hideLoading();
    }
  });
</script>

<div class="chart" role="img" aria-label={ariaLabel} style={`height: ${height}px`}>
  <div bind:this={container} class="chart-canvas"></div>
</div>

<style>
  .chart {
    width: 100%;
    position: relative;
  }
  .chart-canvas {
    width: 100%;
    height: 100%;
  }
</style>
