<script setup lang="ts">
import { ref } from 'vue'
import { ChevronLeft } from 'lucide-vue-next'
import ChatInterface from '../components/console/ChatInterface.vue'
import KnowledgeBase from '../components/console/KnowledgeBase.vue'

const useRag = ref(true)
</script>

<template>
  <div class="min-h-screen p-6 md:p-12 max-w-4xl mx-auto space-y-8 animate-in fade-in duration-700">
    <!-- Header -->
    <header class="flex items-center justify-between mb-12">
      <router-link to="/" class="flex items-center gap-2 text-slate-500 hover:text-accent transition-colors group">
        <ChevronLeft class="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
        <span class="text-sm font-medium">返回主页</span>
      </router-link>
      
      <div class="flex items-center gap-3">
        <div class="w-2 h-2 rounded-full bg-accent animate-pulse-slow"></div>
        <span class="text-xs font-bold text-slate-500 uppercase tracking-widest">System Operational</span>
      </div>
    </header>

    <div class="space-y-2 mb-12">
      <h1 class="text-3xl font-black text-slate-100 tracking-tight">AI Gateway & RAG 控制台</h1>
      <p class="text-slate-500 text-sm">管理模型路由与知识库增强功能，为您的应用提供智能后端支持。</p>
    </div>

    <!-- Main Content Stack -->
    <div class="grid grid-cols-1 gap-8">
      <ChatInterface v-model:use-rag="useRag" />
      <KnowledgeBase v-show="useRag" />
    </div>

    <!-- Footer -->
    <footer class="mt-20 pt-8 border-t border-white/5 text-center">
      <p class="text-[10px] text-slate-600 uppercase tracking-[0.2em] font-bold">
        SYSU-SSE Cloud Infrastructure &copy; 2026
      </p>
    </footer>
  </div>
</template>

<style scoped>
.animate-in {
  animation: fadeIn 0.8s ease-out forwards;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
