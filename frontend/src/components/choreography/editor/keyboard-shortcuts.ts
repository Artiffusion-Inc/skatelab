"use client"

import { useChoreographyEditor } from "./store"
import { useMountEffect } from "@/lib/useMountEffect"

export function useKeyboardShortcuts() {
  const store = useChoreographyEditor()

  useMountEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement
      ) {
        return
      }

      switch (e.key) {
        case "Delete":
        case "Backspace":
          if (store.selectedElementId) {
            store.removeElement(store.selectedElementId)
          }
          break
        case " ":
          e.preventDefault()
          store.setIsPlaying(!store.isPlaying)
          break
        case "+":
        case "=":
          store.zoomIn()
          break
        case "-":
          store.zoomOut()
          break
        case "0":
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault()
            store.resetZoom()
          }
          break
      }
    }

    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  })
}
