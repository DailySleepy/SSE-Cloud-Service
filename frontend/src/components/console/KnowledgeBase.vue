<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { FileText, Upload, Trash2, Database, Loader2 } from 'lucide-vue-next'

const documents = ref<any[]>([])
const isLoading = ref(false)
const isUploading = ref(false)
const uploadProgress = ref(0)
const uploadStatus = ref('')
const currentTaskId = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const dragCounter = ref(0)

const fetchDocs = async () => {
    isLoading.value = true
    try {
        const response = await fetch('/v1/rag/docs?show_content=true')
        const data = await response.json()
        documents.value = data.documents || []
    } catch (err) {
        console.error('Failed to fetch docs:', err)
    } finally {
        isLoading.value = false
    }
}

const deleteDoc = async (source: string) => {
    if (!confirm(`确定要删除文档 "${source}" 吗？此操作不可逆。`)) return
    try {
        const response = await fetch(`/v1/rag/docs/${encodeURIComponent(source)}`, { method: 'DELETE' })
        if (response.ok) fetchDocs()
        else alert("删除失败")
    } catch (err: any) {
        alert("异常: " + err.message)
    }
}

const handleFileUpload = async (file: File) => {
    if (file.size > 10 * 1024 * 1024) {
        uploadStatus.value = '❌ 失败: 文件大小不能超过 10MB'
        return
    }

    isUploading.value = true
    uploadProgress.value = 0
    uploadStatus.value = `正在上传并解析: ${file.name}...`

    const formData = new FormData()
    formData.append('file', file)

    try {
        const response = await fetch('/v1/ingest/file', {
            method: 'POST',
            body: formData
        })
        const data = await response.json()

        if (!response.ok) {
            uploadStatus.value = `❌ 上传失败: ${data.detail || '未知错误'}`
            isUploading.value = false
            return
        }

        currentTaskId.value = data.task_id
        startPolling(data.task_id)
    } catch (err: any) {
        uploadStatus.value = `❌ 网络异常: ${err.message}`
        isUploading.value = false
    }
}

const startPolling = (taskId: string) => {
    const timer = setInterval(async () => {
        try {
            const response = await fetch(`/v1/ingest/status/${taskId}`)
            const data = await response.json()

            if (data.status === 'completed') {
                uploadProgress.value = 100
                uploadStatus.value = '✅ 处理完成！'
                clearInterval(timer)
                setTimeout(() => {
                    isUploading.value = false
                    fetchDocs()
                }, 1000)
            } else if (data.status === 'failed') {
                uploadStatus.value = `❌ 处理失败: ${data.error}`
                clearInterval(timer)
            } else {
                uploadProgress.value = data.progress || 0
                uploadStatus.value = `正在处理: ${uploadProgress.value}%`
            }
        } catch (err) {
            clearInterval(timer)
            isUploading.value = false
        }
    }, 1000)
}

const cancelUpload = async () => {
    if (!currentTaskId.value) return
    try {
        await fetch(`/v1/ingest/cancel/${currentTaskId.value}`, { method: 'DELETE' })
        uploadStatus.value = '⚠️ 已取消处理'
        setTimeout(() => { isUploading.value = false }, 1500)
    } catch (err) {
        console.error('Cancel failed:', err)
    }
}

const onDrop = (e: DragEvent) => {
    dragCounter.value = 0
    isDragging.value = false
    const files = e.dataTransfer?.files
    if (files && files.length > 0) handleFileUpload(files[0])
}

const onDragEnter = (e: DragEvent) => {
    e.preventDefault()
    dragCounter.value++
    isDragging.value = true
}

const onDragLeave = (e: DragEvent) => {
    e.preventDefault()
    dragCounter.value--
    if (dragCounter.value === 0) {
        isDragging.value = false
    }
}

const onFileChange = (e: Event) => {
    const files = (e.target as HTMLInputElement).files
    if (files && files.length > 0) handleFileUpload(files[0])
}

const toggleContent = (doc: any) => {
    doc.showContent = !doc.showContent
}

onMounted(fetchDocs)
</script>

<template>
    <div class="glass-card p-8 space-y-6">
        <div class="flex items-center justify-between border-b border-white/5 pb-4">
            <div class="flex items-center gap-3">
                <Database class="w-6 h-6 text-accent" />
                <h2 class="text-xl font-bold text-slate-100">知识库管理</h2>
            </div>
        </div>

        <!-- Upload Zone -->
        <div @click="fileInput?.click()" 
             @dragover.prevent 
             @dragenter="onDragEnter"
             @dragleave="onDragLeave"
             @drop.prevent="onDrop"
             :class="{ 'border-accent bg-accent/10 scale-[1.02]': isDragging }"
             class="group border-2 border-dashed border-white/10 rounded-2xl p-10 text-center cursor-pointer hover:border-accent hover:bg-accent/5 transition-all space-y-4">
            <div class="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto group-hover:scale-110 transition-transform">
                <Upload class="w-8 h-8 text-slate-400 group-hover:text-accent" />
            </div>
            <div class="space-y-1">
                <p class="text-slate-200 font-semibold">点击或拖拽文件到此处上传</p>
                <p class="text-xs text-slate-500">支持 .txt, .pdf, .md (Max 10MB)</p>
            </div>
            <input type="file" ref="fileInput" @change="onFileChange" hidden accept=".txt,.pdf,.md">
        </div>

        <!-- Uploading Status -->
        <div v-if="isUploading" class="space-y-3 animate-in slide-in-from-top-2 duration-500">
            <div class="h-2 bg-white/5 rounded-full overflow-hidden shadow-inner">
                <div class="h-full bg-gradient-to-r from-accent to-blue-500 transition-all duration-300 shadow-[0_0_10px_var(--accent-glow)]"
                     :style="{ width: `${uploadProgress}%` }"></div>
            </div>
            <div class="flex items-center justify-between text-xs font-semibold text-slate-400 px-1">
                <span class="flex items-center gap-2">
                    <Loader2 class="w-3 h-3 animate-spin" />
                    {{ uploadStatus }}
                </span>
                <button @click="cancelUpload" class="text-red-400 hover:text-red-300 transition-colors uppercase tracking-widest text-[10px]">
                    取消
                </button>
            </div>
        </div>

        <!-- Document List -->
        <div class="space-y-4 pt-4">
            <div class="flex items-center justify-between px-2 text-xs font-bold text-slate-500 uppercase tracking-widest">
                <span>已存文档 ({{ documents.length }})</span>
            </div>

            <div v-if="isLoading && documents.length === 0" class="text-center py-12 text-slate-600">
                <Loader2 class="w-8 h-8 animate-spin mx-auto mb-3 opacity-20" />
                <span class="text-sm">加载知识库...</span>
            </div>

            <div v-else-if="documents.length === 0" class="text-center py-12 border border-white/5 rounded-xl bg-black/10">
                <FileText class="w-12 h-12 text-slate-800 mx-auto mb-3" />
                <p class="text-sm text-slate-600">知识库为空</p>
            </div>

            <div v-else class="space-y-3">
                <div v-for="doc in documents" :key="doc.source" class="group relative bg-white/5 hover:bg-white/[0.08] border border-white/5 rounded-xl p-4 transition-all overflow-hidden">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-4 min-w-0 flex-1">
                            <div class="p-2 rounded-lg bg-accent/10 border border-accent/20 flex-shrink-0">
                                <FileText class="w-5 h-5 text-accent" />
                            </div>
                            <div class="min-w-0 flex-1">
                                <h3 class="text-sm font-bold text-slate-200 break-all">{{ doc.source }}</h3>
                                <p class="text-[10px] text-slate-500 uppercase font-bold tracking-widest mt-1">
                                    {{ doc.chunk_count }} 个知识切片
                                </p>
                            </div>
                        </div>
                        <div class="flex items-center gap-2 flex-shrink-0 ml-4">
                            <button @click="toggleContent(doc)" class="text-[10px] uppercase font-bold px-3 py-1 rounded-full bg-slate-800 text-slate-400 hover:text-accent transition-colors">
                                {{ doc.showContent ? '收起' : '详情' }}
                            </button>
                            <button @click="deleteDoc(doc.source)" class="p-2 text-slate-600 hover:text-red-400 transition-colors">
                                <Trash2 class="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                    
                    <div v-if="doc.showContent" class="mt-4 pt-4 border-t border-white/5 animate-in slide-in-from-top-2 duration-300">
                        <div class="max-h-60 overflow-y-auto overflow-x-hidden pr-2 custom-scrollbar text-xs leading-relaxed text-slate-400 whitespace-pre-wrap font-mono bg-black/20 p-4 rounded-lg">
                            {{ doc.chunks.map((c: any) => c.text).join('\n\n--- Next Chunk ---\n\n') }}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
/* Webkit (Chrome, Edge, Safari) */
.custom-scrollbar::-webkit-scrollbar { 
    width: 6px; 
}
.custom-scrollbar::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.02);
    border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb { 
    background: rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.05);
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: var(--accent, #6366f1);
}

/* Firefox */
.custom-scrollbar {
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 255, 255, 0.1) rgba(255, 255, 255, 0.02);
}
</style>
