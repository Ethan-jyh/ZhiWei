<template>
  <div class="intervention-comparison bg-white rounded-lg shadow-sm border border-gray-200 p-4">
    <!-- 头部标题栏 -->
    <div class="flex items-center justify-between border-b border-gray-100 pb-3 mb-4">
      <div>
        <h3 class="text-base font-semibold text-gray-900">{{ $t('intervention.comparison.title') }}</h3>
        <p class="text-xs text-gray-500 mt-0.5">{{ $t('intervention.comparison.subtitle') }}</p>
      </div>
      <div v-if="state.experiment" class="flex items-center space-x-2">
        <button
          type="button"
          @click="handleRefreshComparison"
          :disabled="state.busy"
          class="text-xs px-2.5 py-1 bg-gray-50 text-gray-700 hover:bg-gray-100 rounded border border-gray-200 disabled:opacity-50"
        >
          {{ $t('intervention.comparison.loadComparison') }}
        </button>
      </div>
    </div>

    <!-- 创建实验表单（未创建实验时显示） -->
    <div v-if="!state.experiment" class="bg-gray-50 rounded-md p-4 mb-4 border border-gray-100">
      <h4 class="text-xs font-semibold text-gray-800 mb-3">{{ $t('intervention.comparison.createTitle') }}</h4>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('intervention.comparison.earlyRound') }}</label>
          <input
            v-model.number="form.early_round"
            type="number"
            min="1"
            class="w-full text-xs rounded border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('intervention.comparison.lateRound') }}</label>
          <input
            v-model.number="form.late_round"
            type="number"
            min="2"
            class="w-full text-xs rounded border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>
      </div>

      <!-- 预设声明内容 -->
      <div class="mb-3">
        <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('intervention.content') }}</label>
        <textarea
          v-model="form.content"
          rows="2"
          placeholder="请输入用于早回应与晚回应对比的统一官方声明内容..."
          class="w-full text-xs rounded border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
        ></textarea>
      </div>

      <div class="flex justify-end">
        <button
          type="button"
          @click="handleCreateExperiment"
          :disabled="state.busy || !form.content"
          class="px-3.5 py-1.5 bg-indigo-600 text-white text-xs font-medium rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          {{ state.busy ? $t('intervention.comparison.creating') : $t('intervention.comparison.createBtn') }}
        </button>
      </div>
    </div>

    <!-- 实验已创建：三组方案状态卡片 -->
    <div v-else class="space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div
          v-for="variant in state.experiment.variants"
          :key="variant.variant_id"
          class="bg-gray-50 rounded p-3 border border-gray-100 flex flex-col justify-between"
        >
          <div>
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold text-gray-900">{{ variant.name }}</span>
              <span
                class="text-[10px] px-1.5 py-0.5 rounded font-mono font-medium"
                :class="getVariantBadgeClass(variant.variant_id)"
              >
                {{ variant.variant_id }}
              </span>
            </div>

            <!-- 声明时点 -->
            <div class="text-xs text-gray-500 mt-2">
              <template v-if="variant.variant_id === 'control'">
                自然发展 (无声明注入)
              </template>
              <template v-else-if="variant.statements && variant.statements.length > 0">
                计划在第 {{ variant.statements[0].trigger.round }} 轮发布
              </template>
            </div>

            <!-- 运行状态与结果 -->
            <div class="mt-3 text-xs space-y-1">
              <div class="flex justify-between text-gray-600">
                <span>运行状态:</span>
                <span class="font-medium">{{ getRunStatusLabel(variant.variant_id) }}</span>
              </div>
              <div class="flex justify-between text-gray-600">
                <span>峰值热度:</span>
                <span class="font-medium">{{ getVariantMetric(variant.variant_id, 'peak_heat') }}</span>
              </div>
              <div class="flex justify-between text-gray-600">
                <span>回落耗时:</span>
                <span class="font-medium">{{ getVariantMetric(variant.variant_id, 'cooling_duration') }}</span>
              </div>
            </div>
          </div>

          <!-- 启动运行按钮 -->
          <div class="mt-4 pt-2 border-t border-gray-200 flex justify-end">
            <button
              v-if="!isRunStarted(variant.variant_id)"
              type="button"
              @click="handleRunVariant(variant.variant_id)"
              :disabled="state.busy"
              class="px-2.5 py-1 bg-indigo-600 text-white text-xs font-medium rounded hover:bg-indigo-700 disabled:opacity-50"
            >
              {{ $t('intervention.comparison.startRun') }}
            </button>
            <span v-else class="text-xs text-green-600 font-medium">
              ✓ 已启动模拟
            </span>
          </div>
        </div>
      </div>

      <!-- 对照曲线图 -->
      <div v-if="chartData.rounds.length > 0" class="bg-gray-50 rounded p-4 border border-gray-100 overflow-x-auto">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-medium text-gray-700">{{ $t('intervention.comparison.chartTitle') }}</span>
          <div class="flex items-center space-x-3 text-xs">
            <span class="flex items-center text-gray-600">
              <span class="w-2.5 h-0.5 bg-gray-500 inline-block mr-1"></span>对照组 (不干预)
            </span>
            <span class="flex items-center text-emerald-700">
              <span class="w-2.5 h-0.5 bg-emerald-600 inline-block mr-1"></span>早回应
            </span>
            <span class="flex items-center text-amber-700">
              <span class="w-2.5 h-0.5 bg-amber-600 inline-block mr-1"></span>晚回应
            </span>
          </div>
        </div>

        <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="w-full h-48 select-none">
          <!-- 网格横线 -->
          <g v-for="tick in yTicks" :key="tick.value">
            <line
              :x1="padding.left"
              :y1="tick.y"
              :x2="chartWidth - padding.right"
              :y2="tick.y"
              stroke="#e5e7eb"
              stroke-width="1"
            />
            <text
              :x="padding.left - 8"
              :y="tick.y + 3"
              text-anchor="end"
              class="text-[10px] fill-gray-400 font-mono"
            >
              {{ tick.value }}
            </text>
          </g>

          <!-- 三组曲线 -->
          <path
            v-for="line in variantLines"
            :key="line.variantId"
            :d="line.path"
            fill="none"
            :stroke="line.color"
            stroke-width="2"
            stroke-linejoin="round"
            stroke-linecap="round"
          />

          <!-- X 轴轮次刻度 -->
          <g v-for="tick in xTicks" :key="tick.round">
            <text
              :x="tick.x"
              :y="chartHeight - padding.bottom + 14"
              text-anchor="middle"
              class="text-[10px] fill-gray-500 font-mono"
            >
              R{{ tick.round }}
            </text>
          </g>
        </svg>
      </div>

      <!-- 不兼容运行提示 -->
      <div
        v-if="state.comparison?.incompatible_runs && state.comparison.incompatible_runs.length > 0"
        class="p-2.5 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800"
      >
        <span class="font-bold mr-1">⚠️ 部分运行不兼容:</span>
        <span v-for="item in state.comparison.incompatible_runs" :key="item.run_id">
          [{{ item.variant_id }}] {{ item.reason }}
        </span>
      </div>

      <!-- 实验局限性说明 -->
      <div
        v-if="state.comparison?.limitations && state.comparison.limitations.length > 0"
        class="bg-gray-50 rounded p-3 border border-gray-100 text-[11px] text-gray-500 space-y-1"
      >
        <div class="font-medium text-gray-600">{{ $t('intervention.comparison.limitationsTitle') }}:</div>
        <div v-for="(lim, idx) in state.comparison.limitations" :key="idx">
          • {{ lim }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  createInterventionExperiment,
  createInterventionExperimentRun,
  startInterventionExperimentRun,
  getInterventionComparison
} from '../api/simulation'
import { createComparisonController } from '../features/intervention/comparison-controller'

const { t } = useI18n()

const props = defineProps({
  simulationId: {
    type: String,
    required: true
  },
  topicId: {
    type: String,
    default: 'default'
  },
  publisherAgentId: {
    type: Number,
    default: 10
  }
})

const state = reactive({
  experiment: null,
  runs: [],
  comparison: null,
  busy: false,
  error: null
})

const form = ref({
  early_round: 5,
  late_round: 15,
  content: ''
})

const apiAdapter = {
  createInterventionExperiment,
  createInterventionExperimentRun,
  startInterventionExperimentRun,
  getInterventionComparison
}

const controller = createComparisonController({
  api: apiAdapter,
  state
})

async function handleCreateExperiment() {
  const payload = {
    source_simulation_id: props.simulationId,
    topic_id: props.topicId,
    t0_sources: [{ id: 't0_src', title: '初始材料', text: '场景冻结' }],
    metric_config: {
      topic_id: props.topicId,
      threshold: 5,
      consecutive_rounds: 2,
      minutes_per_round: 30,
      classifier_version: 'v1'
    },
    statement: {
      event_id: `stmt_${Date.now()}`,
      idempotency_key: `key_${Date.now()}`,
      run_id: props.simulationId,
      topic_id: props.topicId,
      platform: 'twitter',
      publisher_agent_id: props.publisherAgentId,
      content: form.value.content,
      kind: 'official_response',
      trigger: { mode: 'scheduled', round: form.value.early_round }
    },
    early_round: form.value.early_round,
    late_round: form.value.late_round
  }
  await controller.create(payload)
}

async function handleRunVariant(variantId) {
  const run = await controller.createRun(variantId, 1, 42)
  if (run?.run_id) {
    await controller.start(run.run_id)
    await handleRefreshComparison()
  }
}

async function handleRefreshComparison() {
  if (state.experiment?.experiment_id) {
    await controller.load(state.experiment.experiment_id)
  }
}

function getVariantBadgeClass(variantId) {
  if (variantId === 'control') return 'bg-gray-200 text-gray-700'
  if (variantId === 'early') return 'bg-emerald-100 text-emerald-800'
  if (variantId === 'late') return 'bg-amber-100 text-amber-800'
  return 'bg-blue-100 text-blue-800'
}

function isRunStarted(variantId) {
  const run = state.runs.find(r => r.variant_id === variantId)
  return run && (run.status === 'running' || run.status === 'completed')
}

function getRunStatusLabel(variantId) {
  const run = state.runs.find(r => r.variant_id === variantId)
  if (!run) return '未启动'
  return t(`intervention.comparison.runStatus.${run.status}`) || run.status
}

function getVariantMetric(variantId, metricKey) {
  if (!state.comparison?.runs) return '-'
  const entry = state.comparison.runs.find(r => r.variant_id === variantId)
  if (!entry?.bundle) return '-'
  if (metricKey === 'peak_heat') {
    return entry.bundle.cooling?.peak_heat != null ? entry.bundle.cooling.peak_heat : '-'
  }
  if (metricKey === 'cooling_duration') {
    const d = entry.bundle.cooling?.duration_rounds
    return d != null ? `${d} 轮` : (entry.bundle.cooling?.status === 'provisional' ? '计算中' : '未降温')
  }
  return '-'
}

// SVG 图表计算
const chartWidth = 640
const chartHeight = 180
const padding = { top: 20, right: 24, bottom: 28, left: 36 }

const chartData = computed(() => {
  const compRuns = state.comparison?.runs || []
  const allRounds = new Set()
  compRuns.forEach(r => {
    r.bundle?.rounds?.forEach(rnd => allRounds.add(rnd.round_num))
  })
  const sortedRounds = Array.from(allRounds).sort((a, b) => a - b)
  return { rounds: sortedRounds, runs: compRuns }
})

const maxHeat = computed(() => {
  let m = 5
  chartData.value.runs.forEach(r => {
    r.bundle?.rounds?.forEach(rnd => {
      if (rnd.heat != null && rnd.heat > m) m = rnd.heat
    })
  })
  return Math.ceil(m * 1.25)
})

const yTicks = computed(() => {
  const maxH = maxHeat.value
  const innerH = chartHeight - padding.top - padding.bottom
  const steps = 4
  const ticks = []
  for (let i = 0; i <= steps; i++) {
    const val = Math.round((maxH / steps) * i)
    const y = chartHeight - padding.bottom - (val / maxH) * innerH
    ticks.push({ value: val, y })
  }
  return ticks
})

const xTicks = computed(() => {
  const rounds = chartData.value.rounds
  const n = rounds.length
  if (n === 0) return []
  const innerW = chartWidth - padding.left - padding.right
  return rounds.map((rnd, idx) => ({
    round: rnd,
    x: padding.left + (n === 1 ? innerW / 2 : (idx / (n - 1)) * innerW)
  }))
})

const variantLines = computed(() => {
  const rounds = chartData.value.rounds
  const n = rounds.length
  if (n === 0) return []

  const innerW = chartWidth - padding.left - padding.right
  const innerH = chartHeight - padding.top - padding.bottom
  const maxH = maxHeat.value

  const colors = {
    control: '#6b7280',
    early: '#059669',
    late: '#d97706'
  }

  return chartData.value.runs.map(entry => {
    const pts = []
    rounds.forEach((rnd, idx) => {
      const match = entry.bundle?.rounds?.find(r => r.round_num === rnd)
      const x = padding.left + (n === 1 ? innerW / 2 : (idx / (n - 1)) * innerW)
      if (match && match.heat != null) {
        const y = chartHeight - padding.bottom - (match.heat / maxH) * innerH
        pts.push({ x, y })
      }
    })
    const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
    return {
      variantId: entry.variant_id,
      color: colors[entry.variant_id] || '#4f46e5',
      path
    }
  })
})
</script>
