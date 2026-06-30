import { useEffect } from "react"

/**
 * Run a callback once on mount. Cleanup function supported.
 * This is the ONLY allowed wrapper around useEffect in this project.
 */
export function useMountEffect(callback: () => undefined | (() => void)) {
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentionally mount-only
  useEffect(callback, [])
}

/**
 * Run a callback whenever `deps` change (mount + each dependency change).
 *
 * #470: a mount-only effect captures the value of a state variable at initial
 * mount and never re-runs — so a flag that flips AFTER mount (e.g.
 * `isAuthenticated` once the async `fetchMe()` resolves) is stale, and a
 * redirect guarded by `if (isAuthenticated) router.push(...)` never fires. This
 * wrapper keys the effect on the deps so the callback re-runs when they change.
 * Use it instead of `useMountEffect` when the effect must react to a value that
 * arrives after mount.
 */
export function useKeyedEffect(
  callback: () => undefined | (() => void),
  deps: ReadonlyArray<unknown>,
) {
  // biome-ignore lint/correctness/useExhaustiveDependencies: deps intentionally drive re-runs
  useEffect(callback, deps)
}
