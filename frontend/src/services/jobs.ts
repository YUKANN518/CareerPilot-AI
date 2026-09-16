import { jobApi, type JobApi } from "@/api/jobs"

export type JobCenterService = JobApi

// Production intentionally binds to the real FastAPI implementation. Tests may
// inject or mock this interface without putting fixed job arrays in Vue pages.
export const jobService: JobCenterService = jobApi
