// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The evidence view's model — pure, synchronous, and free of React and of I/O.
 *
 * This surface answers one question about the console itself:
 *
 * > Every byte on every other screen came from a file in this table. Are these the
 * > bytes that were sealed, and what is in the table that no screen ever reads?
 *
 * Everything here is arithmetic over `manifest.files` plus the declarations in
 * `src/data/resources.ts`. Nothing is inferred, nothing is smoothed, and every value a
 * caller renders can be recomputed by a reader with the same two inputs — which is the
 * whole point of putting it in a separate module from the screen.
 *
 * ── WHERE A FRAME'S REQUEST LINE COMES FROM, AND WHAT THAT COSTS ─────────────────
 *
 * It comes from `manifest.files[].key`, and it used to come from the file name.
 *
 * Frame file names were once the request line itself under a `~XX` escape, so this
 * module could decode a name and re-encode it to prove the file was filed where its
 * producer would have filed it. That scheme is gone: it produced 218-character paths
 * that a default Windows install cannot check out (see
 * `scripts/submission/check_path_lengths.py`), and names are now content addresses,
 * `<METHOD>-<sha256(key)[:16]>.json`.
 *
 * The honest consequence, stated rather than papered over: **this module can no longer
 * re-derive a frame's name and can no longer, by itself, tell you the name is right.**
 * `src/**` computes no digests, so it cannot hash the key. What replaces the round trip
 * is not nothing, and it is not weaker — it is somewhere else:
 *
 *   * `scripts/capture-bundle.ts seal` REFUSES to seal a directory in which any frame
 *     is not filed under the content address of its own declared key, and `check`
 *     re-derives the same thing independently. A misfiled frame never reaches a
 *     manifest.
 *   * `tests/unit/evidence/model.test.ts` re-hashes every fixture frame's key with
 *     WebCrypto and asserts the committed names match — the round trip, moved to the
 *     one tree that is allowed to hash.
 *   * `BundleTransport` still compares the manifest's `key` against the key inside the
 *     frame's own bytes on every exchange, so the two copies cannot drift apart
 *     unnoticed at serve time.
 *
 * What this module checks is what it can check from the manifest alone: that a frame
 * declares a key at all, and that the key parses as a request a declared resource could
 * have produced. `framesWithoutKey` counts the ones that do not, and the screen shows
 * it, because a frame nothing can address is invisible rather than wrong.
 */

import type { BundleFileEntry, BundleManifest } from '../../data/bundle';
import { RESOURCES, type ResourceDescriptor } from '../../data/resources';

// ── Classification ─────────────────────────────────────────────────────────

/** What a listed file is, decided by its bundle-relative path alone. */
export type FileKind = 'frame' | 'ledger' | 'sql' | 'other';

export function classifyBundlePath(path: string): FileKind {
  if (path.startsWith('frames/')) return 'frame';
  if (path.startsWith('ledger/')) return 'ledger';
  if (path.startsWith('sql/')) return 'sql';
  return 'other';
}

/** The content-address shape `scripts/capture-bundle.ts` writes. */
const FRAME_NAME = /^frames\/(?:GET|POST|REQ)-[0-9a-f]{16}\.json$/;

/**
 * Whether a path is a well-formed frame content address.
 *
 * This is a SHAPE check, not an integrity check: it says the name looks like something
 * the producer writes, not that it is the address of the key the entry declares —
 * confirming that needs a SHA-256 this tree does not compute. It is reported as its own
 * count so the difference is visible on the screen rather than implied.
 */
export function isFrameAddress(path: string): boolean {
  return FRAME_NAME.test(path);
}

/**
 * The request key a manifest entry declares, or `null`.
 *
 * `null` is a real answer and is rendered as one: a frame carrying no key cannot be
 * addressed by any screen, which is worth seeing rather than hiding behind a guess
 * reconstructed from a file name.
 */
export function keyFromManifestEntry(entry: BundleFileEntry): string | null {
  const key = entry.key ?? null;
  return typeof key === 'string' && key !== '' ? key : null;
}

/** `GET /v1/permits/018f…?as_of=…` split into its three canonical parts. */
export interface ParsedRequestKey {
  readonly method: string;
  readonly path: string;
  readonly query: readonly (readonly [string, string])[];
}

export function parseRequestKey(key: string): ParsedRequestKey | null {
  const space = key.indexOf(' ');
  if (space <= 0) return null;
  const method = key.slice(0, space);
  if (method !== 'GET' && method !== 'POST') return null;

  const rest = key.slice(space + 1);
  if (!rest.startsWith('/')) return null;
  const mark = rest.indexOf('?');
  const path = mark >= 0 ? rest.slice(0, mark) : rest;
  const queryString = mark >= 0 ? rest.slice(mark + 1) : '';
  const query = queryString === '' ? [] : [...new URLSearchParams(queryString)].map(
    ([name, value]) => [name, value] as const,
  );
  return { method, path, query };
}

/** A path template (`/v1/permits/{permit_id}`) as an anchored pattern. */
function templatePattern(template: string): RegExp {
  const source = template
    .split(/(\{[a-z_]+\})/)
    .map((part) =>
      /^\{[a-z_]+\}$/.test(part)
        ? '[A-Za-z0-9._~-]{1,128}'
        : part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
    )
    .join('');
  return new RegExp(`^${source}$`);
}

/**
 * Which declared resource a captured request key belongs to, or `null`.
 *
 * `null` is a real answer and is rendered as one: a frame that matches no declared
 * resource is a captured exchange the console has no way to ask for, which is worth
 * seeing rather than hiding.
 */
export function resourceForRequestKey(key: string): ResourceDescriptor | null {
  const parsed = parseRequestKey(key);
  if (parsed === null) return null;
  for (const resource of RESOURCES.values()) {
    if (resource.method !== parsed.method) continue;
    if (!templatePattern(resource.template).test(parsed.path)) continue;
    if (parsed.query.every(([name]) => resource.queryParams.includes(name))) return resource;
  }
  return null;
}

// ── The inventory ──────────────────────────────────────────────────────────

/** What a frame turned out to be, once the manifest was read. */
export interface FrameFacts {
  /** The canonical request key the manifest declares for this frame. */
  readonly requestKey: string;
  /**
   * Whether the file name has the shape of a content address. False means the file is
   * filed under a name the producer would never have written. It does NOT establish
   * that the address is the one this key hashes to — see the module note.
   */
  readonly canonical: boolean;
  /** The declared resource it answers, or null when no declaration matches. */
  readonly resourceKey: string | null;
  /** The backend domain that owes the endpoint, or null when nobody does (ui.md §4). */
  readonly owner: string | null;
  readonly purpose: string | null;
}

/** `unchecked` is the state before the oracle has run; it never means "fine". */
export type DigestState = 'unchecked' | 'match' | 'mismatch' | 'unreadable';

export interface InventoryRow {
  readonly path: string;
  readonly kind: FileKind;
  readonly declaredDigest: string;
  readonly declaredBytes: number;
  readonly mediaType: string | null;
  readonly frame: FrameFacts | null;
  readonly state: DigestState;
  /** The digest this browser computed, or null when it did not get that far. */
  readonly actualDigest: string | null;
  readonly actualBytes: number | null;
  /** Verbatim reason, for `unreadable` and `mismatch`. Never a summary. */
  readonly detail: string | null;
}

function frameFactsFor(entry: BundleFileEntry): FrameFacts | null {
  const requestKey = keyFromManifestEntry(entry);
  if (requestKey === null) return null;
  const resource = resourceForRequestKey(requestKey);
  return {
    requestKey,
    canonical: isFrameAddress(entry.path),
    resourceKey: resource?.key ?? null,
    owner: resource?.owner ?? null,
    purpose: resource?.purpose ?? null,
  };
}

/** One row per `manifest.files` entry, in manifest order, before anything is read. */
export function buildInventory(manifest: BundleManifest): readonly InventoryRow[] {
  return manifest.files.map((entry: BundleFileEntry) => {
    const kind = classifyBundlePath(entry.path);
    return {
      path: entry.path,
      kind,
      declaredDigest: entry.sha256,
      declaredBytes: entry.bytes,
      mediaType: entry.media_type ?? null,
      frame: kind === 'frame' ? frameFactsFor(entry) : null,
      state: 'unchecked' as const,
      actualDigest: null,
      actualBytes: null,
      detail: null,
    };
  });
}

// ── Coverage arithmetic ────────────────────────────────────────────────────

export interface Coverage {
  readonly filesDeclared: number;
  readonly digestsMatched: number;
  readonly digestsMismatched: number;
  readonly filesUnreadable: number;
  readonly filesUnchecked: number;
  readonly bytesDeclared: number;
  readonly bytesRead: number;
  readonly framesDeclared: number;
  /** Frames whose file name is not the canonical encoding of the key it decodes to. */
  readonly framesNonCanonical: number;
  /** Frames that decode to a request no declared resource can produce. */
  readonly framesUnaddressable: number;
  readonly resourcesDeclared: number;
  readonly resourcesWithFrame: number;
  /**
   * Files present in the directory but absent from the manifest, or `null` when the
   * source cannot enumerate itself — which is the normal case for a static host and is
   * rendered as "not established", never as zero.
   */
  readonly unlisted: readonly string[] | null;
  /**
   * `filesDeclared === matched + mismatched + unreadable + unchecked`.
   *
   * A conservation law over the audit's own bookkeeping. It cannot fail while the code
   * is correct, which is exactly why it is displayed: a coverage panel whose parts do
   * not sum to its whole is the one defect that would otherwise be invisible on a
   * screen made of counters.
   */
  readonly conserved: boolean;
}

export function summarise(
  rows: readonly InventoryRow[],
  unlisted: readonly string[] | null,
): Coverage {
  let matched = 0;
  let mismatched = 0;
  let unreadable = 0;
  let unchecked = 0;
  let bytesDeclared = 0;
  let bytesRead = 0;
  let frames = 0;
  let nonCanonical = 0;
  let unaddressable = 0;
  const resourceKeys = new Set<string>();

  for (const row of rows) {
    bytesDeclared += row.declaredBytes;
    bytesRead += row.actualBytes ?? 0;
    if (row.state === 'match') matched += 1;
    else if (row.state === 'mismatch') mismatched += 1;
    else if (row.state === 'unreadable') unreadable += 1;
    else if (row.state === 'unchecked') unchecked += 1;
    // Deliberately no `else`. A row carrying a state this summary has never heard of is
    // counted in NO bucket, so `conserved` goes false and the screen says so. That is
    // the whole point of the conservation law: the day somebody adds a fifth
    // `DigestState` and forgets a branch here, the defect is visible instead of being
    // absorbed into "not checked".

    if (row.kind !== 'frame') continue;
    frames += 1;
    if (row.frame?.canonical !== true) nonCanonical += 1;
    const resourceKey = row.frame?.resourceKey ?? null;
    if (resourceKey === null) unaddressable += 1;
    else resourceKeys.add(resourceKey);
  }

  return {
    filesDeclared: rows.length,
    digestsMatched: matched,
    digestsMismatched: mismatched,
    filesUnreadable: unreadable,
    filesUnchecked: unchecked,
    bytesDeclared,
    bytesRead,
    framesDeclared: frames,
    framesNonCanonical: nonCanonical,
    framesUnaddressable: unaddressable,
    resourcesDeclared: RESOURCES.size,
    resourcesWithFrame: resourceKeys.size,
    unlisted,
    conserved: matched + mismatched + unreadable + unchecked === rows.length,
  };
}

// ── The gap list ───────────────────────────────────────────────────────────

export interface ResourceGap {
  readonly key: string;
  readonly method: string;
  readonly template: string;
  /** `null` when no backend domain owes this endpoint (ui.md §4, `clause_ancestry`). */
  readonly owner: string | null;
  readonly purpose: string;
}

/**
 * Declared resources for which this bundle carries no captured exchange.
 *
 * Rendered as a list rather than a number. In REPLAY, a resource with no frame is a
 * screen that cannot be shown at all, and naming which ones is the difference between
 * "the demo covers most of it" and a statement a reader can check.
 */
export function resourcesWithoutFrame(rows: readonly InventoryRow[]): readonly ResourceGap[] {
  const present = new Set<string>();
  for (const row of rows) {
    const resourceKey = row.frame?.resourceKey ?? null;
    if (resourceKey !== null) present.add(resourceKey);
  }
  return [...RESOURCES.values()]
    .filter((resource) => !present.has(resource.key))
    .map((resource) => ({
      key: resource.key,
      method: resource.method,
      template: resource.template,
      owner: resource.owner,
      purpose: resource.purpose,
    }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

// ── What a green seal on this screen does NOT establish ────────────────────

export interface Limit {
  readonly claim: string;
  readonly why: string;
}

/**
 * The limits panel, as data.
 *
 * It is a constant rather than prose in the component for one reason: a unit test can
 * assert it is non-empty and is rendered, so the honesty section cannot be deleted in a
 * hurry the way a paragraph of JSX can. `docs/leads/ui.md` D16 makes the chrome the
 * console's own must-not-claim control; this is the same discipline at surface scale.
 */
export const LIMITS: readonly Limit[] = Object.freeze([
  Object.freeze({
    claim: 'A matching digest establishes provenance, not truth.',
    why:
      'It says these are the bytes that were sealed and that every screen in this console was ' +
      'produced from them. Whether the numbers inside describe a real cluster is what the ' +
      'STAGED flag and cluster_fingerprint.source are for.',
  }),
  Object.freeze({
    claim: 'Nothing here signs the manifest.',
    why:
      'manifest.json is the one file whose digest is not inside itself. Its authenticity rests ' +
      'entirely on where you fetched it from. This screen recomputes its digest so you can ' +
      'compare it against a value you obtained by some other route; it cannot compare it for you.',
  }),
  Object.freeze({
    claim: 'The carried custody bundle is NOT verified on this screen.',
    why:
      'ledger/bundle.json is a spec/wire/evidence-bundle.md artefact carried verbatim. Its ' +
      'Merkle arithmetic and its checkpoint signature belong to the custody surface and to ' +
      'trappoint-verify. Here it is one more file with one more digest.',
  }),
  Object.freeze({
    claim: 'Absence of a smuggled file is not established unless the source can enumerate itself.',
    why:
      'A static host answers requests; it does not list directories. A file present beside the ' +
      'manifest but absent from manifest.files is never served — that is the transport’s ' +
      'rule — but this screen cannot show you that there is no such file.',
  }),
  Object.freeze({
    claim: 'This screen re-derives one thing, and names it.',
    why:
      'SHA-256 over the sealed bytes. It is not the RFC 8785 canonicaliser, not the RFC 6962 ' +
      'inclusion proof and not the ECDSA checkpoint signature; those are the custody surface’s ' +
      'and they make their own claims with their own seals.',
  }),
]);
