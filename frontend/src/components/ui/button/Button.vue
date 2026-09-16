<script setup lang="ts">
import { type VariantProps, cva } from "class-variance-authority"
import { computed, useAttrs } from "vue"

import { cn } from "@/utils/cn"

defineOptions({ inheritAttrs: false })

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-sm text-sm font-medium transition-colors duration-fast disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-white hover:bg-primary-hover",
        outline: "border bg-surface hover:bg-muted",
        ghost: "hover:bg-muted",
        danger: "bg-danger text-white hover:opacity-90",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 px-3",
        lg: "h-11 px-6",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)

type ButtonVariants = VariantProps<typeof buttonVariants>

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariants["variant"]
    size?: ButtonVariants["size"]
    type?: "button" | "submit" | "reset"
    disabled?: boolean
  }>(),
  {
    variant: "default",
    size: "default",
    type: "button",
    disabled: false,
  },
)

const attrs = useAttrs()
const classes = computed(() => cn(buttonVariants(props), attrs.class as string))
</script>

<template>
  <button
    v-bind="attrs"
    :class="classes"
    :type="type"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>
