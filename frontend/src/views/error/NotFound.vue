<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <section class="page-card" style="max-width: 480px; margin: 12vh auto; text-align: center">
    <h2>页面不存在</h2>
    <p>请从侧栏进入功能页。</p>
    <el-button type="primary" style="margin-top: 16px" @click="router.push('/retrieval-qa')">
      返回检索问答
    </el-button>
  </section>
</template>
