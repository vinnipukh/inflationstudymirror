import type { EChartsCoreOption } from 'echarts/core';
import { baseChartOption, getChartTheme } from '$lib/utils/chartTheme.svelte';
import type {
  ProductHistoryPoint,
  RetailerAverageRecord,
  CoverageOverTimeRecord,
  CategoryCoverageRecord
} from '$lib/types/api';

function dateLabel(value: string): string {
  return value.slice(0, 10);
}

export function productPriceOption(points: ProductHistoryPoint[], title: string): EChartsCoreOption {
  const t = getChartTheme();
  return {
    ...baseChartOption(t),
    title: {
      text: title,
      left: 0,
      textStyle: { color: t.text, fontSize: 14, fontWeight: 600 }
    },
    tooltip: { ...baseChartOption(t).tooltip, trigger: 'axis' },
    xAxis: {
      type: 'category',
      name: 'Date',
      nameLocation: 'middle',
      nameGap: 30,
      data: points.map((p) => dateLabel(p.date)),
      axisLabel: { color: t.text },
      axisLine: { lineStyle: { color: t.axisLine } },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      name: 'Price (TRY)',
      nameTextStyle: { color: t.text },
      axisLabel: { color: t.text },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: t.splitLine } }
    },
    series: [
      {
        name: 'price',
        type: 'line',
        data: points.map((p) => p.price),
        showSymbol: true,
        symbolSize: 7,
        connectNulls: true,
        lineStyle: { width: 2.5, color: t.palette[0] },
        itemStyle: { color: t.palette[0] },
        areaStyle: { color: t.palette[0], opacity: 0.08 }
      }
    ]
  };
}

export function retailerAverageOption(records: RetailerAverageRecord[], title: string): EChartsCoreOption {
  const t = getChartTheme();
  const byRetailer = new Map<string, { dates: string[]; prices: (number | null)[] }>();
  for (const record of records) {
    let entry = byRetailer.get(record.retailer);
    if (!entry) {
      entry = { dates: [], prices: [] };
      byRetailer.set(record.retailer, entry);
    }
    entry.dates.push(dateLabel(record.date));
    entry.prices.push(record.price);
  }
  const retailerNames = [...byRetailer.keys()];
  const dates = [...byRetailer.values()][0]?.dates ?? [];
  return {
    ...baseChartOption(t),
    title: { text: title, left: 0, textStyle: { color: t.text, fontSize: 14, fontWeight: 600 } },
    legend: { top: 28, type: 'scroll', textStyle: { color: t.text }, itemWidth: 14, itemHeight: 8 },
    grid: { left: 8, right: 16, top: 76, bottom: 8, containLabel: true },
    tooltip: { ...baseChartOption(t).tooltip, trigger: 'axis' },
    xAxis: {
      type: 'category',
      name: 'Date',
      nameLocation: 'middle',
      nameGap: 30,
      data: dates,
      axisLabel: { color: t.text },
      axisLine: { lineStyle: { color: t.axisLine } },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      name: 'Price (TRY)',
      nameTextStyle: { color: t.text },
      axisLabel: { color: t.text },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: t.splitLine } }
    },
    series: retailerNames.map((name, index) => ({
      name,
      type: 'line' as const,
      data: byRetailer.get(name)!.prices,
      showSymbol: false,
      connectNulls: true,
      lineStyle: { width: 2 },
      itemStyle: { color: t.palette[index % t.palette.length] }
    }))
  };
}

export function coverageAreaOption(records: CoverageOverTimeRecord[], title: string): EChartsCoreOption {
  const t = getChartTheme();
  const byRetailer = new Map<string, Map<string, number>>();
  const allDates: string[] = [];
  for (const record of records) {
    const d = dateLabel(record.date);
    let retailerMap = byRetailer.get(record.retailer);
    if (!retailerMap) {
      retailerMap = new Map();
      byRetailer.set(record.retailer, retailerMap);
    }
    retailerMap.set(d, record.tracked_products);
    if (!allDates.includes(d)) allDates.push(d);
  }
  allDates.sort();
  const retailerNames = [...byRetailer.keys()];
  return {
    ...baseChartOption(t),
    title: { text: title, left: 0, textStyle: { color: t.text, fontSize: 14, fontWeight: 600 } },
    legend: { top: 28, type: 'scroll', textStyle: { color: t.text }, itemWidth: 14, itemHeight: 8 },
    grid: { left: 8, right: 16, top: 76, bottom: 8, containLabel: true },
    tooltip: { ...baseChartOption(t).tooltip, trigger: 'axis' },
    xAxis: {
      type: 'category',
      name: 'Date',
      nameLocation: 'middle',
      nameGap: 30,
      data: allDates,
      axisLabel: { color: t.text },
      axisLine: { lineStyle: { color: t.axisLine } },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      name: 'Tracked products',
      nameTextStyle: { color: t.text },
      axisLabel: { color: t.text },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: t.splitLine } }
    },
    series: retailerNames.map((name, index) => ({
      name,
      type: 'line' as const,
      data: allDates.map((d) => byRetailer.get(name)?.get(d) ?? null),
      showSymbol: false,
      connectNulls: true,
      lineStyle: { width: 2 },
      itemStyle: { color: t.palette[index % t.palette.length] },
      areaStyle: { color: t.palette[index % t.palette.length], opacity: 0.18 }
    }))
  };
}

export function categoryBarOption(records: CategoryCoverageRecord[], title: string): EChartsCoreOption {
  const t = getChartTheme();
  // Aggregate product totals per category for a stable axis order.
  const totals = new Map<string, number>();
  for (const record of records) {
    totals.set(record.category, (totals.get(record.category) ?? 0) + Number(record.products || 0));
  }
  const categories = [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([category]) => category);
  const byRetailer = new Map<string, Map<string, number>>();
  for (const record of records) {
    let retailerMap = byRetailer.get(record.retailer);
    if (!retailerMap) {
      retailerMap = new Map();
      byRetailer.set(record.retailer, retailerMap);
    }
    retailerMap.set(record.category, Number(record.products));
  }
  const retailerNames = [...byRetailer.keys()];
  return {
    ...baseChartOption(t),
    title: { text: title, left: 0, textStyle: { color: t.text, fontSize: 14, fontWeight: 600 } },
    legend: { top: 28, type: 'scroll', textStyle: { color: t.text }, itemWidth: 14, itemHeight: 8 },
    grid: { left: 8, right: 16, top: 76, bottom: 8, containLabel: true },
    tooltip: { ...baseChartOption(t).tooltip, trigger: 'axis' },
    xAxis: {
      type: 'value',
      name: 'Products',
      nameTextStyle: { color: t.text },
      axisLabel: { color: t.text },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: t.splitLine } }
    },
    yAxis: {
      type: 'category',
      name: 'Category',
      nameTextStyle: { color: t.text },
      data: categories,
      axisLabel: { color: t.text, width: 150, overflow: 'truncate' },
      axisLine: { lineStyle: { color: t.axisLine } },
      axisTick: { show: false }
    },
    series: retailerNames.map((name, index) => ({
      name,
      type: 'bar' as const,
      data: categories.map((category) => byRetailer.get(name)?.get(category) ?? null),
      barMaxWidth: 22,
      itemStyle: { color: t.palette[index % t.palette.length] }
    }))
  };
}

export interface MonthlyAveragePoint {
  month: string; // YYYY-MM
  avg: number;
}

/** Monthly average price chart: months on the X axis, price (TRY) on the Y axis. */
export function monthlyAverageOption(points: MonthlyAveragePoint[], title: string): EChartsCoreOption {
  const t = getChartTheme();
  return {
    ...baseChartOption(t),
    title: { text: title, left: 0, textStyle: { color: t.text, fontSize: 14, fontWeight: 600 } },
    tooltip: { ...baseChartOption(t).tooltip, trigger: 'axis' },
    xAxis: {
      type: 'category',
      name: 'Month',
      nameLocation: 'middle',
      nameGap: 30,
      data: points.map((p) => p.month),
      axisLabel: { color: t.text },
      axisLine: { lineStyle: { color: t.axisLine } },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      name: 'Price (TRY)',
      nameTextStyle: { color: t.text },
      axisLabel: { color: t.text },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: t.splitLine } }
    },
    series: [
      {
        name: 'monthly average',
        type: 'line',
        data: points.map((p) => p.avg),
        showSymbol: true,
        symbolSize: 7,
        connectNulls: true,
        lineStyle: { width: 2.5, color: t.palette[1] },
        itemStyle: { color: t.palette[1] },
        areaStyle: { color: t.palette[1], opacity: 0.06 }
      }
    ]
  };
}
