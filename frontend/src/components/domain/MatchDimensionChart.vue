<script setup lang="ts">
import { BarChart } from "echarts/charts"
import {
  GridComponent,
  TooltipComponent,
  type TooltipComponentOption,
} from "echarts/components"
import { init, use, type ComposeOption, type ECharts } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import type { BarSeriesOption } from "echarts/charts"
import type { GridComponentOption } from "echarts/components"
import { onBeforeUnmount, onMounted, ref, watch } from "vue"

import type { DimensionScore } from "@/types/matching"
import { dimensionLabels } from "@/utils/matching"

const props = defineProps<{ dimensions: DimensionScore[] }>()
const chartElement = ref<HTMLDivElement | null>(null)
type ChartOption = ComposeOption<
  BarSeriesOption | GridComponentOption | TooltipComponentOption
>

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

let chart: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

function render(): void {
  if (!chartElement.value) return
  chart ??= init(chartElement.value)
  const rootStyle = getComputedStyle(document.documentElement)
  const tokenColor = (name: string) =>
    `hsl(${rootStyle.getPropertyValue(name).trim()})`
  const option: ChartOption = {
    animationDuration: 200,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (items: unknown) => {
        const item = Array.isArray(items) ? items[0] : null
        if (!item || typeof item !== "object" || !("dataIndex" in item)) return ""
        const dimension = props.dimensions[Number(item.dataIndex)]
        return dimension
          ? `${dimensionLabels[dimension.code] ?? dimension.label}<br/>维度分 ${dimension.score}<br/>权重 ${dimension.weight}%<br/>贡献 ${dimension.weighted_score}`
          : ""
      },
    },
    grid: { left: 8, right: 20, top: 8, bottom: 8, containLabel: true },
    xAxis: {
      type: "value",
      min: 0,
      max: 100,
      splitLine: { lineStyle: { color: tokenColor("--color-border") } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: props.dimensions.map((item) => dimensionLabels[item.code] ?? item.label),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: {
        width: 130,
        overflow: "truncate",
        color: tokenColor("--color-text-muted"),
      },
    },
    series: [
      {
        type: "bar",
        data: props.dimensions.map((item) => item.score),
        barWidth: 12,
        itemStyle: { color: tokenColor("--color-primary"), borderRadius: 6 },
        label: { show: true, position: "right", formatter: "{c}" },
      },
    ],
  }
  chart.setOption(option)
}

onMounted(() => {
  render()
  if (chartElement.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartElement.value)
  }
})
watch(() => props.dimensions, render, { deep: true })
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div
    ref="chartElement"
    class="h-72 w-full"
    role="img"
    aria-label="六维匹配评分图"
    data-testid="dimension-chart"
  />
</template>
