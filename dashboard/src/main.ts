import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import { router } from './app/router'
import './shared/styles/design-tokens.css'
import './shared/styles/theme.css'

const app = createApp(App)
app.config.errorHandler = (err, _instance, info) => {
  console.error('[App Error]', err, info)
}
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')
