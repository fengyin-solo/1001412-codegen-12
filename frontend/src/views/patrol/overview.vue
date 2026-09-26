<template>
  <section class="page" data-module="patrol-overview">
    <header class="page-head">
      <div>
        <h2>巡查问题分布概览</h2>
        <p class="page-desc">
          按巡查路线与巡查人员统计发现问题数、已提交与作废巡查单、平均巡查里程；同一巡查单只统计一次，作废单不计入问题数，问题数为零的单子不进异常统计。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goPatrolList">返回巡查任务</button>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>开始日期</span>
        <input v-model="start" type="date" />
      </label>
      <label class="filter-item">
        <span>结束日期</span>
        <input v-model="end" type="date" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetRange">重置范围</button>
    </form>

    <div class="stat-row">
      <article v-for="item in summaryCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <h3 class="group-title">按巡查路线</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>巡查路线</th>
          <th v-for="column in groupColumns" :key="column.label">{{ column.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in byRoute" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.problem_count }}</td>
          <td>{{ row.abnormal_orders }}</td>
          <td>{{ row.submitted }}</td>
          <td>{{ row.voided }}</td>
          <td>{{ formatMileage(row.avg_mileage) }}</td>
        </tr>
        <tr v-if="!byRoute.length">
          <td :colspan="groupColumns.length + 1" class="empty-state">当前日期范围内没有巡查记录</td>
        </tr>
      </tbody>
    </table>

    <h3 class="group-title">按巡查人员</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>巡查人员</th>
          <th v-for="column in groupColumns" :key="column.label">{{ column.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in byPerson" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.problem_count }}</td>
          <td>{{ row.abnormal_orders }}</td>
          <td>{{ row.submitted }}</td>
          <td>{{ row.voided }}</td>
          <td>{{ formatMileage(row.avg_mileage) }}</td>
        </tr>
        <tr v-if="!byPerson.length">
          <td :colspan="groupColumns.length + 1" class="empty-state">当前日期范围内没有巡查记录</td>
        </tr>
      </tbody>
    </table>

    <h3 class="group-title">巡查单列表</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in orderColumns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in orders" :key="String(row.id)">
          <td v-for="column in orderColumns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
          </td>
        </tr>
        <tr v-if="!orders.length">
          <td :colspan="orderColumns.length + 1" class="empty-state">当前日期范围内没有巡查单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ orders.length }} 条巡查单计入统计</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { fetchJson } from '@/api/client'

type Row = Record<string, string | number | null>

type GroupRow = {
  name: string
  problem_count: number
  abnormal_orders: number
  submitted: number
  voided: number
  order_count: number
  avg_mileage: number | null
}

type StatsPayload = {
  range: { start: string | null; end: string | null }
  totals: Omit<GroupRow, 'name'>
  by_route: GroupRow[]
  by_person: GroupRow[]
  orders: Row[]
}

const ENDPOINT = '/api/patrol/stats'
const groupColumns = [
  { label: '发现问题数' },
  { label: '异常巡查单' },
  { label: '已提交巡查单' },
  { label: '作废巡查单' },
  { label: '平均巡查里程' },
]
const orderColumns = ['巡查单号', '巡查路线', '巡查人员', '巡查日期', '巡查里程', '发现问题数', '巡查状态']

const router = useRouter()
const start = ref('')
const end = ref('')
const totals = ref<StatsPayload['totals'] | null>(null)
const byRoute = ref<GroupRow[]>([])
const byPerson = ref<GroupRow[]>([])
const orders = ref<Row[]>([])
const errorMessage = ref('')

const summaryCards = computed(() => [
  { label: '发现问题数', value: totals.value?.problem_count ?? 0 },
  { label: '异常巡查单', value: totals.value?.abnormal_orders ?? 0 },
  { label: '已提交巡查单', value: totals.value?.submitted ?? 0 },
  { label: '作废巡查单', value: totals.value?.voided ?? 0 },
  { label: '平均巡查里程', value: formatMileage(totals.value?.avg_mileage ?? null) },
])

function formatMileage(value: number | null): string {
  return value === null || value === undefined ? '—' : `${value} km`
}

function defaultRange() {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  start.value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-01`
  end.value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

function resetRange() {
  defaultRange()
  void reload()
}

function goPatrolList() {
  void router.push('/patrol')
}

function openDetail(row: Row) {
  void router.push(`/patrol/${row.id}`)
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (start.value) query.set('start', start.value)
  if (end.value) query.set('end', end.value)
  try {
    const payload = await fetchJson<StatsPayload>(`${ENDPOINT}?${query.toString()}`)
    totals.value = payload.totals
    byRoute.value = payload.by_route ?? []
    byPerson.value = payload.by_person ?? []
    orders.value = payload.orders ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查问题分布读取失败'
  }
}

onMounted(() => {
  defaultRange()
  void reload()
})
</script>

<style scoped>
.group-title {
  font-size: 14px;
  margin: 16px 0 8px;
}
</style>
