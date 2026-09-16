type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue }

const sensitivePattern =
  /authorization|cookie|api[-_]?key|token|secret|credential|fernet|password/i
const largePayloadPattern = /response|body|payload|raw[_-]?data|html|content/i

export function redactText(value: string): string {
  return value
    .replace(/(bearer\s+)[a-z0-9._~+/=-]+/gi, "$1[REDACTED]")
    .replace(
      /((?:authorization|cookie|api[-_]?key|token|secret|credential|password)\s*[:=]\s*)[^\s,;]+/gi,
      "$1[REDACTED]",
    )
}

export function redactJson(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(redactJson)
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        sensitivePattern.test(key) ? "[REDACTED]" : redactJson(item),
      ]),
    )
  }
  return typeof value === "string" ? redactText(value) : value
}

export function sanitizeLogJson(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.slice(0, 20).map(sanitizeLogJson)
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value)
        .slice(0, 30)
        .map(([key, item]) => [
          key,
          sensitivePattern.test(key)
            ? "[REDACTED]"
            : largePayloadPattern.test(key)
              ? "[OMITTED]"
              : sanitizeLogJson(item),
        ]),
    )
  }
  if (typeof value === "string") return redactText(value).slice(0, 500)
  return value
}
