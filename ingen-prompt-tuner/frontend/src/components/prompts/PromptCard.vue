<script setup lang="ts">
  /**
   * PromptCard component for displaying a prompt file summary.
   * Shows filename, description, size, and tags in a clickable card.
   */
  import type { Prompt } from '@/types'

  defineProps<{
    prompt: Prompt
    selected: boolean
  }>()

  defineEmits<{
    click: []
  }>()

  /**
   * Formats file size in bytes to a human-readable string.
   * @param bytes - The file size in bytes.
   * @returns Formatted size string (e.g., "1.5 KB").
   */
  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    return `${(bytes / 1024).toFixed(1)} KB`
  }
</script>

<template>
  <div
    :class="[
      'px-3 py-2.5 rounded-md cursor-pointer transition-all mb-1 border-l-2',
      selected ? 'bg-shiraz/10 border-shiraz' : 'hover:bg-desert border-transparent',
    ]"
    @click="$emit('click')"
  >
    <p class="text-sm font-medium text-mine truncate">
      {{ prompt.filename }}
    </p>
    <p v-if="prompt.description" class="text-xs text-taupe truncate mt-0.5">
      {{ prompt.description }}
    </p>
    <div v-if="prompt.tags && prompt.tags.length > 0" class="flex items-center gap-1 mt-1.5">
      <span
        v-for="tag in prompt.tags.slice(0, 2)"
        :key="tag"
        class="px-1.5 py-0.5 text-[10px] bg-desert text-taupe rounded"
      >
        {{ tag }}
      </span>
      <span v-if="prompt.tags.length > 2" class="text-[10px] text-taupe">
        +{{ prompt.tags.length - 2 }}
      </span>
    </div>
  </div>
</template>
