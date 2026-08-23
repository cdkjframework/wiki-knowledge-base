<script setup lang="ts">
/**
 * 登录页占位（鉴权能力后续接入）。
 */
import { useRouter } from 'vue-router'

const router = useRouter()

function enterApp() {
  router.push('/retrieval-qa')
}
</script>

<template>
  <div class="page-card" style="max-width: 420px; margin: 12vh auto">
    <h2>登录</h2>
    <p>当前为本地开发占位，点击进入应用主界面。</p>
    <el-button type="primary" style="margin-top: 16px" @click="enterApp">进入控制台</el-button>
  </div>
</template>
