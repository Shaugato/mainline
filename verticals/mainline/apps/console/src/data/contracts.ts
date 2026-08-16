// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The contract registry: every `contracts/*.schema.json` file, loaded as TEXT and
 * parsed at runtime.
 *
 * Two properties are deliberate.
 *
 * **They are imported with `?raw`, not as JSON modules.** A JSON module import makes
 * TypeScript infer a literal type for every string in a 12 KB schema, which costs
 * minutes of `tsc` across every file in `contracts/` and buys nothing — the schemas are
 * consumed as data by the validator, never as types by a call site. The types the
 * console actually uses come from `types.generated.ts`, which is generated from these
 * same files by `scripts/gen-types.ts`.
 *
 * **The imports are explicit, one per line, rather than an `import.meta.glob`.** A glob
 * would silently drop a contract that was renamed or deleted, and the first symptom
 * would be a `$ref` failing to resolve at runtime in front of a judge. An explicit list
 * turns the same mistake into a build error.
 *
 * TWO of these documents are VERBATIM copies of a file this workspace may not import,
 * and both are pinned the same way — `tests/unit/data/contracts.test.ts` compares copy
 * and original JSON-pointer by JSON-pointer, in BOTH directions, so a field added,
 * removed or retyped upstream fails the console's own suite by name on the next run:
 *
 *   * `refusal.schema.json` ← `spec/wire/refusal.schema.json`. The specification owns it.
 *   * `gate-run.schema.json` ← `verticals/mainline/apps/demo-api/contracts/gate-run.schema.json`.
 *     The demo API owns it, serves `POST /v1/demo/gate-run` against it, and repeats its
 *     `$id` inside the payload; the console validates the response before rendering it,
 *     so the two must be the same document or the demo's front door refuses its own
 *     answer.
 *
 * Never edit either copy here. Edit the original, then re-copy byte for byte — the
 * drift tests are structural, so a reformat passes them and still makes the two files
 * disagree about what a reader is looking at.
 *
 * A THIRD document joined them on 2026-08-15, on exactly the same terms:
 *
 *   * `subjects.schema.json` ← `verticals/mainline/apps/demo-api/contracts/subjects.schema.json`.
 *     It governs `GET /v1/demo/subjects`, the read that tells the console which subjects a
 *     deployment actually seeded (`src/data/demo-subjects.ts`) — the read that exists so
 *     that no surface has to carry an identifier of its own. The demo API owns the route,
 *     emits the payload from `subjects.py`, and therefore owns the contract; this is the
 *     copy, and it is checked against the original the same way the two above are.
 *
 * And a FOURTH on 2026-08-16, on the same terms again:
 *
 *   * `cr-gate-run.schema.json` ← `verticals/mainline/apps/demo-api/contracts/cr-gate-run.schema.json`.
 *     It governs `POST /v1/demo/cr-gate-run`, the SECOND gated subject's run: the permit
 *     gate run shows that a permit cannot be ISSUED while an obligation raised by blame is
 *     open, and this one shows the mirror — that the clause under blame cannot quietly be
 *     EDITED AWAY either. `cr_gate_run.py` repeats this document's `$id` inside its own
 *     payload, exactly as `gate_run.py` does, so the same drift argument applies verbatim.
 *
 *     It is a SEPARATE document from `gate-run.schema.json` rather than one widened to
 *     admit both, because the two runs' beats differ in kind — this one has no admitted
 *     beat and declares that absence with the grant rows behind it — and a schema admitting
 *     both would assert neither.
 *
 * ════════════════════════════════════════════════════════════════════════════════════
 * WHY THE FOURTH IS LOADED ON DEMAND AND THE OTHER NINETEEN ARE NOT — a measurement
 * ════════════════════════════════════════════════════════════════════════════════════
 *
 * `src/app/composition.tsx` imports `contractRegistry` statically, so every string in
 * `CONTRACT_SOURCES` is inlined verbatim into the console's ENTRY chunk. That is the right
 * trade for nineteen documents the console validates payloads against on the read path. It
 * is the wrong trade for this one, and the numbers are not close.
 *
 * Measured on this workstation, 2026-08-16, `vite build` before and after adding the entry:
 *
 *     entry chunk `assets/index-*.js`, gzipped     138,278 B  →  145,594 B   (+7,316)
 *     static_site.DEFAULT_MAX_RESPONSE_BYTES                     139,264 B
 *
 * The ceiling is not a style guide. An entry chunk above it means the origin answers **413
 * to every browser on earth** for the one object no human types: `GET /` still returns 200
 * and the shell, the shell asks for its module, receives a JSON problem document, and a
 * judge is looking at a blank page while the health check reports fine. `DEFAULT_MAX_RESPONSE_BYTES`
 * may not move — it has already been loosened twice to fit the tree it is supposed to bound.
 *
 * And the console entry does not read this route. `POST /v1/demo/cr-gate-run` is driven by
 * the OPERATOR entry (`src/operator/change/**`), which is a separate HTML entry, shares no
 * module with the console, and deliberately carries no runtime validator at all.
 *
 * So the document is declared HERE, by name, in an explicit import line that is not a glob,
 * and it is registered — but its bytes are fetched when somebody asks for them rather than
 * carried by every page load. Everything the eager entries get, this one gets:
 *
 *   * `contractRegistryFull()` compiles it exactly as `contractRegistry()` compiles the
 *     others, so an unimplemented keyword or a dangling `$ref` still fails loudly;
 *   * `tests/unit/data/contracts.test.ts` pins it against the demo API's original, byte for
 *     byte AND pointer by pointer in both directions, on the same terms as the other three;
 *   * a renamed or deleted file is still a BUILD error, because the import names the path.
 *
 * What it does not get is a place in the entry closure. That is the whole of the change.
 */

import ancestryRaw from '../../contracts/ancestry.schema.json?raw';
import auditRaw from '../../contracts/audit.schema.json?raw';
import blockingCheckRaw from '../../contracts/blocking-check.schema.json?raw';
import bundleRaw from '../../contracts/bundle.schema.json?raw';
import changeRequestRaw from '../../contracts/change-request.schema.json?raw';
import clauseRaw from '../../contracts/clause.schema.json?raw';
import commonRaw from '../../contracts/common.schema.json?raw';
import dispositionRaw from '../../contracts/disposition.schema.json?raw';
import envelopeRaw from '../../contracts/envelope.schema.json?raw';
import exposureRaw from '../../contracts/exposure.schema.json?raw';
import gateRunRaw from '../../contracts/gate-run.schema.json?raw';
import invokeRaw from '../../contracts/invoke.schema.json?raw';
import ledgerRaw from '../../contracts/ledger.schema.json?raw';
import permitRaw from '../../contracts/permit.schema.json?raw';
import propagationRaw from '../../contracts/propagation.schema.json?raw';
import recallRunRaw from '../../contracts/recall-run.schema.json?raw';
import refusalRaw from '../../contracts/refusal.schema.json?raw';
import silenceRaw from '../../contracts/silence.schema.json?raw';
import subjectsRaw from '../../contracts/subjects.schema.json?raw';

import type { SchemaDocument } from './schema';
import { SchemaRegistry } from './schema';

/**
 * File name → source text. The key is the file name because that is what a `$ref` like
 * `common.schema.json#/$defs/uuid` names, and because it is what a human greps for.
 */
export const CONTRACT_SOURCES: readonly (readonly [string, string])[] = Object.freeze([
  ['ancestry.schema.json', ancestryRaw],
  ['audit.schema.json', auditRaw],
  ['blocking-check.schema.json', blockingCheckRaw],
  ['bundle.schema.json', bundleRaw],
  ['change-request.schema.json', changeRequestRaw],
  ['clause.schema.json', clauseRaw],
  ['common.schema.json', commonRaw],
  ['disposition.schema.json', dispositionRaw],
  ['envelope.schema.json', envelopeRaw],
  ['exposure.schema.json', exposureRaw],
  ['gate-run.schema.json', gateRunRaw],
  ['invoke.schema.json', invokeRaw],
  ['ledger.schema.json', ledgerRaw],
  ['permit.schema.json', permitRaw],
  ['propagation.schema.json', propagationRaw],
  ['recall-run.schema.json', recallRunRaw],
  ['refusal.schema.json', refusalRaw],
  ['silence.schema.json', silenceRaw],
  ['subjects.schema.json', subjectsRaw],
] as const);

/**
 * Contracts registered by NAME here and fetched when asked for. See the note above.
 *
 * The loader is an explicit `import()` of a literal path — not a glob, and not a name
 * assembled at runtime — so the bundler resolves it at build time and a file renamed or
 * deleted is still a build error rather than a `$ref` that fails in front of a judge.
 */
export const DEFERRED_CONTRACT_SOURCES: readonly (readonly [
  string,
  () => Promise<string>,
])[] = Object.freeze([
  [
    'cr-gate-run.schema.json',
    async (): Promise<string> =>
      (await import('../../contracts/cr-gate-run.schema.json?raw')).default,
  ],
] as const);

/** The `$id` of the specification-owned refusal contract, carried here verbatim. */
export const REFUSAL_SCHEMA_ID = 'https://spec.trappoint.org/1.0/wire/refusal.schema.json';

/** The `$id` prefix every console-owned contract uses. */
export const CONTRACT_ID_PREFIX = 'https://console.mainline.trappoint.org/contracts/1.0/';

let cached: SchemaRegistry | null = null;

/**
 * Builds the registry and COMPILES every document, which refuses any keyword this
 * validator does not implement and resolves every `$ref`.
 *
 * Compilation is not an optimisation. A contract carrying an unimplemented keyword
 * would otherwise validate vacuously, and a conformance suite over vacuous contracts
 * is the exact failure PL-2 exists to prevent — so the cost is paid at startup, once,
 * and loudly.
 */
function build(sources: readonly (readonly [string, string])[]): SchemaRegistry {
  const registry = new SchemaRegistry();
  for (const [name, source] of sources) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(source);
    } catch (error) {
      // `cause` is not decoration here, and it is not interchangeable with the
      // interpolation beside it. `String(error)` stringifies a SyntaxError down to one
      // line and throws away the object: the stack that names the parse site, and
      // whatever a future JSON parser attaches (V8 already carries a byte offset that
      // `String()` renders only as prose). This throw happens once, at startup, before
      // any surface exists to report it — so the browser's uncaught-error handler and
      // the devtools `[cause]` chain are the ONLY places the original failure can still
      // be read. Dropping it turned "ledger.schema.json broke at line 412" into
      // "something in the registry is not JSON", which is the symptom, not the fault.
      throw new Error(`contracts/${name} is not valid JSON: ${String(error)}`, {
        cause: error,
      });
    }
    registry.add(parsed as SchemaDocument);
  }
  registry.compileAll();
  return registry;
}

export function createContractRegistry(): SchemaRegistry {
  return build(CONTRACT_SOURCES);
}

/** Memoised registry. Building it is pure, so one instance is enough for a process. */
export function contractRegistry(): SchemaRegistry {
  cached ??= createContractRegistry();
  return cached;
}

/**
 * The registry with the deferred documents in it too.
 *
 * A SECOND registry rather than a mutation of the memoised one: `compileAll()` resolves
 * every `$ref` and a registry that gained documents after compiling would have two
 * different answers to "does this `$ref` resolve?" depending on when it was asked. One
 * object, one compile, one answer.
 *
 * It throws exactly where {@link createContractRegistry} throws, for the same reasons, so a
 * deferred document carrying an unimplemented keyword fails as loudly as an eager one —
 * later, but not more quietly.
 */
export async function createFullContractRegistry(): Promise<SchemaRegistry> {
  const sources: (readonly [string, string])[] = [...CONTRACT_SOURCES];
  for (const [name, load] of DEFERRED_CONTRACT_SOURCES) {
    sources.push([name, await load()] as const);
  }
  return build(sources);
}
