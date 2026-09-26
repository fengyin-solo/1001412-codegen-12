<template>
  <section class="page" data-module="patrol-distribution">
    <header class="page-head">
      <div>
        <h2>巡查问题分布概览</h2>
        <p class="page-desc">按巡查路线与巡查人员汇总发现问题数、已提交与作废巡查单、平均巡查里程；同一巡查单只统计一次，作废单不计入问题数。</p>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>起始日期</span>
        <input v-model="startDate" type="date" />
      </label>
      <label class="filter-item">
        <span>截止日期</span>
        <input v-model="endDate" type="date" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetRange">全部日期</button>
    </form>

    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in groupColumns" :key="column">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in groups" :key="`${row.巡查路线}-${row.巡查人员}`">
          <td v-for="column in groupColumns" :key="column">{{ row[column] }}</td>
        </tr>
        <tr v-if="!groups.length">
          <td :colspan="groupColumns.length" class="empty-state">该日期范围内没有巡查记录，可调整日期再查</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">范围内巡查单（同一单号只列一次，共 {{ orders.length }} 条）</h3>
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
          <td>
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
          </td>
        </tr>
        <tr v-if="!orders.length">
          <td :colspan="orderColumns.length + 1" class="empty-state">该日期范围内没有巡查单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>统计口径：作废巡查单不计入发现问题数，问题数为零的巡查单不计入异常</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <header class="modal-head">
          <h3>巡查单详情 · {{ detail.巡查单号 }}</h3>
          <button class="btn ghost" type="button" @click="closeDetail">返回概览</button>
        </header>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] ?? '—' }}</dd>
          </template>
        </dl>
        <div class="modal-actions">
          <button
            v-for="action in actions"
            :key="action"
            class="btn"
            type="button"
            @click="runAction(action)"
          >
            {{ action }}
          </button>
        </div>
        <p v-if="detailMessage" :class="detailOk ? 'ok-text' : 'error-text'">{{ detailMessage }}</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type OrderRow = Record<string, string | number | null> & { id: number }
type GroupRow = Record<string, string | number>
type Card = { label: string; value: number }
type DistributionPayload = { cards: Card[]; groups: GroupRow[]; orders: OrderRow[] }
type ActionResult = { ok: boolean; message: string; entry: OrderRow | null }

const ENDPOINT = '/api/patrol'
const groupColumns = ["巡查路线", "巡查人员", "发现问题数", "异常巡查单", "已提交巡查单", "作废巡查单", "平均巡查里程"]
const orderColumns = ["巡查单号", "巡查路线", "巡查人员", "巡查日期", "巡查里程", "发现问题数", "巡查时长", "巡查状态"]
const detailFields = orderColumns
const actions = ["派发巡查", "提交结果", "作废巡查"]

const cards = ref<Card[]>([])
const groups = ref<GroupRow[]>([])
const orders = ref<OrderRow[]>([])
const startDate = ref('')
const endDate = ref('')
const errorMessage = ref('')
const detail = ref<OrderRow | null>(null)
const detailMessage = ref('')
const detailOk = ref(true)

function resetRange() {
  startDate.value = ''
  endDate.value = ''
  void reload()
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (startDate.value) query.set('start', startDate.value)
  if (endDate.value) query.set('end', endDate.value)
  try {
    const payload = await fetchJson<DistributionPayload>(`${ENDPOINT}/distribution?${query}`)
    cards.value = payload.cards ?? []
    groups.value = payload.groups ?? []
    orders.value = payload.orders ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分布概览读取失败'
  }
}

async function openDetail(row: OrderRow) {
  detailMessage.value = ''
  try {
    detail.value = await fetchJson<OrderRow>(`${ENDPOINT}/${row.id}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查单详情读取失败'
  }
}

async function runAction(action: string) {
  if (!detail.value) return
  detailMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${detail.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = (await response.json()) as ActionResult
    detailOk.value = response.ok && result.ok
    detailMessage.value = result.message || (result.ok ? '操作已生效' : '操作未生效')
    if (result.ok && result.entry) {
      detail.value = result.entry
    }
    await reload()
  } catch (error) {
    detailOk.value = false
    detailMessage.value = error instanceof Error ? error.message : '巡查任务操作失败'
  }
}

async function closeDetail() {
  detail.value = null
  await reload()
}

onMounted(reload)
</script>

<style scoped>
.section-title { font-size: 14px; margin: 16px 0 8px; }
.modal-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); display: flex; align-items: center; justify-content: center; z-index: 10; }
.modal-card { background: #fff; border-radius: 8px; padding: 16px 20px; width: 520px; max-width: 90vw; }
.modal-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.modal-head h3 { margin: 0; font-size: 15px; }
.detail-grid { display: grid; grid-template-columns: 96px 1fr; row-gap: 6px; font-size: 13px; margin: 12px 0; }
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; }
.modal-actions { display: flex; gap: 8px; }
.ok-text { color: #067647; font-size: 13px; }
.error-text { font-size: 13px; }
</style>
