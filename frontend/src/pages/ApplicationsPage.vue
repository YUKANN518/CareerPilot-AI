<script setup lang="ts">
import {
  BriefcaseBusiness,
  CalendarClock,
  ExternalLink,
  GripVertical,
  MapPin,
  Pencil,
  Trash2,
} from "@lucide/vue"
import { computed, onMounted, ref } from "vue"

import { getApiErrorMessage } from "@/api/auth"
import { applicationService } from "@/api/applications"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { FormField } from "@/components/ui/form-field"
import { StatusBadge } from "@/components/ui/status-badge"
import type { Application, ApplicationBoard, ApplicationStatus } from "@/types/application"

interface BoardColumn {
  status: ApplicationStatus
  label: string
  tone: "neutral" | "primary" | "success" | "warning" | "danger"
}

const columns: BoardColumn[] = [
  { status: "SAVED", label: "收藏", tone: "neutral" },
  { status: "APPLIED", label: "已投递", tone: "primary" },
  { status: "INTERVIEW", label: "面试中", tone: "warning" },
  { status: "OFFER", label: "已获 Offer", tone: "success" },
  { status: "REJECTED", label: "未通过", tone: "danger" },
]

const board = ref<ApplicationBoard | null>(null)
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const actionMessage = ref<string | null>(null)
const actionError = ref<string | null>(null)
const draggingId = ref<number | null>(null)
const updatingId = ref<number | null>(null)
const selected = ref<Application | null>(null)
const detailOpen = ref(false)
const editNotes = ref("")
const editNextAction = ref("")
const saving = ref(false)
const changingStatus = ref(false)
const selectedStatus = ref<ApplicationStatus>("SAVED")

const applications = computed(() =>
  board.value ? columns.flatMap((column) => board.value?.columns[column.status] ?? []) : [],
)

function formatDate(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
        new Date(value),
      )
    : "未设置"
}

function toDateTimeLocal(value: string | null): string {
  if (!value) return ""
  const date = new Date(value)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    board.value = await applicationService.board()
  } catch (error) {
    board.value = null
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

function openDetail(application: Application): void {
  selected.value = application
  selectedStatus.value = application.status
  editNotes.value = application.notes ?? ""
  editNextAction.value = toDateTimeLocal(application.next_action_at)
  detailOpen.value = true
}

async function saveStatus(): Promise<void> {
  if (!selected.value || changingStatus.value || selectedStatus.value === selected.value.status) {
    return
  }
  changingStatus.value = true
  actionError.value = null
  try {
    const updated = await applicationService.updateStatus(selected.value.id, {
      status: selectedStatus.value,
    })
    selected.value = updated
    actionMessage.value = "投递状态已更新，并已保存到状态历史。"
    await load()
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    changingStatus.value = false
  }
}

async function moveApplication(applicationId: number, target: ApplicationStatus): Promise<void> {
  const application = applications.value.find((item) => item.id === applicationId)
  if (!application || application.status === target || updatingId.value !== null) return
  updatingId.value = applicationId
  actionError.value = null
  actionMessage.value = null
  try {
    await applicationService.updateStatus(applicationId, { status: target })
    actionMessage.value = "投递状态已更新，并已保存到状态历史。"
    await load()
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    updatingId.value = null
    draggingId.value = null
  }
}

async function saveDetail(): Promise<void> {
  if (!selected.value || saving.value) return
  saving.value = true
  actionError.value = null
  try {
    await applicationService.update(selected.value.id, {
      notes: editNotes.value.trim() || null,
      next_action_at: editNextAction.value ? new Date(editNextAction.value).toISOString() : null,
    })
    actionMessage.value = "投递备注与下一步已保存。"
    detailOpen.value = false
    await load()
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    saving.value = false
  }
}

async function removeApplication(): Promise<void> {
  if (!selected.value || saving.value) return
  saving.value = true
  try {
    await applicationService.delete(selected.value.id)
    actionMessage.value = "投递记录已删除。"
    detailOpen.value = false
    await load()
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <PageHeader
      eyebrow="求职进度"
      title="求职进度"
      description="拖动岗位卡片更新状态；每次变化都会同步到后端并保留状态历史。"
    />

    <p
      v-if="actionMessage"
      class="rounded-md border border-success/20 bg-success-soft p-3 text-sm text-success"
      role="status"
    >
      {{ actionMessage }}
    </p>
    <ErrorState
      v-if="actionError"
      compact
      title="操作未完成"
      :message="actionError"
    />

    <LoadingState
      v-if="loading"
      label="正在加载投递看板"
      :rows="6"
    />
    <ErrorState
      v-else-if="errorMessage"
      :message="errorMessage"
      @retry="load"
    />
    <EmptyState
      v-else-if="applications.length === 0"
      title="还没有投递记录"
      description="从岗位详情页收藏感兴趣的岗位，然后在这里推进求职进度。"
    >
      <RouterLink :to="{ name: 'jobs' }">
        <Button>浏览岗位</Button>
      </RouterLink>
    </EmptyState>
    <div
      v-else
      class="overflow-x-auto pb-3"
    >
      <div class="flex min-w-max items-start gap-4">
        <section
          v-for="column in columns"
          :key="column.status"
          class="w-72 shrink-0 rounded-lg border bg-muted/35 p-3"
          :data-testid="`application-column-${column.status}`"
          @dragover.prevent
          @drop="draggingId !== null && moveApplication(draggingId, column.status)"
        >
          <header class="flex items-center justify-between gap-3 px-1 pb-3">
            <StatusBadge :tone="column.tone">
              {{ column.label }}
            </StatusBadge>
            <span class="text-xs text-muted-foreground">{{ board?.counts[column.status] ?? 0 }}</span>
          </header>
          <div class="min-h-24 space-y-3 rounded-md">
            <article
              v-for="application in board?.columns[column.status] ?? []"
              :key="application.id"
              draggable="true"
              class="cursor-grab rounded-md border bg-surface p-4 shadow-sm transition-shadow hover:shadow-md active:cursor-grabbing"
              :class="{ 'opacity-50': updatingId === application.id }"
              @dragstart="draggingId = application.id"
              @dragend="draggingId = null"
              @click="openDetail(application)"
            >
              <div class="flex items-start gap-2">
                <GripVertical class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <div class="min-w-0 flex-1">
                  <h2 class="line-clamp-2 text-sm font-semibold">{{ application.job.title }}</h2>
                  <p class="mt-1 text-xs text-muted-foreground">{{ application.job.company }}</p>
                </div>
              </div>
              <p class="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
                <MapPin class="size-3.5" />
                {{ application.job.location || "地点未注明" }}
              </p>
              <p
                v-if="application.next_action_at"
                class="mt-2 flex items-center gap-1.5 text-xs text-warning"
              >
                <CalendarClock class="size-3.5" />
                {{ formatDate(application.next_action_at) }}
              </p>
            </article>
            <p
              v-if="(board?.columns[column.status] ?? []).length === 0"
              class="rounded-md border border-dashed bg-surface/60 p-3 text-center text-xs text-muted-foreground"
            >
              拖到这里
            </p>
          </div>
        </section>
      </div>
    </div>

    <Dialog
      :open="detailOpen"
      title="投递记录"
      description="编辑备注、下一步行动，或查看完整状态历史。"
      size="lg"
      @close="detailOpen = false"
    >
      <div
        v-if="selected"
        class="space-y-5"
      >
        <div class="flex items-start justify-between gap-4 rounded-md border bg-muted/35 p-4">
          <div class="min-w-0">
            <h2 class="font-semibold">{{ selected.job.title }}</h2>
            <p class="mt-1 text-sm text-muted-foreground">{{ selected.job.company }}</p>
          </div>
          <a
            v-if="selected.job.source_url"
            :href="selected.job.source_url"
            target="_blank"
            rel="noopener noreferrer"
          >
            <Button
              size="sm"
              variant="outline"
            >
              <ExternalLink class="mr-2 size-3.5" />
              来源
            </Button>
          </a>
        </div>
        <form
          class="space-y-4"
          @submit.prevent="saveDetail"
        >
          <FormField
            label="当前投递状态"
            for-id="application-status"
          >
            <div class="flex flex-wrap gap-2">
              <select
                id="application-status"
                v-model="selectedStatus"
                class="h-10 min-w-40 rounded-sm border bg-surface px-3 text-sm"
              >
                <option
                  v-for="column in columns"
                  :key="column.status"
                  :value="column.status"
                >
                  {{ column.label }}
                </option>
              </select>
              <Button
                type="button"
                variant="outline"
                :disabled="changingStatus || selectedStatus === selected.status"
                @click="saveStatus"
              >
                {{ changingStatus ? "更新中…" : "更新状态" }}
              </Button>
            </div>
          </FormField>
          <FormField
            label="投递备注"
            for-id="application-notes"
          >
            <textarea
              id="application-notes"
              v-model="editNotes"
              class="min-h-28 w-full rounded-sm border bg-surface p-3 text-sm"
              placeholder="例如：已根据岗位要求调整项目描述"
            />
          </FormField>
          <FormField
            label="下一步行动时间"
            for-id="application-next-action"
          >
            <input
              id="application-next-action"
              v-model="editNextAction"
              type="datetime-local"
              class="h-10 w-full rounded-sm border bg-surface px-3 text-sm"
            >
          </FormField>
          <div class="flex justify-between gap-2 border-t pt-4">
            <Button
              type="button"
              variant="danger"
              :disabled="saving"
              @click="removeApplication"
            >
              <Trash2 class="mr-2 size-4" />
              删除记录
            </Button>
            <Button
              type="submit"
              :disabled="saving"
            >
              <Pencil class="mr-2 size-4" />
              {{ saving ? "保存中…" : "保存" }}
            </Button>
          </div>
        </form>
        <section class="border-t pt-5">
          <h3 class="flex items-center gap-2 text-sm font-semibold">
            <BriefcaseBusiness class="size-4 text-primary" />
            状态历史
          </h3>
          <ol class="mt-4 space-y-3">
            <li
              v-for="item in selected.status_history"
              :key="item.id"
              class="border-l-2 border-primary/25 pl-3 text-sm"
            >
              <p class="font-medium">
                {{ item.from_status || "新建" }} → {{ item.to_status }}
              </p>
              <p
                v-if="item.note"
                class="mt-1 text-muted-foreground"
              >
                {{ item.note }}
              </p>
              <p class="mt-1 text-xs text-muted-foreground">{{ formatDate(item.created_at) }}</p>
            </li>
          </ol>
        </section>
      </div>
    </Dialog>
  </section>
</template>
