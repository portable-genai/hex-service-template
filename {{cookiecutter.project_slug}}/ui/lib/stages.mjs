/**
 * The rules behind the console's stage stack, as plain functions.
 *
 * They live here rather than inside `components/StageStack.tsx` so the gate can test the
 * DECISIONS without a browser or a React renderer: which stage is in focus, and whether a
 * stage is still being driven automatically. Both are the parts that go quietly wrong —
 * a stage stack whose rules are only exercised through rendering is one whose rules are
 * only exercised when somebody looks.
 *
 * `lib/csp.mjs` is the precedent: real logic in `.mjs`, imported by both the TypeScript
 * that uses it and the test that pins it, so the test cannot mirror an implementation and
 * then drift from it.
 */

/**
 * The stage that should be open: the last one that has something to show.
 *
 * Expressed as a rule over readiness rather than a hard-coded name so adding a stage later
 * needs no new branch. Before anything is ready, the first stage is the focus — an empty
 * console should be showing its input, not nothing.
 *
 * @param {ReadonlyArray<{id: string, ready: boolean}>} stages in display order
 * @returns {string} the id of the stage to open, or "" when there are no stages
 */
export function activeStage(stages) {
  if (!Array.isArray(stages) || stages.length === 0) return "";
  let active = "";
  for (const stage of stages) {
    if (stage && stage.ready) active = stage.id;
  }
  return active || stages[0].id;
}

/**
 * Whether `active` still drives this stage, or the reader has taken it over.
 *
 * The rule is deliberately one-way: taking over is permanent for the session. A stage that
 * resumed being driven after some later event would slam shut under a reader who had
 * opened it on purpose, and that is the single most common way this pattern is got wrong.
 *
 * @param {string} id
 * @param {ReadonlySet<string>} taken
 * @returns {boolean} true when the stage stack should still set this stage's openness
 */
export function isDriven(id, taken) {
  return !taken.has(id);
}

/**
 * Add a stage to the taken-over set, preserving referential identity when it is already in.
 *
 * Returning the SAME set when nothing changed is what stops a React state update, and with
 * it a re-render, on every toggle of an already-taken stage.
 *
 * @param {ReadonlySet<string>} taken
 * @param {string} id
 * @returns {Set<string>|ReadonlySet<string>}
 */
export function withTakeover(taken, id) {
  if (taken.has(id)) return taken;
  return new Set(taken).add(id);
}
