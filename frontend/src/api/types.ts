export interface ApiResponse<T> {
  success: true
  data: T
  message: string
}

export interface ApiErrorBody {
  success: false
  error: {
    code: string
    message: string
    details?: ApiValidationDetail[] | unknown
  }
}

export interface ApiValidationDetail {
  field: string
  message: string
  type: string
}
