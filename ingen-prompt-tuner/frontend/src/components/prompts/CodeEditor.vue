<script setup lang="ts">
  import { ref, onMounted, onUnmounted, watch, shallowRef } from 'vue'
  import { EditorState } from '@codemirror/state'
  import {
    EditorView,
    keymap,
    lineNumbers,
    highlightActiveLine,
    highlightActiveLineGutter,
  } from '@codemirror/view'
  import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
  import { HighlightStyle, syntaxHighlighting, StreamLanguage } from '@codemirror/language'
  import { oneDark } from '@codemirror/theme-one-dark'
  import { tags } from '@lezer/highlight'

  const props = defineProps<{
    modelValue: string
  }>()

  const emit = defineEmits<{
    (e: 'update:modelValue', value: string): void
  }>()

  const container = ref<HTMLElement | null>(null)
  const view = shallowRef<EditorView | null>(null)

  // Custom Jinja2 highlighting
  const jinjaLanguage = StreamLanguage.define({
    token(stream) {
      // Jinja block: {% ... %}
      if (stream.match(/\{%/)) {
        stream.eatWhile(/[^%]/)
        if (stream.match(/%}/)) {
          return 'keyword'
        }
        return 'keyword'
      }
      // Jinja variable: {{ ... }}
      if (stream.match(/\{\{/)) {
        stream.eatWhile(/[^}]/)
        if (stream.match(/}}/)) {
          return 'variableName'
        }
        return 'variableName'
      }
      // Jinja comment: {# ... #}
      if (stream.match(/\{#/)) {
        stream.eatWhile(/[^#]/)
        if (stream.match(/#}/)) {
          return 'comment'
        }
        return 'comment'
      }
      // Skip to next Jinja syntax
      if (stream.skipTo('{')) {
        return null
      }
      stream.skipToEnd()
      return null
    },
  })

  // Custom highlighting for Jinja
  const jinjaHighlighting = HighlightStyle.define([
    { tag: tags.keyword, color: '#c792ea' },
    { tag: tags.variableName, color: '#ffcb6b' },
    { tag: tags.comment, color: '#546e7a', fontStyle: 'italic' },
  ])

  onMounted(() => {
    if (!container.value) return

    const startState = EditorState.create({
      doc: props.modelValue,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        highlightActiveLineGutter(),
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        jinjaLanguage,
        syntaxHighlighting(jinjaHighlighting),
        oneDark,
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            emit('update:modelValue', update.state.doc.toString())
          }
        }),
        EditorView.theme({
          '&': {
            height: '100%',
            fontSize: '14px',
          },
          '.cm-scroller': {
            overflow: 'auto',
            fontFamily:
              'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace',
          },
          '.cm-content': {
            padding: '12px 0',
          },
          '.cm-line': {
            padding: '0 16px',
          },
          '.cm-gutters': {
            backgroundColor: '#21252b',
            borderRight: '1px solid #181a1f',
          },
          '.cm-activeLineGutter': {
            backgroundColor: '#2c313c',
          },
        }),
      ],
    })

    view.value = new EditorView({
      state: startState,
      parent: container.value,
    })
  })

  watch(
    () => props.modelValue,
    (newValue) => {
      if (!view.value) return
      const currentValue = view.value.state.doc.toString()
      if (newValue !== currentValue) {
        view.value.dispatch({
          changes: {
            from: 0,
            to: currentValue.length,
            insert: newValue,
          },
        })
      }
    }
  )

  onUnmounted(() => {
    if (view.value) {
      view.value.destroy()
      view.value = null
    }
  })
</script>

<template>
  <div ref="container" class="code-editor-container" />
</template>

<style scoped>
  .code-editor-container {
    height: 100%;
    border-radius: 0.375rem;
    overflow: hidden;
  }

  .code-editor-container :deep(.cm-editor) {
    height: 100%;
    border-radius: 0.375rem;
  }

  .code-editor-container :deep(.cm-scroller) {
    height: 100%;
  }

  .code-editor-container :deep(.cm-focused) {
    outline: none;
  }
</style>
