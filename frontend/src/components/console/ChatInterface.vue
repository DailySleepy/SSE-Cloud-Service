<script setup lang="ts">
import { ref } from 'vue'
import { MessageSquare, Zap, Book, RefreshCw } from 'lucide-vue-next'

interface Citation {
  source: string
  text: string
}

interface ChatResult {
  content: string
  error?: boolean
  status?: number
  meta?: {
    latency?: number
    cached?: boolean
    totalTime?: number
  }
  citations?: Citation[]
}

const model = ref('ollama/qwen2.5:0.5b')
const useRag = defineModel<boolean>('useRag', { default: true })
const topK = ref(3)
const prompt = ref('')
const isLoading = ref(false)
const result = ref<ChatResult | null>(null)
const startTime = ref(0)
const totalTime = ref(0)

const submitChat = async () => {
  if (!prompt.value.trim() || isLoading.value) return
  
  isLoading.value = true
  startTime.value = Date.now()
  result.value = { content: useRag.value ? '正在检索知识并生成回答...' : '正在生成回答...', meta: {}, citations: [] }

  try {
    const response = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: model.value,
        messages: [{ role: "user", content: prompt.value }],
        use_rag: useRag.value,
        top_k: topK.value
      })
    })

    const data = await response.json()
    totalTime.value = Date.now() - startTime.value

    if (!response.ok) {
      result.value = { 
        error: true,
        content: data.detail || JSON.stringify(data.error || data),
        status: response.status 
      }
      return
    }

    result.value = {
      content: data.choices[0]?.message?.content || "无返回。",
      meta: {
        latency: data.usage?.latency_ms,
        cached: data._meta?.cached,
        totalTime: totalTime.value
      },
      citations: data.citations || []
    }
  } catch (err: any) {
    result.value = { error: true, content: "网络异常: " + err.message }
  } finally {
    isLoading.value = false
  }
}

const handleKeyDown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submitChat()
  }
}
</script>

<template>
  <div class="glass-card p-8 mb-8 space-y-6">
    <div class="flex items-center gap-3 border-b border-white/5 pb-4">
      <MessageSquare class="w-6 h-6 text-accent" />
      <h2 class="text-xl font-bold text-slate-100">对话 Playground</h2>
    </div>

    <div class="space-y-4">
      <div class="input-group">
        <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">推理模型后端</label>
        <select v-model="model" class="input-base">
          <option value="ollama/qwen2.5:0.5b">Ollama: Qwen 2.5 (本地 0.5B)</option>
          <option value="saas/openrouter/auto">SaaS: OpenRouter (Auto)</option>
        </select>
      </div>

      <div class="p-4 rounded-xl bg-white/5 border border-white/5 space-y-4">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium text-slate-300">启用 RAG 知识检索增强</span>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="useRag" class="sr-only peer">
            <div class="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent"></div>
          </label>
        </div>

        <div v-if="useRag" class="flex items-center justify-between pt-3 border-t border-white/5">
          <span class="text-xs text-slate-400 font-medium">检索数量 (Top-K)</span>
          <input type="number" v-model="topK" min="1" max="10" 
                 class="w-16 bg-slate-900/50 border border-white/10 rounded px-2 py-1 text-center text-sm">
        </div>
      </div>

      <div class="input-group">
        <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">输入指令</label>
        <textarea v-model="prompt" @keydown="handleKeyDown" rows="4" 
                  placeholder="向 AI 提问，如果启用了 RAG，它会参考检索到的文档..."
                  class="input-base resize-none"></textarea>
      </div>

      <button @click="submitChat" :disabled="isLoading" class="btn-primary w-full flex items-center justify-center gap-2 group">
        <RefreshCw v-if="isLoading" class="w-5 h-5 animate-spin" />
        <Zap v-else class="w-5 h-5 group-hover:animate-pulse" />
        <span>{{ isLoading ? '思考中...' : '发起调用请求' }}</span>
      </button>

      <!-- Result Panel -->
      <div v-if="result" class="mt-8 space-y-4 transition-all animate-in fade-in duration-500">
        <div class="flex flex-wrap gap-2 text-[10px] uppercase font-bold tracking-widest">
          <span v-if="result.meta?.totalTime" class="px-2 py-1 rounded bg-slate-800 text-slate-400 border border-white/5">
            端到端: {{ result.meta.totalTime }}ms
          </span>
          <span v-if="result.meta?.latency" class="px-2 py-1 rounded bg-slate-800 text-slate-400 border border-white/5">
            推理: {{ result.meta.latency }}ms
          </span>
          <span v-if="result.meta?.cached" class="px-2 py-1 rounded bg-accent/20 text-accent border border-accent/30 font-black italic">
            ⚡ Redis 命中
          </span>
          <span v-if="useRag" class="px-2 py-1 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">
            📚 RAG 已启用
          </span>
          <span v-if="result.error" class="px-2 py-1 rounded bg-red-500/20 text-red-400 border border-red-500/30">
            错误 {{ result.status }}
          </span>
        </div>

        <div class="p-6 rounded-xl bg-black/30 border border-white/5 text-slate-200 leading-relaxed whitespace-pre-wrap text-sm">
          {{ result.content }}
        </div>

        <div v-if="result.citations?.length" class="p-4 rounded-xl bg-white/5 border border-white/5 space-y-3">
          <div class="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-tighter">
            <Book class="w-4 h-4" />
            <span>参考引文</span>
          </div>
          <div class="space-y-2">
            <div v-for="(cite, idx) in result.citations" :key="idx" class="text-xs text-slate-500 italic leading-relaxed">
              <strong class="text-accent">[{{ idx + 1 }}]</strong> {{ cite.source }}: 
              <span class="text-slate-400 leading-relaxed">"{{ cite.text.length > 150 ? cite.text.substring(0, 150) + '...' : cite.text }}"</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 移除数字输入框的原生箭头 */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
input[type="number"] {
  -moz-appearance: textfield;
}
</style>
