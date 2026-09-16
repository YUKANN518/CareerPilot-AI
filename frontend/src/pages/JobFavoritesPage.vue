<script setup lang="ts">
import { ArrowLeft, Building2, Heart, MapPin } from "@lucide/vue"
import { onMounted, ref } from "vue"

import { getApiErrorMessage } from "@/api/auth"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import { jobService } from "@/services/jobs"
import type { Job } from "@/types/job"

const jobs = ref<Job[]>([])
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const busyId = ref<number | null>(null)

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    jobs.value = (await jobService.listFavoriteJobs()).items
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function remove(job: Job): Promise<void> {
  busyId.value = job.id
  try {
    await jobService.setJobFavorite(job.id, false)
    jobs.value = jobs.value.filter((item) => item.id !== job.id)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <PageHeader
      eyebrow="Target jobs"
      title="我的收藏"
      description="收藏记录仅属于当前账号，其他用户无法查看或修改。"
    >
      <template #actions>
        <RouterLink :to="{ name: 'jobs' }">
          <Button variant="outline">
            <ArrowLeft class="mr-2 size-4" />
            返回目标岗位
          </Button>
        </RouterLink>
      </template>
    </PageHeader>

    <LoadingState
      v-if="loading"
      label="正在加载收藏岗位"
      :rows="4"
    />
    <ErrorState
      v-else-if="errorMessage"
      :message="errorMessage"
      @retry="load"
    />
    <EmptyState
      v-else-if="jobs.length === 0"
      title="暂时没有收藏岗位"
      description="在目标岗位中收藏感兴趣的岗位后，会显示在这里。"
    >
      <RouterLink :to="{ name: 'jobs' }">
        <Button>浏览岗位</Button>
      </RouterLink>
    </EmptyState>
    <ul
      v-else
      class="grid gap-4 lg:grid-cols-2"
    >
      <li
        v-for="job in jobs"
        :key="job.id"
        class="rounded-lg border bg-surface p-5 shadow-sm"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <RouterLink
              :to="{ name: 'job-detail', params: { jobId: job.id } }"
              class="font-semibold hover:text-primary"
            >
              {{ job.title }}
            </RouterLink>
            <p class="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Building2 class="size-3.5" />
              {{ job.company }}
            </p>
            <p class="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <MapPin class="size-3.5" />
              {{ job.location || "地点未注明" }}
            </p>
          </div>
          <Button
            size="sm"
            variant="ghost"
            :disabled="busyId === job.id"
            :aria-label="`取消收藏 ${job.title}`"
            @click="remove(job)"
          >
            <Heart class="size-4 fill-danger text-danger" />
          </Button>
        </div>
        <p class="mt-4 line-clamp-2 text-sm leading-6 text-muted-foreground">
          {{ job.description }}
        </p>
        <div class="mt-4 flex flex-wrap gap-1.5">
          <StatusBadge tone="neutral">{{ job.source_name }}</StatusBadge>
          <StatusBadge tone="primary">{{ job.data_completeness }}% 完整</StatusBadge>
        </div>
      </li>
    </ul>
  </section>
</template>
