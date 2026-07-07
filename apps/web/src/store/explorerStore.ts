import { create } from 'zustand'

interface ExplorerState {
  selectedVid: string | null
  expandedVids: Set<string>
  hiddenTags: Set<string>
  hiddenEdgeTypes: Set<string>
  select: (vid: string | null) => void
  markExpanded: (vid: string) => void
  markCollapsed: (vid: string) => void
  toggleTag: (tag: string) => void
  toggleEdgeType: (edgeType: string) => void
  reset: () => void
}

export const useExplorerStore = create<ExplorerState>((set) => ({
  selectedVid: null,
  expandedVids: new Set(),
  hiddenTags: new Set(),
  hiddenEdgeTypes: new Set(),

  select: (vid) => set({ selectedVid: vid }),

  markExpanded: (vid) =>
    set((state) => ({ expandedVids: new Set(state.expandedVids).add(vid) })),

  markCollapsed: (vid) =>
    set((state) => {
      const next = new Set(state.expandedVids)
      next.delete(vid)
      return { expandedVids: next }
    }),

  toggleTag: (tag) =>
    set((state) => {
      const next = new Set(state.hiddenTags)
      if (next.has(tag)) next.delete(tag)
      else next.add(tag)
      return { hiddenTags: next }
    }),

  toggleEdgeType: (edgeType) =>
    set((state) => {
      const next = new Set(state.hiddenEdgeTypes)
      if (next.has(edgeType)) next.delete(edgeType)
      else next.add(edgeType)
      return { hiddenEdgeTypes: next }
    }),

  reset: () =>
    set({
      selectedVid: null,
      expandedVids: new Set(),
      hiddenTags: new Set(),
      hiddenEdgeTypes: new Set(),
    }),
}))
