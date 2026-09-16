<script setup lang="ts">
import { computed, useAttrs } from "vue"

import { cn } from "@/utils/cn"

defineOptions({ inheritAttrs: false })

const attrs = useAttrs()
const classes = computed(() =>
  cn("rounded-md border bg-surface p-6 shadow-sm", attrs.class as string),
)
</script>

<template>
  <section
    v-bind="attrs"
    :class="classes"
  >
    <slot />
  </section>
</template>
