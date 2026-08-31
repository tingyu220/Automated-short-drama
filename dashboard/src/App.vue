<script setup lang="ts">
import AppLayout from "@/app/layouts/AppLayout.vue"
import ErrorBoundary from "@/shared/ui/ErrorBoundary.vue"
</script>

<template>
  <ErrorBoundary>
    <AppLayout />
  </ErrorBoundary>
</template>
