<script setup lang="ts">
import { ref } from "vue"

import AppHeader from "@/components/layout/AppHeader.vue"
import AppSidebar from "@/components/layout/AppSidebar.vue"

const sidebarCollapsed = ref(false)
</script>

<template>
  <div class="flex min-h-screen bg-background">
    <AppSidebar v-model:collapsed="sidebarCollapsed" />
    <div class="min-w-0 flex-1">
      <AppHeader />
      <main class="mx-auto w-full max-w-content p-4 md:p-6 lg:p-8">
        <RouterView />
      </main>
    </div>
  </div>
</template>
