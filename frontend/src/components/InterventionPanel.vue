<template>
  <div class="intervention-panel bg-white rounded-lg shadow-sm border border-gray-200 p-4">
    <div class="flex items-center justify-between mb-4 border-b border-gray-100 pb-3">
      <div>
        <h3 class="text-base font-semibold text-gray-900">{{ $t('intervention.title') }}</h3>
        <p class="text-xs text-gray-500 mt-0.5">{{ $t('intervention.subtitle') }}</p>
      </div>
      <span
        v-if="isReadOnlyPhase"
        class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600"
      >
        {{ phaseLabel }}
      </span>
    </div>

    <!-- 提交声明表单 -->
    <div v-if="!isReadOnlyPhase" class="mb-6 bg-gray-50 rounded-md p-3.5 border border-gray-100">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <!-- 平台选择 -->
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('intervention.platform') }}</label>
          <select
            v-model="form.platform"
            class="w-full text-xs rounded border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            <option v-for="p in supportedPlatforms" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>

        <!-- 角色选择 -->
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('intervention.role') }}</label>
          <select
            v-model.number="form.publisher_agent_id"
            class="w-full text-xs rounded border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            <option v-for="agent in availableAgents" :key="agent.agent_id" :value="agent.agent_id">
              {{ agent.name }} (ID: {{ agent.agent_id }})
            </option>
          </select>
        </div>

        <!-- 声明类型 -->
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('intervention.kind') }}</label>
          <select
            v-model="form.kind"
            class="w-full text-xs rounded border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            <option value="official_response">{{ $t('intervention.kinds.official_response') }}</option>
            <option value="fact_check">{{ $t('intervention.kinds.fact_check') }}</option>
            <option value="rumor_rebuttal">{{ $t('intervention.kinds.rumor_rebuttal') }}</option>
            <option value="custom">{{ $t('intervention.kinds.custom') }}</option>
          </select>
        </div>
      </div>

      <!-- 正文内容 -->
      <div class="mb-3">
        <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('intervention.content') }}</label>
        <textarea
          v-model="form.content"
          rows="3"
          :placeholder="$t('intervention.placeholderContent')"
          class="w-full text-xs rounded border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
        ></textarea>
      </div>

      <div class="flex items-center justify-between">
        <span class="text-xs text-gray-500 italic">
          {{ $t('intervention.triggerNextRound') }}
        </span>
        <button
          type="button"
          :disabled="controllerState.busy || !form.content.trim()"
          @click="handleSubmit"
          class="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50"
        >
          {{ controllerState.busy ? $t('intervention.submitting') : $t('intervention.submit') }}
        </button>
      </div>
      <p v-if="controllerState.error" class="text-xs text-red-600 mt-2">
        {{ controllerState.error }}
      </p>
    </div>

    <!-- 声明列表 -->
    <div>
      <h4 class="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2">已注入声明</h4>
      <div v-if="controllerState.items.length === 0" class="text-xs text-gray-400 py-4 text-center">
        {{ $t('intervention.noInterventions') }}
      </div>
      <div v-else class="space-y-2">
        <div
          v-for="item in controllerState.items"
          :key="item.statement.event_id"
          class="p-2.5 rounded border border-gray-100 bg-gray-50 text-xs flex flex-col gap-1.5"
        >
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="font-semibold text-gray-800">
                Agent {{ item.statement.publisher_agent_id }}
              </span>
              <span class="px-1.5 py-0.2 rounded bg-indigo-50 text-indigo-700 text-[10px]">
                {{ item.statement.platform }}
              </span>
              <span class="text-gray-400">|</span>
              <span class="text-gray-600">
                {{ $t(`intervention.kinds.${item.statement.kind}`) }}
              </span>
            </div>
            <div class="flex items-center space-x-2">
              <span
                :class="statusBadgeClass(item.execution.status)"
                class="px-2 py-0.5 rounded text-[10px] font-medium"
              >
                {{ $t(`intervention.status.${item.execution.status}`) }}
              </span>
              <button
                v-if="canCancel(item.execution.status)"
                @click="handleCancel(item.statement.event_id)"
                class="text-[10px] text-red-600 hover:underline"
              >
                {{ $t('intervention.cancel') }}
              </button>
            </div>
          </div>
          <!-- 纯文本插值，禁止 v-html -->
          <p class="text-gray-700 whitespace-pre-wrap break-words text-xs">
            {{ item.statement.content }}
          </p>
          <div class="flex items-center justify-between text-[10px] text-gray-400 pt-1 border-t border-gray-200/50">
            <span>
              {{ $t('intervention.effectiveRound') }}: {{ item.execution.effective_round ?? '-' }}
            </span>
            <span v-if="item.execution.receipt?.post_id">
              {{ $t('intervention.postId') }}: {{ item.execution.receipt.post_id }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部免责声明说明 -->
    <p class="mt-4 text-[10px] text-gray-400 leading-normal">
      * {{ $t('intervention.disclaimer') }}
    </p>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { createInterventionController } from '../features/intervention/controller.js'
import * as simApi from '../api/simulation.js'

const props = defineProps({
  simulationId: {
    type: String,
    required: true
  },
  phase: {
    type: String,
    default: 'running'
  },
  topicId: {
    type: String,
    default: 'default'
  },
  profiles: {
    type: Array,
    default: () => []
  },
  supportedPlatforms: {
    type: Array,
    default: () => ['twitter', 'reddit']
  }
})

const controllerState = reactive({
  items: [],
  busy: false,
  error: null,
  pendingKey: null,
  currentRunId: null
})

const controller = createInterventionController({
  api: simApi,
  state: controllerState
})

const form = reactive({
  platform: 'twitter',
  publisher_agent_id: 0,
  kind: 'official_response',
  content: ''
})

const availableAgents = computed(() => {
  if (props.profiles && props.profiles.length > 0) {
    return props.profiles.map((p, idx) => ({
      agent_id: p.agent_id ?? p.id ?? idx,
      name: p.name || p.username || `Agent_${idx}`
    }))
  }
  return [{ agent_id: 0, name: 'Default Official' }]
})

watch(
  availableAgents,
  (agents) => {
    if (agents.length > 0 && !agents.some(a => a.agent_id === form.publisher_agent_id)) {
      form.publisher_agent_id = agents[0].agent_id
    }
  },
  { immediate: true }
)

const isReadOnlyPhase = computed(() => {
  return ['interview', 'stopped', 'completed', 'failed'].includes(props.phase)
})

const phaseLabel = computed(() => {
  return props.phase.toUpperCase()
})

const canCancel = (status) => {
  return ['queued', 'accepted'].includes(status) && !isReadOnlyPhase.value
}

const statusBadgeClass = (status) => {
  switch (status) {
    case 'published':
      return 'bg-green-100 text-green-800'
    case 'executing':
      return 'bg-blue-100 text-blue-800'
    case 'accepted':
    case 'queued':
      return 'bg-yellow-100 text-yellow-800'
    case 'failed':
      return 'bg-red-100 text-red-800'
    case 'canceled':
      return 'bg-gray-100 text-gray-600'
    case 'expired':
      return 'bg-orange-100 text-orange-800'
    default:
      return 'bg-purple-100 text-purple-800'
  }
}

const handleSubmit = async () => {
  if (!form.content.trim()) return
  const payload = {
    topic_id: props.topicId,
    platform: form.platform,
    publisher_agent_id: form.publisher_agent_id,
    kind: form.kind,
    content: form.content.trim(),
    trigger: { mode: 'next_round' }
  }
  const result = await controller.submit(props.simulationId, payload)
  if (result) {
    form.content = ''
  }
}

const handleCancel = async (eventId) => {
  await controller.cancel(props.simulationId, eventId)
}

onMounted(() => {
  if (props.simulationId) {
    controller.load(props.simulationId)
    controller.startPolling(props.simulationId)
  }
})

onUnmounted(() => {
  controller.stopPolling()
})

watch(
  () => props.simulationId,
  (newId) => {
    if (newId) {
      controller.load(newId)
      controller.startPolling(newId)
    }
  }
)
</script>
