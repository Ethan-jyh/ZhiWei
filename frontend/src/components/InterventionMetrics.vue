<template>
  <div class="intervention-metrics bg-white rounded-lg shadow-sm border border-gray-200 p-4">
    <!-- 头部标题栏 -->
    <div class="flex items-center justify-between border-b border-gray-100 pb-3 mb-4">
      <div>
        <h3 class="text-base font-semibold text-gray-900">{{ $t('intervention.metrics.title') }}</h3>
        <p class="text-xs text-gray-500 mt-0.5">{{ $t('intervention.metrics.subtitle') }}</p>
      </div>
      <div v-if="configured && !showConfigForm" class="flex items-center space-x-2">
        <button
          type="button"
          @click="showCorrectionForm = !showCorrectionForm"
          class="text-xs px-2.5 py-1 bg-gray-50 text-gray-700 hover:bg-gray-100 rounded border border-gray-200"
        >
          {{ $t('intervention.metrics.correctTitle') }}
        </button>
        <button
          type="button"
          @click="showConfigForm = true"
          class="text-xs px-2.5 py-1 bg-gray-50 text-gray-700 hover:bg-gray-100 rounded border border-gray-200"
        >
          {{ $t('intervention.metrics.reconfigure') }}
        </button>
      </div>
    </div>

    <!-- 未配置或修改配置表单 -->
    <div v-if="!configured || showConfigForm" class="bg-gray-50 rounded-md p-4 mb-4 border border-gray-100">
      <div class="flex items-center justify-between mb-3">
        <h4 class="text-xs font-semibold text-gray-800">{{ $t('intervention.metrics.configureTitle') }}</h4>
        <button
          v-if="configured && showConfigForm"
          type="button"
          @click="showConfigForm = false"
          class="text-xs text-gray-400 hover:text-gray-600"
        >
          ✕
        </button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('intervention.metrics.threshold') }}</label>
          <input
            v-model.number="configForm.threshold"
            type="number"
            min="0"
            class="w-full text-xs rounded border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('intervention.metrics.consecutiveRounds') }}</label>
          <input
            v-model.number="configForm.consecutive_rounds"
            type="number"
            min="1"
            class="w-full text-xs rounded border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('intervention.metrics.minutesPerRound') }}</label>
          <input
            v-model.number="configForm.minutes_per_round"
            type="number"
            min="1"
            class="w-full text-xs rounded border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>
      </div>
      <div class="flex justify-end">
        <button
          type="button"
          @click="handleSaveConfig"
          :disabled="savingConfig"
          class="px-3 py-1.5 bg-indigo-600 text-white text-xs font-medium rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          {{ savingConfig ? '...' : $t('intervention.metrics.saveAndCalculate') }}
        </button>
      </div>
    </div>

    <!-- 人工修正标签表单 (折叠) -->
    <div v-if="showCorrectionForm" class="bg-amber-50 rounded-md p-4 mb-4 border border-amber-200">
      <div class="flex items-center justify-between mb-3">
        <h4 class="text-xs font-semibold text-amber-900">{{ $t('intervention.metrics.correctTitle') }}</h4>
        <button
          type="button"
          @click="showCorrectionForm = false"
          class="text-xs text-amber-600 hover:text-amber-800"
        >
          ✕
        </button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
        <div>
          <label class="block text-xs font-medium text-amber-800 mb-1">{{ $t('intervention.metrics.correctPlatform') }}</label>
          <select
            v-model="correctionForm.platform"
            class="w-full text-xs rounded border-amber-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            <option value="twitter">twitter</option>
            <option value="reddit">reddit</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-amber-800 mb-1">{{ $t('intervention.metrics.correctRowId') }}</label>
          <input
            v-model.number="correctionForm.trace_rowid"
            type="number"
            min="1"
            class="w-full text-xs rounded border-amber-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-amber-800 mb-1">{{ $t('intervention.metrics.correctRelated') }}</label>
          <select
            v-model="correctionForm.related"
            class="w-full text-xs rounded border-amber-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            <option :value="true">是 (相关)</option>
            <option :value="false">否 (无关)</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-amber-800 mb-1">{{ $t('intervention.metrics.correctReason') }}</label>
          <input
            v-model="correctionForm.reason"
            type="text"
            placeholder="人工核实判定原因"
            class="w-full text-xs rounded border-amber-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>
      </div>
      <div class="flex justify-end">
        <button
          type="button"
          @click="handleSubmitCorrection"
          :disabled="submittingCorrection || !correctionForm.trace_rowid"
          class="px-3 py-1.5 bg-amber-600 text-white text-xs font-medium rounded hover:bg-amber-700 disabled:opacity-50"
        >
          {{ submittingCorrection ? '...' : $t('intervention.metrics.submitCorrection') }}
        </button>
      </div>
    </div>

    <!-- 计算中状态 -->
    <div v-if="computing" class="p-6 text-center text-xs text-gray-500">
      <div class="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-indigo-600 mb-2"></div>
      <p>{{ $t('intervention.metrics.computing') }}</p>
    </div>

    <!-- 指标摘要卡片 -->
    <div v-else-if="bundle && configured" class="space-y-4">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <!-- 峰值 -->
        <div class="bg-gray-50 rounded p-3 border border-gray-100">
          <div class="text-xs text-gray-500">{{ $t('intervention.metrics.peakHeat') }}</div>
          <div class="text-lg font-bold text-gray-900 mt-1">
            {{ bundle.cooling.peak_heat != null ? bundle.cooling.peak_heat : '-' }}
          </div>
          <div class="text-xs text-gray-400 mt-0.5">
            {{ bundle.cooling.peak_round != null ? $t('intervention.metrics.peakRound', { round: bundle.cooling.peak_round }) : '' }}
          </div>
        </div>

        <!-- 回落耗时 -->
        <div class="bg-gray-50 rounded p-3 border border-gray-100">
          <div class="text-xs text-gray-500">{{ $t('intervention.metrics.coolingDuration') }}</div>
          <div class="text-lg font-bold text-gray-900 mt-1">
            <template v-if="bundle.cooling.duration_rounds != null">
              {{ $t('intervention.metrics.durationDetail', { rounds: bundle.cooling.duration_rounds, minutes: bundle.cooling.duration_minutes }) }}
            </template>
            <template v-else>-</template>
          </div>
          <div class="text-xs text-gray-400 mt-0.5">
            {{ bundle.cooling.confirmed_round ? `确认于第 ${bundle.cooling.confirmed_round} 轮` : '' }}
          </div>
        </div>

        <!-- 冷却状态 -->
        <div class="bg-gray-50 rounded p-3 border border-gray-100">
          <div class="text-xs text-gray-500">状态</div>
          <div class="mt-1">
            <span
              class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
              :class="coolingStatusClass"
            >
              {{ $t(`intervention.metrics.status.${bundle.cooling.status}`) }}
            </span>
          </div>
        </div>

        <!-- 阈值参数 -->
        <div class="bg-gray-50 rounded p-3 border border-gray-100">
          <div class="text-xs text-gray-500">设定阈值 / 窗口</div>
          <div class="text-sm font-semibold text-gray-800 mt-1">
            θ = {{ bundle.config.threshold }}
          </div>
          <div class="text-xs text-gray-400 mt-0.5">
            w = {{ bundle.config.consecutive_rounds }} 轮连续达标
          </div>
        </div>
      </div>

      <!-- 反弹提示 -->
      <div
        v-if="bundle.cooling.rebound_rounds && bundle.cooling.rebound_rounds.length > 0"
        class="p-2.5 bg-red-50 border border-red-200 rounded text-xs text-red-700 flex items-center"
      >
        <span class="mr-1.5">⚠️</span>
        <span>{{ $t('intervention.metrics.reboundAlert', { rounds: bundle.cooling.rebound_rounds.join(', ') }) }}</span>
      </div>

      <!-- 舆情热度走势 SVG 图表 -->
      <div class="bg-gray-50 rounded p-4 border border-gray-100 overflow-x-auto">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-medium text-gray-700">各轮次舆情热度与干预时点</span>
          <div class="flex items-center space-x-3 text-xs text-gray-500">
            <span class="flex items-center"><span class="w-2.5 h-0.5 bg-indigo-600 inline-block mr-1"></span>热度走势</span>
            <span class="flex items-center"><span class="w-2.5 h-0.5 border-b border-dashed border-red-500 inline-block mr-1"></span>回落阈值 (θ)</span>
            <span class="flex items-center"><span class="w-2 h-2 rounded-full bg-amber-500 inline-block mr-1"></span>声明发布</span>
          </div>
        </div>

        <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="w-full h-48 select-none">
          <!-- 网格横线与Y轴刻度 -->
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

          <!-- 阈值参考虚线 -->
          <line
            v-if="thresholdY != null"
            :x1="padding.left"
            :y1="thresholdY"
            :x2="chartWidth - padding.right"
            :y2="thresholdY"
            stroke="#ef4444"
            stroke-width="1.5"
            stroke-dasharray="4 3"
          />

          <!-- 折线片段（缺失轮次自动断线） -->
          <path
            v-for="(seg, idx) in lineSegments"
            :key="idx"
            :d="seg"
            fill="none"
            stroke="#4f46e5"
            stroke-width="2"
            stroke-linejoin="round"
            stroke-linecap="round"
          />

          <!-- 轮次数据点 -->
          <g v-for="pt in points" :key="pt.round">
            <template v-if="pt.heat != null">
              <circle
                :cx="pt.x"
                :cy="pt.y"
                r="3.5"
                fill="#4f46e5"
                stroke="#ffffff"
                stroke-width="1.5"
              />
              <text
                :x="pt.x"
                :y="pt.y - 7"
                text-anchor="middle"
                class="text-[9px] fill-indigo-800 font-mono font-medium"
              >
                {{ pt.heat }}
              </text>
            </template>
            <template v-else>
              <!-- 缺失或待定轮次标记 -->
              <text
                :x="pt.x"
                :y="chartHeight - padding.bottom - 10"
                text-anchor="middle"
                class="text-[9px] fill-gray-400 italic"
              >
                待定
              </text>
            </template>

            <!-- X 轴轮次刻度 -->
            <text
              :x="pt.x"
              :y="chartHeight - padding.bottom + 14"
              text-anchor="middle"
              class="text-[10px] fill-gray-500 font-mono"
            >
              R{{ pt.round }}
            </text>
          </g>

          <!-- 干预声明发布标记 -->
          <g v-for="marker in markerPins" :key="marker.id">
            <line
              :x1="marker.x"
              :y1="padding.top"
              :x2="marker.x"
              :y2="chartHeight - padding.bottom"
              stroke="#f59e0b"
              stroke-width="1.5"
              stroke-dasharray="2 2"
            />
            <circle
              :cx="marker.x"
              :cy="padding.top + 4"
              r="4"
              fill="#f59e0b"
              stroke="#ffffff"
              stroke-width="1.5"
            />
            <title>{{ marker.tooltip }}</title>
          </g>
        </svg>
      </div>

      <!-- 责任免除与说明 -->
      <div class="text-[11px] text-gray-400 bg-gray-50 rounded p-2.5 border border-gray-100">
        {{ $t('intervention.metrics.disclaimer') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getInterventionMetrics,
  saveInterventionMetricConfig,
  correctInterventionLabel,
  listInterventions
} from '../api/simulation'
import { loadMetricView } from '../features/intervention/metrics-controller'

const { t } = useI18n()

const props = defineProps({
  simulationId: {
    type: String,
    required: true
  },
  topicId: {
    type: String,
    default: 'default'
  }
})

const configured = ref(false)
const computing = ref(false)
const bundle = ref(null)
const markers = ref([])
const showConfigForm = ref(false)
const showCorrectionForm = ref(false)
const savingConfig = ref(false)
const submittingCorrection = ref(false)

const configForm = ref({
  threshold: 5,
  consecutive_rounds: 2,
  minutes_per_round: 30,
  classifier_version: 'v1'
})

const correctionForm = ref({
  platform: 'twitter',
  trace_rowid: null,
  related: true,
  reason: ''
})

let pollTimer = null

const apiAdapter = {
  getInterventionMetrics,
  listInterventions
}

async function refreshMetrics() {
  if (!props.simulationId) return
  const view = await loadMetricView(apiAdapter, props.simulationId)
  configured.value = view.configured
  computing.value = view.computing
  bundle.value = view.bundle
  markers.value = view.markers || []

  if (view.bundle?.config) {
    configForm.value = {
      threshold: view.bundle.config.threshold,
      consecutive_rounds: view.bundle.config.consecutive_rounds,
      minutes_per_round: view.bundle.config.minutes_per_round,
      classifier_version: view.bundle.config.classifier_version
    }
  }
}

async function handleSaveConfig() {
  savingConfig.value = true
  try {
    const payload = {
      topic_id: props.topicId || 'default',
      threshold: Number(configForm.value.threshold),
      consecutive_rounds: Number(configForm.value.consecutive_rounds),
      minutes_per_round: Number(configForm.value.minutes_per_round),
      classifier_version: configForm.value.classifier_version || 'v1'
    }
    await saveInterventionMetricConfig(props.simulationId, payload)
    showConfigForm.value = false
    await refreshMetrics()
  } catch (err) {
    console.error('Failed to save config:', err)
  } finally {
    savingConfig.value = false
  }
}

async function handleSubmitCorrection() {
  submittingCorrection.value = true
  try {
    await correctInterventionLabel(props.simulationId, {
      platform: correctionForm.value.platform,
      trace_rowid: Number(correctionForm.value.trace_rowid),
      related: Boolean(correctionForm.value.related),
      reason: correctionForm.value.reason
    })
    showCorrectionForm.value = false
    correctionForm.value.trace_rowid = null
    correctionForm.value.reason = ''
    await refreshMetrics()
  } catch (err) {
    console.error('Failed to correct label:', err)
  } finally {
    submittingCorrection.value = false
  }
}

const coolingStatusClass = computed(() => {
  const s = bundle.value?.cooling?.status
  if (s === 'cooled') return 'bg-green-100 text-green-800'
  if (s === 'provisional') return 'bg-amber-100 text-amber-800'
  if (s === 'not_cooled') return 'bg-rose-100 text-rose-800'
  if (s === 'below_threshold') return 'bg-blue-100 text-blue-800'
  return 'bg-gray-100 text-gray-700'
})

// SVG 图表几何计算
const chartWidth = 640
const chartHeight = 180
const padding = { top: 20, right: 24, bottom: 28, left: 36 }

const roundsList = computed(() => bundle.value?.rounds || [])

const maxHeatValue = computed(() => {
  const heats = roundsList.value.map(r => r.heat).filter(h => h != null)
  const thresh = bundle.value?.config?.threshold || 0
  const m = Math.max(...heats, thresh, 5)
  return Math.ceil(m * 1.25)
})

const points = computed(() => {
  const list = roundsList.value
  const n = list.length
  if (n === 0) return []

  const innerW = chartWidth - padding.left - padding.right
  const innerH = chartHeight - padding.top - padding.bottom
  const maxH = maxHeatValue.value

  return list.map((r, idx) => {
    const x = padding.left + (n === 1 ? innerW / 2 : (idx / (n - 1)) * innerW)
    const y = r.heat != null ? chartHeight - padding.bottom - (r.heat / maxH) * innerH : null
    return {
      round: r.round_num,
      heat: r.heat,
      status: r.status,
      x,
      y
    }
  })
})

const yTicks = computed(() => {
  const maxH = maxHeatValue.value
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

const thresholdY = computed(() => {
  const thresh = bundle.value?.config?.threshold
  if (thresh == null) return null
  const innerH = chartHeight - padding.top - padding.bottom
  const maxH = maxHeatValue.value
  return chartHeight - padding.bottom - (thresh / maxH) * innerH
})

const lineSegments = computed(() => {
  const pts = points.value
  const segments = []
  let current = []

  for (const pt of pts) {
    if (pt.y != null) {
      current.push(pt)
    } else {
      if (current.length > 1) {
        segments.push(buildPathString(current))
      }
      current = []
    }
  }
  if (current.length > 1) {
    segments.push(buildPathString(current))
  }
  return segments
})

function buildPathString(pts) {
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
}

const markerPins = computed(() => {
  const pts = points.value
  if (!markers.value.length || !pts.length) return []
  return markers.value.map((m, idx) => {
    const pt = pts.find(p => p.round === m.round)
    const x = pt ? pt.x : padding.left
    return {
      id: idx,
      x,
      round: m.round,
      tooltip: `第 ${m.round} 轮干预声明: ${m.content || ''}`
    }
  })
})

watch(() => props.simulationId, () => {
  refreshMetrics()
})

onMounted(() => {
  refreshMetrics()
  pollTimer = setInterval(() => {
    if (computing.value) {
      refreshMetrics()
    }
  }, 4000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
