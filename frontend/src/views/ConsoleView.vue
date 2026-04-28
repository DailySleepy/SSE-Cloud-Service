<script setup lang="ts">
import { ref } from 'vue'
import ChatInterface from '../components/console/ChatInterface.vue'
import KnowledgeBase from '../components/console/KnowledgeBase.vue'

const useRag = ref(true)
</script>

<template>
  <div class="min-h-screen p-6 md:p-12 max-w-4xl mx-auto space-y-8 animate-in fade-in duration-700">
    <div class="space-y-2 mb-12">
      <h1 class="text-3xl font-black text-slate-100 tracking-tight">AI Gateway & RAG 控制台</h1>
      <p class="text-slate-500 text-sm">管理模型路由与知识库增强功能，为您的应用提供智能后端支持。</p>
    </div>

    <div class="grid grid-cols-1 gap-8">
      <ChatInterface v-model:use-rag="useRag" />
      <KnowledgeBase v-show="useRag" />
    </div>
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
