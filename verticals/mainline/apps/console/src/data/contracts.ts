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
export function createContractRegistry(): SchemaRegistry {
  const registry = new SchemaRegistry();
  for (const [name, source] of CONTRACT_SOURCES) {
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

/** Memoised registry. Building it is pure, so one instance is enough for a process. */
export function contractRegistry(): SchemaRegistry {
  cached ??= createContractRegistry();
  return cached;
}
