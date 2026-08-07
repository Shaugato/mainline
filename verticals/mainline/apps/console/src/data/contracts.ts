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
 * minutes of `tsc` across sixteen files and buys nothing — the schemas are consumed as
 * data by the validator, never as types by a call site. The types the console actually
 * uses come from `types.generated.ts`, which is generated from these same files by
 * `scripts/gen-types.ts`.
 *
 * **The imports are explicit, one per line, rather than an `import.meta.glob`.** A glob
 * would silently drop a contract that was renamed or deleted, and the first symptom
 * would be a `$ref` failing to resolve at runtime in front of a judge. An explicit list
 * turns the same mistake into a build error.
 *
 * `refusal.schema.json` is a VERBATIM copy of `spec/wire/refusal.schema.json`. It is
 * copied rather than imported because the console workspace may not reach outside
 * itself, and `tests/unit/data/refusal-contract.test.ts` fails the moment the copy and
 * the specification disagree. Never edit it here — edit the specification, then re-copy.
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
import invokeRaw from '../../contracts/invoke.schema.json?raw';
import ledgerRaw from '../../contracts/ledger.schema.json?raw';
import permitRaw from '../../contracts/permit.schema.json?raw';
import propagationRaw from '../../contracts/propagation.schema.json?raw';
import recallRunRaw from '../../contracts/recall-run.schema.json?raw';
import refusalRaw from '../../contracts/refusal.schema.json?raw';
import silenceRaw from '../../contracts/silence.schema.json?raw';

import type { SchemaDocument } from './schema';
import { SchemaRegistry } from './schema';

/**
 * File name → source text. The key is the file name because that is what a `$ref` like
 * `common.schema.json#/$defs/uuid` names, and because it is what a human greps for.
 */
export const CONTRACT_SOURCES: ReadonlyArray<readonly [string, string]> = Object.freeze([
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
  ['invoke.schema.json', invokeRaw],
  ['ledger.schema.json', ledgerRaw],
  ['permit.schema.json', permitRaw],
  ['propagation.schema.json', propagationRaw],
  ['recall-run.schema.json', recallRunRaw],
  ['refusal.schema.json', refusalRaw],
  ['silence.schema.json', silenceRaw],
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
      throw new Error(`contracts/${name} is not valid JSON: ${String(error)}`);
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
