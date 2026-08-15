// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE READ ENVELOPE, AND THE ONLY PLACE A PROVENANCE CHIP MAY COME FROM.
 *
 * Every read this deployment serves — and the gate run, and the subject index — comes
 * wrapped in the shape `contracts/envelope.schema.json` governs: `envelope_version`,
 * `resource`, `schema_id`, `observed_at`, `server_date`, `staged`, `staged_note`,
 * `statement_refs`, `provenance`, `data`. This module parses that wrapper and refuses one
 * it does not recognise.
 *
 * THE CHIP RULE (D5, carried into the operator surface by operator-systems-plan §4.2):
 * a value on screen may carry a provenance chip **only** when the envelope's `provenance`
 * list names its JSON Pointer. {@link chipFor} is the one function that answers that
 * question, and it answers `null` for a pointer the payload did not claim. The envelope
 * contract states the reason in its own words: *"A pointer absent from this list has NO
 * chip and is rendered without one — an unclaimed provenance is better than a comfortable
 * default."* So a screen that wants a chip asks here; a screen that gets `null` renders
 * the value bare. There is no fallback chip and no ancestor lookup: `/subject` does not
 * inherit the chip of `/subject/open_blocking`, because the emitter claimed one and not
 * the other, and widening that claim on the client would be the console composing an
 * evidentiary assertion — the exact thing D5 exists to forbid.
 *
 * A NAMING NOTE, RECORDED RATHER THAN SMOOTHED OVER. The wire calls the member `chip`
 * (`common.schema.json#/$defs/field_provenance`, `{ pointer, chip }`); the interface
 * operator-systems-plan §4.2 fixed for the four screen workers calls it `kind`. Both names
 * are carried on the parsed entry, with the same value, so neither the contract nor the
 * plan has to be edited to make the other true.
 */

/**
 * The five chips, spelled out as operator-systems-plan §4.2 spells them.
 *
 * NOT imported from the generated contract model, and the reason is that an alias would
 * have caught nothing: a `type` cannot check that the RUNTIME list this module filters on
 * ({@link CHIPS}) still matches the contract, and the runtime list is what decides whether a
 * chip renders. `tests/unit/operator/kernel/envelope.test.ts` reads
 * `contracts/common.schema.json` and asserts the two are the same set, which is a real
 * drift check rather than a compile-time restatement of one.
 */
export type ProvChip = 'db:column' | 'db:constraint' | 'recomputed' | 'staged' | 'derived';

/** One claim the emitter made about where one value came from. */
export interface ProvenanceEntry {
  /** RFC 6901 JSON Pointer into `data`, verbatim. */
  readonly pointer: string;
  /** The chip, under the name operator-systems-plan §4.2 fixed. */
  readonly kind: ProvChip;
  /** The same chip, under the name `common.schema.json` uses on the wire. */
  readonly chip: ProvChip;
  /** Present only when the payload carried one. Today's contract admits none. */
  readonly note?: string;
}

/** Where a payload came from, as `common.schema.json#/$defs/statement_ref` states it. */
export interface StatementRef {
  readonly kind: string;
  readonly object: string;
  /** The statement VERBATIM when the emitter disclosed one; null when it declined. */
  readonly text: string | null;
  readonly sql_path: string | null;
}

/** The parsed read envelope. Member names follow the wire and operator-systems-plan §4.2. */
export interface Envelope {
  readonly envelope_version: 1;
  readonly resource: string;
  readonly schema_id: string;
  /** When the read API produced this payload. Null when it declined to say; never now(). */
  readonly observed_at: string | null;
  /** The server's own clock at emission — the honest half of a clock-skew reading. */
  readonly server_date: string | null;
  /** True when any part of `data` is hand-authored demonstration material. */
  readonly staged: boolean;
  /** Non-null exactly when `staged` is true, in the words of whoever staged it. */
  readonly staged_note: string | null;
  readonly statement_refs: readonly StatementRef[];
  readonly provenance: readonly ProvenanceEntry[];
}

/**
 * The result of looking at one response body.
 *
 * `ok: false` with `reason: null` means "this is not an envelope" — a problem+json body,
 * an empty body, HTML. `ok: false` with a `reason` means "it claims to be one and this
 * reader refuses it", which the envelope contract requires: *"A reader that does not
 * recognise the version refuses the payload rather than guessing at it."*
 */
export type EnvelopeParse =
  | { readonly ok: true; readonly envelope: Envelope; readonly data: unknown }
  | { readonly ok: false; readonly reason: string | null };

/**
 * The runtime vocabulary. An entry naming anything else is skipped, so a chip this build
 * does not know cannot render as one it does. Exported for the drift test only.
 */
export const CHIPS: readonly ProvChip[] = [
  'db:column',
  'db:constraint',
  'recomputed',
  'staged',
  'derived',
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** True only for one of the five. Nothing is coerced and nothing is defaulted. */
function isChip(value: unknown): value is ProvChip {
  return typeof value === 'string' && (CHIPS as readonly string[]).includes(value);
}

function stringOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function parseProvenance(value: unknown): readonly ProvenanceEntry[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const entries: ProvenanceEntry[] = [];
  for (const item of value as readonly unknown[]) {
    if (!isRecord(item)) {
      continue;
    }
    const pointer = item.pointer;
    // `chip` is the wire name; `kind` is accepted so a future emitter that adopts the
    // §4.2 spelling is not silently dropped. Neither is defaulted: an entry naming a chip
    // this reader does not know is skipped, and a value with no entry gets no chip.
    const chip = item.chip ?? item.kind;
    if (typeof pointer !== 'string' || !isChip(chip)) {
      continue;
    }
    const note = item.note;
    entries.push(
      typeof note === 'string'
        ? { pointer, kind: chip, chip, note }
        : { pointer, kind: chip, chip },
    );
  }
  return entries;
}

function parseStatementRefs(value: unknown): readonly StatementRef[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const refs: StatementRef[] = [];
  for (const item of value as readonly unknown[]) {
    if (!isRecord(item)) {
      continue;
    }
    const kind = item.kind;
    const object = item.object;
    if (typeof kind !== 'string' || typeof object !== 'string') {
      continue;
    }
    refs.push({
      kind,
      object,
      text: stringOrNull(item.text),
      sql_path: stringOrNull(item.sql_path),
    });
  }
  return refs;
}

/**
 * Read one response body as an envelope.
 *
 * Structural only. This is NOT the console's runtime contract validator — that lives in
 * `src/data/schema.ts`, which R1 puts out of bounds for the operator surface because it
 * would drag the whole read stack into an entry that must add zero bytes to the existing
 * one. What is checked here is exactly what the envelope contract makes a precondition of
 * reading anything at all: the version, and that the wrapper's required members are
 * present and of the stated type. Everything under `data` is asserted by the caller's type
 * parameter and is NOT validated — which is why every screen renders absence for a null
 * field, and why the raw drawer (R18) puts the bytes themselves one click away.
 */
export function parseEnvelope(value: unknown): EnvelopeParse {
  if (!isRecord(value)) {
    return { ok: false, reason: null };
  }
  const version = value.envelope_version;
  if (version === undefined) {
    return { ok: false, reason: null };
  }
  if (version !== 1) {
    return {
      ok: false,
      reason:
        `envelope_version is ${JSON.stringify(version)} and this reader knows version 1. ` +
        `The envelope contract requires a reader that does not recognise the version to ` +
        `refuse the payload rather than guess at it.`,
    };
  }
  const resource = value.resource;
  const schemaId = value.schema_id;
  const staged = value.staged;
  if (typeof resource !== 'string' || typeof schemaId !== 'string' || typeof staged !== 'boolean') {
    return {
      ok: false,
      reason:
        `the body declares envelope_version 1 but does not carry resource, schema_id and ` +
        `staged as the contract requires, so it is not a payload this reader can name.`,
    };
  }
  return {
    ok: true,
    envelope: {
      envelope_version: 1,
      resource,
      schema_id: schemaId,
      observed_at: stringOrNull(value.observed_at),
      server_date: stringOrNull(value.server_date),
      staged,
      staged_note: stringOrNull(value.staged_note),
      statement_refs: parseStatementRefs(value.statement_refs),
      provenance: parseProvenance(value.provenance),
    },
    data: value.data ?? null,
  };
}

/**
 * The chip for one JSON Pointer, or `null`.
 *
 * Exact pointer match, by design (see the module note). Screens attach chips from this
 * function only; a chip that is not backed by a provenance pointer must not render.
 */
export function chipFor(env: Envelope | null, jsonPointer: string): ProvChip | null {
  if (env === null) {
    return null;
  }
  for (const entry of env.provenance) {
    if (entry.pointer === jsonPointer) {
      return entry.kind;
    }
  }
  return null;
}

/** Every pointer the envelope claimed, in wire order. For the raw drawer and W7's proof. */
export function claimedPointers(env: Envelope | null): readonly string[] {
  return env === null ? [] : env.provenance.map((entry) => entry.pointer);
}
