import { createRouter, createWebHistory } from "vue-router"

import AuthLayout from "@/layouts/AuthLayout.vue"
import { hasRequiredRole } from "@/router/permissions"
import { useAuthStore } from "@/stores/auth"

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/auth",
      component: AuthLayout,
      meta: { guestOnly: true },
      children: [
        {
          path: "login",
          name: "login",
          component: () => import("@/pages/LoginPage.vue"),
        },
        {
          path: "register",
          name: "register",
          component: () => import("@/pages/RegisterPage.vue"),
        },
      ],
    },
    {
      path: "/",
      component: () => import("@/layouts/AppLayout.vue"),
      meta: { requiresAuth: true },
      children: [
        { path: "", redirect: { name: "dashboard" } },
        {
          path: "dashboard",
          name: "dashboard",
          component: () => import("@/pages/DashboardPage.vue"),
        },
        {
          path: "resumes",
          name: "resumes",
          component: () => import("@/pages/ResumesPage.vue"),
        },
        {
          path: "resumes/upload",
          name: "resume-upload",
          component: () => import("@/pages/ResumeUploadPage.vue"),
        },
        {
          path: "resumes/:resumeId",
          name: "resume-status",
          component: () => import("@/pages/ResumeStatusPage.vue"),
        },
        {
          path: "resumes/:resumeId/confirm",
          name: "resume-confirm",
          component: () => import("@/pages/ResumeConfirmPage.vue"),
        },
        {
          path: "resume-versions/:versionId",
          name: "resume-version",
          component: () => import("@/pages/ResumeVersionPage.vue"),
        },
        {
          path: "jobs",
          name: "jobs",
          component: () => import("@/pages/JobsPage.vue"),
        },
        {
          path: "jobs/favorites",
          name: "job-favorites",
          component: () => import("@/pages/JobFavoritesPage.vue"),
        },
        {
          path: "jobs/:jobId",
          name: "job-detail",
          component: () => import("@/pages/JobDetailPage.vue"),
        },
        {
          path: "applications",
          name: "applications",
          component: () => import("@/pages/ApplicationsPage.vue"),
        },
        {
          path: "matches",
          name: "matches",
          component: () => import("@/pages/MatchesPage.vue"),
        },
        {
          path: "matches/new",
          name: "match-new",
          component: () => import("@/pages/MatchNewPage.vue"),
        },
        {
          path: "match-runs/:runId/processing",
          name: "match-processing",
          component: () => import("@/pages/MatchProcessingPage.vue"),
        },
        {
          path: "matches/:matchId",
          name: "match-report",
          component: () => import("@/pages/MatchReportPage.vue"),
        },
        {
          path: "resume-optimizations",
          name: "resume-optimizations",
          component: () => import("@/pages/ResumeOptimizationsPage.vue"),
        },
        {
          path: "resume-optimizations/:optimizationId",
          name: "resume-optimization-detail",
          component: () => import("@/pages/ResumeOptimizationDetailPage.vue"),
        },
        {
          path: "interviews",
          name: "interviews",
          component: () => import("@/pages/InterviewsPage.vue"),
        },
        {
          path: "interviews/:interviewId",
          name: "interview-detail",
          redirect: (to) => ({
            name: "interview-chat",
            params: { interviewId: to.params.interviewId },
          }),
        },
        {
          path: "interviews/:interviewId/chat",
          name: "interview-chat",
          component: () => import("@/pages/InterviewChatPage.vue"),
        },
        {
          path: "interviews/:interviewId/chat/report",
          name: "interview-chat-report",
          component: () => import("@/pages/InterviewChatReportPage.vue"),
        },
        {
          path: "career-assistant",
          name: "career-assistant",
          component: () => import("@/pages/CareerAssistantPage.vue"),
        },
      ],
    },
    {
      path: "/admin",
      component: () => import("@/layouts/AdminLayout.vue"),
      meta: { requiresAuth: true, roles: ["ADMIN"] },
      children: [
        {
          path: "",
          name: "admin-home",
          redirect: { name: "admin-knowledge-documents" },
        },
        {
          path: "knowledge-documents",
          name: "admin-knowledge-documents",
          component: () => import("@/pages/AdminKnowledgeDocumentsPage.vue"),
        },
      ],
    },
    {
      path: "/forbidden",
      name: "forbidden",
      component: () => import("@/pages/ForbiddenPage.vue"),
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/pages/NotFoundPage.vue"),
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  if (!authStore.initialized) {
    await authStore.initialize()
  }
  if (to.meta.guestOnly && authStore.isAuthenticated) {
    return { name: "dashboard" }
  }
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } }
  }
  if (!hasRequiredRole(authStore.user?.role, to.meta.roles)) {
    return { name: "forbidden" }
  }
  return true
})
