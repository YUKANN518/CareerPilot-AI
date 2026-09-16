import type { Config } from "tailwindcss"

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "1rem",
      screens: {
        "2xl": "1280px",
      },
    },
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "system-ui",
          "-apple-system",
          '"Segoe UI"',
          "sans-serif",
        ],
      },
      fontSize: {
        caption: ["var(--font-size-caption)", { lineHeight: "var(--line-height-caption)" }],
        xs: ["var(--font-size-support)", { lineHeight: "var(--line-height-support)" }],
        sm: ["var(--font-size-card)", { lineHeight: "var(--line-height-card)" }],
        base: ["var(--font-size-body)", { lineHeight: "var(--line-height-body)" }],
        lg: ["var(--font-size-section)", { lineHeight: "var(--line-height-section)" }],
        "2xl": ["var(--font-size-page)", { lineHeight: "var(--line-height-page)" }],
        "3xl": ["var(--font-size-metric)", { lineHeight: "var(--line-height-metric)" }],
      },
      spacing: {
        4.5: "1.125rem",
      },
      colors: {
        background: "hsl(var(--color-background) / <alpha-value>)",
        surface: "hsl(var(--color-surface) / <alpha-value>)",
        muted: "hsl(var(--color-surface-muted) / <alpha-value>)",
        border: "hsl(var(--color-border) / <alpha-value>)",
        foreground: "hsl(var(--color-text) / <alpha-value>)",
        "muted-foreground": "hsl(var(--color-text-muted) / <alpha-value>)",
        primary: "hsl(var(--color-primary) / <alpha-value>)",
        "primary-hover": "hsl(var(--color-primary-hover) / <alpha-value>)",
        "primary-soft": "hsl(var(--color-primary-soft) / <alpha-value>)",
        info: "hsl(var(--color-info) / <alpha-value>)",
        "info-soft": "hsl(var(--color-info-soft) / <alpha-value>)",
        success: "hsl(var(--color-success) / <alpha-value>)",
        "success-soft": "hsl(var(--color-success-soft) / <alpha-value>)",
        warning: "hsl(var(--color-warning) / <alpha-value>)",
        "warning-soft": "hsl(var(--color-warning-soft) / <alpha-value>)",
        danger: "hsl(var(--color-danger) / <alpha-value>)",
        "danger-soft": "hsl(var(--color-danger-soft) / <alpha-value>)",
        purple: "hsl(var(--color-purple) / <alpha-value>)",
        "purple-soft": "hsl(var(--color-purple-soft) / <alpha-value>)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
      transitionDuration: {
        fast: "var(--motion-fast)",
        normal: "var(--motion-normal)",
        slow: "var(--motion-slow)",
      },
      gridTemplateColumns: {
        shell: "14.5rem minmax(0, 1fr)",
        auth: "minmax(0, 0.92fr) minmax(0, 1.08fr)",
        "resume-review": "minmax(20rem, 2fr) minmax(30rem, 3fr)",
      },
      width: {
        sidebar: "14.5rem",
      },
      maxWidth: {
        content: "80rem",
        auth: "32rem",
      },
      minWidth: {
        table: "56rem",
      },
    },
  },
  plugins: [],
} satisfies Config
