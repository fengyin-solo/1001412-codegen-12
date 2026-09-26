<template>
  <section class="page" data-module="patrol-detail">
    <header class="page-head">
      <div>
        <h2>巡查单详情</h2>
        <p class="page-desc">查看单条巡查单并执行既有派发流程；返回分布概览后统计数字与巡查单列表保持一致。</p>
      </div>
      <div class="page-actions">
        <button
          v-for="action in actions"
          :key="action"
          class="btn"
          type="button"
          @click="runAction(action)"
        >
          {{ action }}
        </button>
        <button class="btn ghost" type="button" @click="goBack">返回分布概览</button>
      </div>
    </header>

    <table v-if="entry" class="data-table">
      <tbody>
        <tr v-for="field in detailFields" :key="field">
          <th>{{ field }}</th>
          <td>{{ entry[field] ?? '—' }}</td>
        </tr>
        <tr>
          <th>系统状态</th>
          <td>{{ entry.status }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty-state">巡查单加载中……</p>

    <footer class="page-foot">
      <span v-if="message" class="stat-label">{{ message }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchJson, request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/patrol'
const detailFields = ['巡查单号', '巡查路线', '巡查人员', '巡查日期', '巡查里程', '发现问题数', '巡查时长', '巡查状态']
const actions = ['派发巡查', '提交结果', '作废巡查']

const route = useRoute()
const router = useRouter()
const entry = ref<Row | null>(null)
const message = ref('')
const errorMessage = ref('')

function goBack() {
  void router.push('/patrol/overview')
}

async function reload() {
  errorMessage.value = ''
  try {
    entry.value = await fetchJson<Row>(`${ENDPOINT}/${route.params.id}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查单详情读取失败'
  }
}

async function runAction(action: string) {
  errorMessage.value = ''
  message.value = ''
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!payload.ok) {
      throw new Error(payload.message || '巡查任务动作未生效')
    }
    message.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查任务操作失败'
  }
}

onMounted(reload)
</script>
