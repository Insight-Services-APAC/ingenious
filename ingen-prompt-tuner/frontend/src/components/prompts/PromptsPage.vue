<script setup lang="ts">
  /**
   * PromptsPage component for managing prompt revisions and files.
   * Provides revision selection, creation, and prompt editing interface.
   */
  import { onMounted, ref } from 'vue'
  import { useRevisionsStore } from '@/stores/revisions'
  import { useEditorStore } from '@/stores/editor'
  import Button from '@/components/common/Button.vue'
  import PromptCard from './PromptCard.vue'
  import EditorPanel from './EditorPanel.vue'

  const revisionsStore = useRevisionsStore()
  const editorStore = useEditorStore()

  // Modal state for creating revision
  const showCreateModal = ref(false)
  const newRevisionName = ref('')
  const copyPrompts = ref(true)

  onMounted(async () => {
    await revisionsStore.fetchRevisions()
    if (revisionsStore.activeRevision) {
      await revisionsStore.fetchPrompts()
    }
  })

  /**
   * Handles revision dropdown selection changes.
   * @param event - The change event from the select element.
   */
  function handleRevisionChange(event: Event) {
    const target = event.target as HTMLSelectElement
    revisionsStore.setActiveRevision(target.value)
    editorStore.clearSelection()
  }

  /**
   * Opens the create revision modal with default values.
   */
  function openCreateModal() {
    newRevisionName.value = ''
    copyPrompts.value = true
    showCreateModal.value = true
  }

  /**
   * Closes the create revision modal.
   */
  function closeCreateModal() {
    showCreateModal.value = false
  }

  /**
   * Creates a new revision with the specified name.
   */
  async function handleCreateRevision() {
    if (!newRevisionName.value.trim()) return

    try {
      await revisionsStore.createRevision(
        newRevisionName.value.trim(),
        copyPrompts.value ? revisionsStore.activeRevision : undefined
      )
      closeCreateModal()
    } catch {
      alert('Failed to create revision. Name may already exist.')
    }
  }
</script>

<template>
  <div>
    <div class="flex h-[calc(100vh-120px)] gap-6">
      <!-- Left Sidebar -->
      <aside class="w-72 flex-shrink-0 flex flex-col bg-white rounded-lg border border-gray-200">
        <!-- Sidebar Header -->
        <div class="p-4 border-b border-gray-200">
          <label class="block text-xs font-medium text-taupe mb-1.5 uppercase tracking-wide"
            >Revision</label
          >
          <select
            :value="revisionsStore.activeRevision"
            class="w-full px-3 py-2 bg-desert border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-shiraz/20 focus:border-shiraz"
            @change="handleRevisionChange"
          >
            <option
              v-for="revision in revisionsStore.revisions"
              :key="revision.id"
              :value="revision.id"
            >
              {{ revision.name }}
            </option>
          </select>
        </div>

        <!-- Scrollable Agent List -->
        <div class="flex-1 overflow-y-auto p-2">
          <PromptCard
            v-for="prompt in revisionsStore.prompts"
            :key="prompt.filename"
            :prompt="prompt"
            :selected="editorStore.selectedPrompt?.filename === prompt.filename"
            @click="editorStore.selectPrompt(prompt)"
          />
        </div>

        <!-- Sidebar Footer -->
        <div class="p-4 border-t border-gray-200">
          <Button class="w-full" size="sm" @click="openCreateModal">New Revision</Button>
        </div>
      </aside>

      <!-- Right Editor Panel -->
      <main class="flex-1 min-w-0">
        <EditorPanel v-if="editorStore.selectedPrompt" class="h-full" />
        <div
          v-else
          class="h-full bg-white rounded-lg border border-gray-200 flex items-center justify-center"
        >
          <div class="text-center">
            <p class="text-taupe text-sm">Select a prompt to edit</p>
          </div>
        </div>
      </main>
    </div>

    <!-- Create Revision Modal -->
    <div
      v-if="showCreateModal"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="closeCreateModal"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-mine mb-4">Create New Revision</h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-taupe mb-1">Revision Name</label>
            <input
              v-model="newRevisionName"
              type="text"
              placeholder="e.g., v2-experiment"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-shiraz/20 focus:border-shiraz"
              @keyup.enter="handleCreateRevision"
            />
            <p class="text-xs text-taupe mt-1">Use alphanumeric characters and hyphens only</p>
          </div>

          <div class="flex items-center gap-2">
            <input
              id="copyPrompts"
              v-model="copyPrompts"
              type="checkbox"
              class="w-4 h-4 text-shiraz border-gray-300 rounded focus:ring-shiraz"
            />
            <label for="copyPrompts" class="text-sm text-mine">
              Copy prompts from current revision ({{ revisionsStore.activeRevision }})
            </label>
          </div>
        </div>

        <div class="flex justify-end gap-2 mt-6">
          <Button variant="secondary" @click="closeCreateModal">Cancel</Button>
          <Button :disabled="!newRevisionName.trim()" @click="handleCreateRevision">Create</Button>
        </div>
      </div>
    </div>
  </div>
</template>
