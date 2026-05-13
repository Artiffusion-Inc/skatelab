import { describe, expect, it, beforeEach } from "vitest"
import { useChoreographyEditor } from "../store"

beforeEach(() => {
  useChoreographyEditor.setState({
    programId: null,
    title: "",
    discipline: "mens_singles",
    segment: "free_skate",
    musicAnalysisId: null,
    audioUrl: null,
    musicDuration: 180,
    beatMarkers: [],
    phraseMarkers: [],
    elements: [],
    selectedElementId: null,
    currentTime: 0,
    isPlaying: false,
    pixelsPerSecond: 15,
    snapMode: "beats",
    editorBpm: 0,
    rinkPreset: "olympic",
    rinkWidth: 60,
    rinkHeight: 30,
    isLoading: false,
  })
})

describe("addElement", () => {
  it("creates an element with correct trackType", () => {
    useChoreographyEditor.getState().addElement("jumps", 10, "3Lz")
    const els = useChoreographyEditor.getState().elements
    expect(els).toHaveLength(1)
    expect(els[0].code).toBe("3Lz")
    expect(els[0].trackType).toBe("jumps")
    expect(els[0].timestamp).toBe(10)
    expect(els[0].duration).toBe(3)
  })

  it("selects newly added element", () => {
    useChoreographyEditor.getState().addElement("spins", 20, "CSp4")
    expect(useChoreographyEditor.getState().selectedElementId).toBe(
      useChoreographyEditor.getState().elements[0].id,
    )
  })
})

describe("removeElement", () => {
  it("removes element by id and clears selection", () => {
    useChoreographyEditor.getState().addElement("jumps", 10, "3Lz")
    const id = useChoreographyEditor.getState().elements[0].id
    useChoreographyEditor.getState().setSelectedElement(id)
    useChoreographyEditor.getState().removeElement(id)
    expect(useChoreographyEditor.getState().elements).toHaveLength(0)
    expect(useChoreographyEditor.getState().selectedElementId).toBeNull()
  })
})

describe("moveElement", () => {
  it("updates timestamp", () => {
    useChoreographyEditor.getState().addElement("jumps", 10, "3Lz")
    const id = useChoreographyEditor.getState().elements[0].id
    useChoreographyEditor.getState().moveElement(id, 45)
    expect(useChoreographyEditor.getState().elements[0].timestamp).toBe(45)
  })

  it("clamps negative timestamps to 0", () => {
    useChoreographyEditor.getState().addElement("jumps", 10, "3Lz")
    const id = useChoreographyEditor.getState().elements[0].id
    useChoreographyEditor.getState().moveElement(id, -5)
    expect(useChoreographyEditor.getState().elements[0].timestamp).toBe(0)
  })
})

describe("resizeElement", () => {
  it("updates duration", () => {
    useChoreographyEditor.getState().addElement("jumps", 10, "3Lz")
    const id = useChoreographyEditor.getState().elements[0].id
    useChoreographyEditor.getState().resizeElement(id, 8)
    expect(useChoreographyEditor.getState().elements[0].duration).toBe(8)
  })

  it("clamps duration to minimum 1", () => {
    useChoreographyEditor.getState().addElement("jumps", 10, "3Lz")
    const id = useChoreographyEditor.getState().elements[0].id
    useChoreographyEditor.getState().resizeElement(id, 0)
    expect(useChoreographyEditor.getState().elements[0].duration).toBe(1)
  })
})

describe("duplicateElement", () => {
  it("creates copy with new id", () => {
    useChoreographyEditor.getState().addElement("jumps", 10, "3Lz")
    const original = useChoreographyEditor.getState().elements[0]
    useChoreographyEditor.getState().duplicateElement(original.id)
    const els = useChoreographyEditor.getState().elements
    expect(els).toHaveLength(2)
    expect(els[1].code).toBe("3Lz")
    expect(els[1].id).not.toBe(original.id)
    expect(els[1].timestamp).toBe(original.timestamp + 2)
  })
})

describe("updateElement", () => {
  it("patches element fields", () => {
    useChoreographyEditor.getState().addElement("jumps", 10, "3Lz")
    const id = useChoreographyEditor.getState().elements[0].id
    useChoreographyEditor.getState().updateElement(id, { goe: 2 })
    expect(useChoreographyEditor.getState().elements[0].goe).toBe(2)
  })
})

describe("updateElementPosition", () => {
  it("sets x and y", () => {
    useChoreographyEditor.getState().addElement("jumps", 10, "3Lz")
    const id = useChoreographyEditor.getState().elements[0].id
    useChoreographyEditor.getState().updateElementPosition(id, 15, 25)
    expect(useChoreographyEditor.getState().elements[0].position).toEqual({ x: 15, y: 25 })
  })
})

describe("getLayoutForSave", () => {
  it("returns LayoutElement array with jump flags", () => {
    useChoreographyEditor.getState().addElement("jumps", 10, "3Lz")
    useChoreographyEditor.getState().addElement("spins", 20, "CSp4")
    const layout = useChoreographyEditor.getState().getLayoutForSave()
    expect(layout.layout).toHaveLength(2)
    expect(layout.layout[0].is_jump_pass).toBe(true)
    expect(layout.layout[1].is_jump_pass).toBe(false)
  })
})

describe("zoom", () => {
  it("zoomIn increases pixelsPerSecond", () => {
    useChoreographyEditor.getState().zoomIn()
    expect(useChoreographyEditor.getState().pixelsPerSecond).toBeGreaterThan(15)
  })

  it("zoomOut decreases pixelsPerSecond", () => {
    useChoreographyEditor.getState().zoomOut()
    expect(useChoreographyEditor.getState().pixelsPerSecond).toBeLessThan(15)
  })

  it("resetZoom restores default", () => {
    useChoreographyEditor.getState().zoomIn()
    useChoreographyEditor.getState().resetZoom()
    expect(useChoreographyEditor.getState().pixelsPerSecond).toBe(15)
  })
})
