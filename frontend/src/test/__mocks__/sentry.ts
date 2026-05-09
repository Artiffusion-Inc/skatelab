export const captureException = vi.fn()
export const captureMessage = vi.fn()
export const withScope = vi.fn((_, fn) => fn({ setExtra: vi.fn(), setTag: vi.fn() }))
export const init = vi.fn()
