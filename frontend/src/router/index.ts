import { createRouter, createWebHistory } from 'vue-router'
import ConsoleView from '../views/ConsoleView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'console',
      component: ConsoleView
    }
  ]
})

export default router
