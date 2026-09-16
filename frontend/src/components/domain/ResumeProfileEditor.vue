<script setup lang="ts">
import EvidenceFieldEditor from "@/components/domain/EvidenceFieldEditor.vue"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type {
  EducationItem,
  EvidenceField,
  ProjectExperienceItem,
  ResumeProfile,
  StructuredSkill,
  WorkExperienceItem,
} from "@/types/resume"

const profile = defineModel<ResumeProfile>({ required: true })
const emit = defineEmits<{
  "focus-evidence": [field: EvidenceField]
  modified: []
}>()

const basicFields = [
  { key: "full_name", label: "姓名" },
  { key: "email", label: "邮箱" },
  { key: "phone", label: "电话" },
  { key: "location", label: "所在地" },
] as const
const educationFields: { key: keyof EducationItem; label: string; multiline?: boolean }[] = [
  { key: "institution", label: "学校" },
  { key: "degree", label: "学历" },
  { key: "field_of_study", label: "专业" },
  { key: "start_date", label: "开始时间" },
  { key: "end_date", label: "结束时间" },
  { key: "description", label: "教育描述", multiline: true },
]
const workFields: { key: keyof WorkExperienceItem; label: string; multiline?: boolean }[] = [
  { key: "company", label: "公司" },
  { key: "title", label: "职位" },
  { key: "start_date", label: "开始时间" },
  { key: "end_date", label: "结束时间" },
  { key: "description", label: "工作描述", multiline: true },
]
const projectFields: {
  key: keyof ProjectExperienceItem
  label: string
  multiline?: boolean
}[] = [
  { key: "name", label: "项目名称" },
  { key: "role", label: "项目角色" },
  { key: "start_date", label: "开始时间" },
  { key: "end_date", label: "结束时间" },
  { key: "description", label: "项目描述", multiline: true },
]

function emptyField(): EvidenceField {
  return {
    value: "",
    confidence: 0,
    evidence_text: "",
    source_location: {
      source_type: "unknown",
      page_number: null,
      block_index: null,
      paragraph_index: null,
      table_index: null,
      row_index: null,
      label: "manual-entry",
    },
    needs_confirmation: true,
  }
}

function addEducation(): void {
  profile.value.education.push({
    institution: emptyField(),
    degree: emptyField(),
    field_of_study: emptyField(),
    start_date: emptyField(),
    end_date: emptyField(),
    description: emptyField(),
  })
  emit("modified")
}

function addWork(): void {
  profile.value.work_experience.push({
    company: emptyField(),
    title: emptyField(),
    start_date: emptyField(),
    end_date: emptyField(),
    description: emptyField(),
  })
  emit("modified")
}

function addProject(): void {
  profile.value.project_experience.push({
    name: emptyField(),
    role: emptyField(),
    start_date: emptyField(),
    end_date: emptyField(),
    description: emptyField(),
  })
  emit("modified")
}

function addSkill(target: "technical_skills" | "soft_skills"): void {
  const skill: StructuredSkill = {
    ...emptyField(),
    category: null,
    level: null,
  }
  profile.value[target].push(skill)
  emit("modified")
}

function removeEducation(index: number): void {
  profile.value.education.splice(index, 1)
  emit("modified")
}

function removeWork(index: number): void {
  profile.value.work_experience.splice(index, 1)
  emit("modified")
}

function removeProject(index: number): void {
  profile.value.project_experience.splice(index, 1)
  emit("modified")
}

function removeSkill(
  target: "technical_skills" | "soft_skills",
  index: number,
): void {
  profile.value[target].splice(index, 1)
  emit("modified")
}

function addSimple(target: "languages" | "certificates" | "awards"): void {
  profile.value[target].push(emptyField())
  emit("modified")
}

function removeSimple(
  target: "languages" | "certificates" | "awards",
  index: number,
): void {
  profile.value[target].splice(index, 1)
  emit("modified")
}
</script>

<template>
  <div class="space-y-5">
    <section class="space-y-3 rounded-md border bg-background/40 p-4">
      <h2 class="text-sm font-semibold">基本信息</h2>
      <div class="grid gap-3 md:grid-cols-2">
        <EvidenceFieldEditor
          v-for="field in basicFields"
          :key="field.key"
          v-model="profile.basic_info[field.key]"
          :label="field.label"
          @focus-evidence="emit('focus-evidence', $event)"
          @modified="emit('modified')"
        />
      </div>
    </section>

    <section class="space-y-3 rounded-md border bg-background/40 p-4">
      <h2 class="text-sm font-semibold">个人摘要</h2>
      <EvidenceFieldEditor
        v-model="profile.summary"
        label="摘要"
        multiline
        @focus-evidence="emit('focus-evidence', $event)"
        @modified="emit('modified')"
      />
    </section>

    <section class="space-y-3 rounded-md border bg-background/40 p-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold">教育经历</h2>
        <Button
          size="sm"
          variant="outline"
          @click="addEducation"
        >
          增加教育经历
        </Button>
      </div>
      <p
        v-if="profile.education.length === 0"
        class="text-sm text-muted-foreground"
      >
        暂无教育经历。
      </p>
      <div
        v-for="(item, index) in profile.education"
        :key="index"
        class="space-y-3 rounded-md border bg-surface p-4"
      >
        <div class="flex justify-end">
          <Button
            size="sm"
            variant="danger"
            @click="removeEducation(index)"
          >
            删除
          </Button>
        </div>
        <EvidenceFieldEditor
          v-for="field in educationFields"
          :key="field.key"
          v-model="item[field.key]"
          :label="field.label"
          :multiline="field.multiline"
          @focus-evidence="emit('focus-evidence', $event)"
          @modified="emit('modified')"
        />
      </div>
    </section>

    <section class="space-y-3 rounded-md border bg-background/40 p-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold">工作经历</h2>
        <Button
          size="sm"
          variant="outline"
          @click="addWork"
        >
          增加工作经历
        </Button>
      </div>
      <p
        v-if="profile.work_experience.length === 0"
        class="text-sm text-muted-foreground"
      >
        暂无工作经历。
      </p>
      <div
        v-for="(item, index) in profile.work_experience"
        :key="index"
        class="space-y-3 rounded-md border bg-surface p-4"
      >
        <div class="flex justify-end">
          <Button
            size="sm"
            variant="danger"
            @click="removeWork(index)"
          >
            删除
          </Button>
        </div>
        <EvidenceFieldEditor
          v-for="field in workFields"
          :key="field.key"
          v-model="item[field.key]"
          :label="field.label"
          :multiline="field.multiline"
          @focus-evidence="emit('focus-evidence', $event)"
          @modified="emit('modified')"
        />
      </div>
    </section>

    <section class="space-y-3 rounded-md border bg-background/40 p-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold">项目经历</h2>
        <Button
          size="sm"
          variant="outline"
          @click="addProject"
        >
          增加项目经历
        </Button>
      </div>
      <p
        v-if="profile.project_experience.length === 0"
        class="text-sm text-muted-foreground"
      >
        暂无项目经历。
      </p>
      <div
        v-for="(item, index) in profile.project_experience"
        :key="index"
        class="space-y-3 rounded-md border bg-surface p-4"
      >
        <div class="flex justify-end">
          <Button
            size="sm"
            variant="danger"
            @click="removeProject(index)"
          >
            删除
          </Button>
        </div>
        <EvidenceFieldEditor
          v-for="field in projectFields"
          :key="field.key"
          v-model="item[field.key]"
          :label="field.label"
          :multiline="field.multiline"
          @focus-evidence="emit('focus-evidence', $event)"
          @modified="emit('modified')"
        />
      </div>
    </section>

    <section
      v-for="group in [
        { key: 'technical_skills' as const, label: '技术技能' },
        { key: 'soft_skills' as const, label: '软技能' },
      ]"
      :key="group.key"
      class="space-y-3 rounded-md border bg-background/40 p-4"
    >
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold">{{ group.label }}</h2>
        <Button
          size="sm"
          variant="outline"
          @click="addSkill(group.key)"
        >
          增加技能
        </Button>
      </div>
      <p
        v-if="profile[group.key].length === 0"
        class="text-sm text-muted-foreground"
      >
        暂无技能。
      </p>
      <div
        v-for="(skill, index) in profile[group.key]"
        :key="index"
        class="space-y-3 rounded-md border bg-surface p-4"
      >
        <div class="flex justify-end">
          <Button
            size="sm"
            variant="danger"
            @click="removeSkill(group.key, index)"
          >
            删除
          </Button>
        </div>
        <EvidenceFieldEditor
          v-model="profile[group.key][index]"
          label="技能名称"
          @focus-evidence="emit('focus-evidence', $event)"
          @modified="emit('modified')"
        />
        <div class="grid gap-3 md:grid-cols-2">
          <label class="space-y-2 text-sm font-medium">
            分类
            <Input
              :model-value="skill.category ?? ''"
              @update:model-value="
                skill.category = $event || null;
                emit('modified')
              "
            />
          </label>
          <label class="space-y-2 text-sm font-medium">
            水平
            <Input
              :model-value="skill.level ?? ''"
              @update:model-value="
                skill.level = $event || null;
                emit('modified')
              "
            />
          </label>
        </div>
      </div>
    </section>

    <section
      v-for="group in [
        { key: 'languages' as const, label: '语言能力' },
        { key: 'certificates' as const, label: '证书' },
        { key: 'awards' as const, label: '奖项' },
      ]"
      :key="group.key"
      class="space-y-3 rounded-md border bg-background/40 p-4"
    >
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold">{{ group.label }}</h2>
        <Button
          size="sm"
          variant="outline"
          @click="addSimple(group.key)"
        >
          增加
        </Button>
      </div>
      <p
        v-if="profile[group.key].length === 0"
        class="text-sm text-muted-foreground"
      >
        暂无记录。
      </p>
      <div
        v-for="(field, index) in profile[group.key]"
        :key="index"
        class="space-y-3 rounded-md border bg-surface p-4"
      >
        <div class="flex justify-end">
          <Button
            size="sm"
            variant="danger"
            @click="removeSimple(group.key, index)"
          >
            删除
          </Button>
        </div>
        <EvidenceFieldEditor
          v-model="profile[group.key][index]"
          :label="group.label"
          @focus-evidence="emit('focus-evidence', $event)"
          @modified="emit('modified')"
        />
      </div>
    </section>
  </div>
</template>
