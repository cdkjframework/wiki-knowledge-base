<script setup lang="ts">
/**
 * 服务商品牌 SVG 图标（本地资源，不依赖外网 CDN）。
 */
import { computed } from 'vue'

const props = defineProps<{
  providerId: string
  /** 传入时覆盖默认色 */
  color?: string
}>()

const id = computed(() => String(props.providerId || '').trim().toLowerCase())
</script>

<template>
  <svg
    class="prov-icon"
    viewBox="0 0 24 24"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <!-- OpenAI -->
    <g v-if="id === 'openai'" fill="currentColor">
      <path
        d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0l-4.83-2.786A4.504 4.504 0 0 1 2.34 7.872zm16.597 3.855l-5.833-3.387L15.119 7.2a.076.076 0 0 1 .071 0l4.83 2.787a4.494 4.494 0 0 1-.676 8.105v-5.678a.79.79 0 0 0-.407-.667zm2.01-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.83-2.787a4.5 4.5 0 0 1 6.68 4.66zM8.306 12.863l-2.02-1.163a.08.08 0 0 1-.038-.057V6.074c.0-2.48 2.016-4.5 4.494-4.494a4.46 4.46 0 0 1 2.876 1.04l-.141.08-4.778 2.758a.795.795 0 0 0-.393.681zm1.097-2.365L12 8.43l2.597 1.498v2.998L12 14.925l-2.597-1.498z"
      />
    </g>

    <!-- DeepSeek -->
    <g v-else-if="id === 'deepseek'" fill="currentColor">
      <path
        d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm0 2.5a7.5 7.5 0 0 1 7.5 7.5c0 1.85-.67 3.55-1.78 4.86L12 12.5l-5.72 4.36A7.47 7.47 0 0 1 4.5 12 7.5 7.5 0 0 1 12 4.5zm0 3.2a4.3 4.3 0 1 0 0 8.6 4.3 4.3 0 0 0 0-8.6z"
      />
    </g>

    <!-- Qwen / DashScope：六角星风格 -->
    <g v-else-if="id === 'qwen' || id === 'dashscope'" fill="currentColor">
      <path
        d="M12 2.2 14.4 8l6.4.5-4.9 4.1 1.5 6.2L12 15.7 6.6 18.8l1.5-6.2L3.2 8.5 9.6 8 12 2.2zm0 4.1L10.7 9.5l-3.5.3 2.7 2.2-.8 3.4L12 13.6l3 1.8-.8-3.4 2.7-2.2-3.5-.3L12 6.3z"
      />
    </g>

    <!-- Kimi / Moonshot -->
    <g v-else-if="id === 'kimi' || id === 'moonshot'" fill="currentColor">
      <path
        d="M4 4h4.2v7.1L14.8 4H20l-7.3 8.1L20.2 20h-5.3l-5.7-7.2V20H4V4z"
      />
    </g>

    <!-- Doubao -->
    <g v-else-if="id === 'doubao'" fill="currentColor">
      <path
        d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 3.2a3.4 3.4 0 0 1 3.4 3.4c0 1.7-1.1 2.9-2.5 3.8.9.4 1.9 1.1 2.5 2.2.7 1.3.6 2.8-.2 3.9A4.8 4.8 0 0 1 12 19.5a4.8 4.8 0 0 1-3.2-1.1c-.8-1.1-.9-2.6-.2-3.9.6-1.1 1.6-1.8 2.5-2.2-1.4-.9-2.5-2.1-2.5-3.8A3.4 3.4 0 0 1 12 5.2z"
      />
    </g>

    <!-- Gemini -->
    <g v-else-if="id === 'gemini'" fill="currentColor">
      <path
        d="M12 2c.4 4.8 2.7 7.1 7.5 7.5C14.7 9.9 12.4 12.2 12 17c-.4-4.8-2.7-7.1-7.5-7.5C9.3 9.1 11.6 6.8 12 2zm7.5 12.5c-.2 2.4-1.3 3.5-3.7 3.7 2.4.2 3.5 1.3 3.7 3.7.2-2.4 1.3-3.5 3.7-3.7-2.4-.2-3.5-1.3-3.7-3.7z"
      />
    </g>

    <!-- Grok / xAI -->
    <g v-else-if="id === 'xai'" fill="currentColor">
      <path
        d="M3.5 3.5h4.2L12 10.1 16.3 3.5h4.2L13.9 12l7 8.5h-4.3L12 13.9 7.4 20.5H3.1L10.1 12 3.5 3.5z"
      />
    </g>

    <!-- Hugging Face：简化脸标 -->
    <g v-else-if="id === 'huggingface'" fill="currentColor">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6" />
      <circle cx="9" cy="10.5" r="1.2" />
      <circle cx="15" cy="10.5" r="1.2" />
      <path
        d="M8.2 14.2c1.1 1.5 2.4 2.2 3.8 2.2s2.7-.7 3.8-2.2"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
      />
    </g>

    <!-- Ollama：驼峰简标 -->
    <g v-else-if="id === 'ollama'" fill="currentColor">
      <path
        d="M6.5 15.5c0-4.2 2.5-7.5 5.5-7.5s5.5 3.3 5.5 7.5c0 1.2-.3 2.3-.8 3.2H7.3c-.5-.9-.8-2-.8-3.2z"
      />
      <circle cx="9.6" cy="13.2" r="1.1" fill="#fff" />
      <circle cx="14.4" cy="13.2" r="1.1" fill="#fff" />
      <path d="M8 8.2c.8-1.6 2-2.6 4-2.6s3.2 1 4 2.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
    </g>

    <!-- LM Studio -->
    <g v-else-if="id === 'lm_studio'" fill="currentColor">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6" />
      <path d="M7 15.5V8.5h2.2c1.5 0 2.4.8 2.4 2.1s-.9 2.1-2.4 2.1H7zm2-2.8c.6 0 1-.3 1-.9s-.4-.9-1-.9H8.6v1.8H9zM13.2 15.5V8.5h1.6v5.4h3.2v1.6h-4.8z" />
    </g>

    <!-- 兜底：几何标 -->
    <g v-else fill="currentColor">
      <rect x="4" y="4" width="16" height="16" rx="4" opacity="0.2" />
      <path d="M8 12h8M12 8v8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
    </g>
  </svg>
</template>

<style scoped>
.prov-icon {
  width: 60%;
  height: 60%;
  display: block;
}
</style>
