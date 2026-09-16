<script setup lang="ts">
import AppHeader from "@/components/layout/AppHeader.vue"
import AdminSidebar from "@/components/layout/AdminSidebar.vue"
</script>

<template>
  <div class="flex min-h-screen bg-background">
    <AdminSidebar />
    <div class="min-w-0 flex-1">
      <AppHeader />
      <main class="mx-auto w-full max-w-content p-4 md:p-6 lg:p-8">
        <RouterView />
      </main>
    </div>
  </div>
</template>
