<script setup lang="ts">
  /**
   * EditorPanel component for editing prompt content.
   * Provides a code editor with save, discard, and export functionality.
   */
  import { useEditorStore } from '@/stores/editor'
  import { useRevisionsStore } from '@/stores/revisions'
  import { promptsService } from '@/services/prompts.service'
  import Button from '@/components/common/Button.vue'
  import CodeEditor from './CodeEditor.vue'

  const editorStore = useEditorStore()
  const revisionsStore = useRevisionsStore()

  /**
   * Saves the current prompt content to the backend.
   */
  async function handleSave() {
    if (editorStore.selectedPrompt && editorStore.modifiedContent) {
      await promptsService.update(
        revisionsStore.activeRevision,
        editorStore.selectedPrompt.filename,
        editorStore.modifiedContent
      )
    }
  }

  /**
   * Handles content changes from the code editor.
   * @param value - The new content value.
   */
  function handleEditorChange(value: string) {
    editorStore.updateContent(value)
  }

  /**
   * Exports the current prompt content as a downloadable file.
   */
  function handleExport() {
    if (!editorStore.selectedPrompt) return

    const content = editorStore.modifiedContent || ''
    const filename = editorStore.selectedPrompt.filename
    const blob = new Blob([content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }
</script>

<template>
  <div
    v-if="editorStore.selectedPrompt"
    class="bg-white rounded-lg border border-gray-200 flex flex-col h-full overflow-hidden"
  >
    <!-- Header -->
    <div class="flex items-center justify-between px-5 py-3 border-b border-gray-200 flex-shrink-0">
      <div class="flex items-center gap-3">
        <span class="text-sm font-medium text-mine">{{ editorStore.selectedPrompt.filename }}</span>
        <span class="text-xs text-taupe">Last modified 2 hours ago</span>
      </div>
      <div class="flex items-center gap-2">
        <Button size="sm" variant="secondary" @click="handleExport"> Export </Button>
        <Button
          size="sm"
          variant="secondary"
          :disabled="!editorStore.hasChanges"
          @click="editorStore.discardChanges()"
        >
          Discard
        </Button>
        <Button size="sm" :disabled="!editorStore.hasChanges" @click="handleSave"> Save </Button>
      </div>
    </div>

    <!-- Editor (fills remaining space) -->
    <div class="flex-1 min-h-0">
      <CodeEditor
        class="h-full"
        :model-value="editorStore.modifiedContent || ''"
        @update:model-value="handleEditorChange"
      />
    </div>

    <!-- Footer -->
    <div class="px-5 py-3 border-t border-gray-200 flex items-center gap-2 flex-wrap flex-shrink-0">
      <span class="text-xs text-taupe">Variables:</span>
      <span
        v-for="variable in editorStore.extractedVariables"
        :key="variable"
        class="px-2 py-0.5 text-xs rounded font-mono bg-yellow-100 text-yellow-800"
      >
        {{ variable }}
      </span>
      <span v-if="editorStore.extractedVariables.length === 0" class="text-xs text-taupe italic">
        No variables detected
      </span>
    </div>
  </div>
</template>
