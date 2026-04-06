<script setup lang="ts">
import { BookOpen, Terminal } from 'lucide-vue-next'
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-6">
    <div class="container max-w-2xl text-center glass-card p-12 relative animate-in fade-in slide-in-from-bottom-5 duration-1000">
      <div class="inline-block px-5 py-1.5 rounded-full bg-gradient-to-r from-accent to-[#456d33] text-white text-sm font-bold tracking-widest mb-8 shadow-lg shadow-accent/30">
        SYSU-SSE
      </div>
      
      <h1 class="text-5xl md:text-6xl font-extrabold mb-6 bg-gradient-to-br from-white to-slate-400 bg-clip-text text-transparent tracking-tighter">
        SSE Cloud Service <span class="text-2xl align-top opacity-60">v0.3.0</span>
      </h1>
      
      <p class="text-lg text-slate-400 mb-12 leading-relaxed max-w-lg mx-auto">
        欢迎来到云原生与服务计算联合实验环境。所有核心微服务架构均已准备就绪并平稳运行。
      </p>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-6 mt-8">
        <a href="/blog/" class="group p-6 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 hover:border-white/20 transition-all duration-300 flex flex-col items-center gap-3">
          <BookOpen class="w-10 h-10 text-accent group-hover:scale-110 transition-transform" />
          <span class="font-bold text-slate-200">技术博客</span>
          <span class="text-xs text-slate-500">访问 WordPress 服务</span>
        </a>

        <router-link to="/console" class="group p-6 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 hover:border-white/20 transition-all duration-300 flex flex-col items-center gap-3">
          <Terminal class="w-10 h-10 text-accent group-hover:scale-110 transition-transform" />
          <span class="font-bold text-slate-200">CourseBot API</span>
          <span class="text-xs text-slate-500">AI Gateway 控制台</span>
        </router-link>
      </div>

      <div class="mt-12 pt-8 border-t border-white/5 flex justify-center gap-8 text-slate-500 text-xs uppercase tracking-widest">
        <span>Cloud Native</span>
        <span>Service Computing</span>
        <span>AI Gateway</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.animate-in {
  animation: fadeIn 1.2s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
