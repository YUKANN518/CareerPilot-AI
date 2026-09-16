import { createPinia } from "pinia"
import { createApp } from "vue"

import App from "@/App.vue"
import { router } from "@/router"
import { useAuthStore } from "@/stores/auth"
import "@/styles/main.css"

const app = createApp(App)
const pinia = createPinia()

async function bootstrap(): Promise<void> {
  app.use(pinia)
  await useAuthStore(pinia).initialize()
  app.use(router)
  app.mount("#app")
}

void bootstrap()
