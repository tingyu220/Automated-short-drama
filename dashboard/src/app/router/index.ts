import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router"

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "workspace",
    component: () => import("@/pages/workspace/index.vue"),
    meta: { title: "工作台" }
  },
  {
    path: "/tasks",
    name: "tasks",
    component: () => import("@/pages/tasks/index.vue"),
    meta: { title: "今日任务" }
  },
  {
    path: "/queue",
    name: "queue",
    component: () => import("@/pages/queue/index.vue"),
    meta: { title: "自动化队列" }
  },
  {
    path: "/plans",
    name: "plans",
    component: () => import("@/pages/plans/index.vue"),
    meta: { title: "计划管理" }
  },
  {
    path: "/rules",
    name: "rules",
    component: () => import("@/pages/rules/index.vue"),
    meta: { title: "规则与配置" }
  },
  {
    path: "/exceptions",
    name: "exceptions",
    component: () => import("@/pages/exceptions/index.vue"),
    meta: { title: "异常中心" }
  },
  {
    path: "/records",
    name: "records",
    component: () => import("@/pages/records/index.vue"),
    meta: { title: "系统记录" }
  }
]

export const router = createRouter({
  history: createWebHistory(),
  routes
})
