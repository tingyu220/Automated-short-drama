<script setup lang="ts">
import { ref, onErrorCaptured } from "vue"
import ErrorState from "./ErrorState.vue"

const error = ref<Error | null>(null)

onErrorCaptured((err: unknown) => {
  error.value = err as Error
  return false
})

function reset() {
  error.value = null
}
</script>

<template>
  <ErrorState
    v-if="error"
    :message="error.message"
    retry-text="重试"
    @retry="reset"
  />
  <slot v-else />
</template>
