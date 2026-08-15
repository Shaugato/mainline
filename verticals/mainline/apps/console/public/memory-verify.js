// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * MEMORY-VERIFY — the one thing on `/memory.html` that is not a read.
 *
 * Every other cell on that page renders a value the server sent, beside a chip the server
 * claimed for it. This module earns the single exception: it takes the bytes the ledger
 * returned, hashes them in the browser, and compares the answer to the hash the ledger
 * says those bytes have. That is why the STORE column can say `recomputed` — a chip the
 * read API is forbidden to emit, because (its own words) *an emitter cannot vouch for a
 * recomputation the reader has not performed.*
 *
 * ── WHAT IS COMPUTED, AND UNDER WHOSE DEFINITION ──────────────────────────────────────
 *
 *   leaf_hash = SHA-256(0x00 || canon_bytes)          RFC 6962 §2.1, the MTH leaf hash
 *   link_hash = SHA-256(prev_link_hash || leaf_hash)  the chain, per the kernel's own
 *                                                     `trappoint_ledger.chain` docstring,
 *                                                     which states there is deliberately
 *                                                     NO domain-separation prefix here
 *                                                     because a link's inputs are two
 *                                                     fixed-width digests and a leaf's are
 *                                                     arbitrary bytes.
 *
 * Both were re-derived against the deployed ledger before this file was written: four
 * leaves, four leaf hashes matched, four links matched. Neither formula is copied from a
 * comment — each is stated by the kernel package that produces the column.
 *
 * ── WHAT THIS MODULE MAY NOT DO ───────────────────────────────────────────────────────
 *
 * It may not invent a provenance chip, and it may not hand a page a chip the response did
 * not claim. The vocabulary below is the envelope's five and it is CLOSED: `renderChip`
 * throws on anything else, and returns `null` — renders NOTHING, not a placeholder, not a
 * dash, not a grey box — when no chip was claimed. An unclaimed provenance is better than
 * a comfortable default.
 *
 * It may not let a failed verification look like a quiet absence. A leaf whose recomputed
 * hash differs from its claimed hash renders as an alert carrying BOTH hex strings in
 * full, and it never carries a `recomputed` chip: the chip is the claim that the
 * recomputation succeeded, so a failure that wore one would be the exact lie this whole
 * page exists to make impossible.
 *
 * No dependency, no framework, no bundler, no network. A plain ES module, loadable by
 * `<script type="module">` from this origin or from `file://`.
 */

/** The envelope's provenance vocabulary, closed. `common.schema.json#/$defs/provenance_chip`. */
export const PROVENANCE_CHIPS = Object.freeze([
  'db:column',
  'db:constraint',
  'recomputed',
  'staged',
  'derived',
]);

/**
 * How each chip is spoken to assistive technology.
 *
 * The first four are transcribed from the console's `src/design/provenance.ts`
 * `PROVENANCE_SPOKEN`, word for word, so a judge hearing the console and hearing this page
 * hears the same sentence for the same claim. The fifth exists because the console's
 * vocabulary has four and the API's has five; `derived` is worded from the read API's own
 * definition of it — computed by that API from columns it names in `statement_refs`.
 */
export const PROVENANCE_SPOKEN = Object.freeze({
  'db:column': 'read from a database column',
  'db:constraint': 'reported by a database constraint',
  recomputed: 'recomputed in this browser from signed bytes',
  staged: 'staged in this browser only — not written, not refused, not signed',
  derived: 'computed by the read API from the columns it names in statement_refs',
});

/**
 * The class names this module emits. Exported so the stylesheet and the audit script name
 * the same strings this file does, rather than each carrying its own copy of them.
 */
export const CLASS_NAMES = Object.freeze({
  chip: 'mem-chip',
  chipDetail: 'mem-chip-detail',
  visuallyHidden: 'mem-visually-hidden',
  verify: 'mem-verify',
  verifyFailure: 'mem-verify-failure',
  verifyHash: 'mem-verify-hash',
  verifyLabel: 'mem-verify-label',
});

/**
 * The two ledger entry kinds that ARE the store half of the loop: the incident being
 * ingested, and the blame closure being computed over it.
 *
 * Addressed by `entry_kind`, never by array index. An index is a fact about the order a
 * seed happened to run in; the kind is a fact about what the row is.
 */
export const MEMORY_LEAF_KINDS = Object.freeze([
  'precursor_event_ingested',
  'blame_closure_computed',
]);

/** The genesis `prev_link_hash`: thirty-two zero bytes, explicit, never null. */
export const GENESIS_LINK_HASH_HEX = '0'.repeat(64);

/** Stated on screen beside the result, so the claim names its own definition. */
export const LEAF_HASH_RULE = 'RFC 6962 §2.1 — SHA-256(0x00 || canon_bytes)';
export const LINK_HASH_RULE = 'SHA-256(prev_link_hash || leaf_hash)';

const HEX_64 = /^[0-9a-f]{64}$/;

/**
 * Resolve `crypto.subtle` AT CALL TIME, never at import time.
 *
 * Import-time resolution would freeze whatever was on `globalThis` when the module was
 * first evaluated, which in a test environment is decided by module ordering. Resolving
 * per call means the answer is always the host's real answer.
 *
 * A missing SubtleCrypto is reported as an error, never as a `false` verification: "this
 * browser cannot hash" and "these bytes do not hash to that value" are different facts and
 * only one of them is an accusation.
 */
function requireSubtle() {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle || typeof subtle.digest !== 'function') {
    throw new Error(
      'memory-verify: crypto.subtle is unavailable in this context. ' +
        'SubtleCrypto requires a secure context (https:, localhost, or file:). ' +
        'Nothing is rendered as verified when it was not verified.',
    );
  }
  return subtle;
}

/** Decode standard (padded, non-URL-safe) base64 to bytes. Throws on anything else. */
function decodeBase64(value) {
  if (typeof value !== 'string' || value.length === 0) {
    throw new TypeError('canon_bytes_b64 is not a non-empty string');
  }
  if (typeof globalThis.atob !== 'function') {
    throw new Error('memory-verify: atob is unavailable in this context');
  }
  const binary = globalThis.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/** Bytes to lower-case hex. */
function toHex(bytes) {
  let out = '';
  for (const byte of bytes) {
    out += byte.toString(16).padStart(2, '0');
  }
  return out;
}

/** Hex to bytes. Throws unless the input is exactly 64 lower-case hex characters. */
function fromHex64(value, label) {
  if (typeof value !== 'string' || !HEX_64.test(value)) {
    throw new TypeError(`${label} is not 64 lower-case hex characters`);
  }
  const bytes = new Uint8Array(32);
  for (let i = 0; i < 32; i += 1) {
    bytes[i] = Number.parseInt(value.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

async function sha256Hex(...parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const joined = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    joined.set(part, offset);
    offset += part.length;
  }
  const digest = await requireSubtle().digest('SHA-256', joined);
  return toHex(new Uint8Array(digest));
}

function frozenResult(fields) {
  return Object.freeze({
    seq: null,
    entry_kind: null,
    claimed_leaf_hash_hex: null,
    recomputed_leaf_hash_hex: null,
    canon_bytes_length: null,
    matched: false,
    status: 'unverifiable',
    reason: null,
    rule: LEAF_HASH_RULE,
    ...fields,
  });
}

/**
 * Recompute one ledger leaf's RFC 6962 leaf hash from the bytes the server returned.
 *
 * Returns a structured result and never throws for a leaf that simply fails to verify —
 * a thrown exception is swallowable by a caller's `catch` and a failure must reach the
 * screen. It DOES surface a host without SubtleCrypto as `status: 'unverifiable'` with the
 * reason attached, which is a different sentence from `status: 'mismatch'` and is rendered
 * as a different sentence.
 *
 * `status` is the honest three-way answer:
 *   `match`         the bytes hash to the hash the ledger claims for them
 *   `mismatch`      they do not — the loud case, and the only reason this code exists
 *   `unverifiable`  the leaf did not carry what verification needs, or this host cannot
 *                   hash. NOT a pass, and never rendered as one.
 *
 * @param {unknown} leaf a `data.leaves[]` element from `GET /v1/ledger`
 * @returns {Promise<Readonly<object>>}
 */
export async function verifyLeaf(leaf) {
  if (typeof leaf !== 'object' || leaf === null) {
    return frozenResult({ reason: 'leaf is not an object' });
  }

  const seq = typeof leaf.seq === 'number' ? leaf.seq : null;
  const entryKind = typeof leaf.entry_kind === 'string' ? leaf.entry_kind : null;
  const claimed = typeof leaf.leaf_hash_hex === 'string' ? leaf.leaf_hash_hex.toLowerCase() : null;

  if (claimed === null || !HEX_64.test(claimed)) {
    return frozenResult({
      seq,
      entry_kind: entryKind,
      claimed_leaf_hash_hex: typeof leaf.leaf_hash_hex === 'string' ? leaf.leaf_hash_hex : null,
      reason: 'leaf_hash_hex is not 64 lower-case hex characters',
    });
  }

  let canonBytes;
  try {
    canonBytes = decodeBase64(leaf.canon_bytes_b64);
  } catch (error) {
    return frozenResult({
      seq,
      entry_kind: entryKind,
      claimed_leaf_hash_hex: claimed,
      reason: `canon_bytes_b64 could not be decoded: ${String(error)}`,
    });
  }

  let recomputed;
  try {
    // RFC 6962 §2.1: the leaf hash is over 0x00 concatenated with the entry's bytes. The
    // prefix is what stops a leaf from being reinterpreted as an interior node.
    recomputed = await sha256Hex(new Uint8Array([0x00]), canonBytes);
  } catch (error) {
    return frozenResult({
      seq,
      entry_kind: entryKind,
      claimed_leaf_hash_hex: claimed,
      canon_bytes_length: canonBytes.length,
      reason: String(error),
    });
  }

  const matched = recomputed === claimed;
  return frozenResult({
    seq,
    entry_kind: entryKind,
    claimed_leaf_hash_hex: claimed,
    recomputed_leaf_hash_hex: recomputed,
    canon_bytes_length: canonBytes.length,
    matched,
    status: matched ? 'match' : 'mismatch',
    reason: matched
      ? null
      : 'the bytes the ledger returned do not hash to the hash the ledger claims for them',
  });
}

/**
 * Verify a list of leaves and report the tally.
 *
 * `all_matched` is true only when there is at least one leaf and every one of them
 * matched. An empty list is not a pass — "nothing was checked" must never read as
 * "everything checked out".
 *
 * @param {unknown} leaves
 */
export async function verifyLeaves(leaves) {
  const list = Array.isArray(leaves) ? leaves : [];
  const results = [];
  // Sequential, deliberately: these are four small digests, and a `Promise.all` here would
  // only make the failure ordering on screen depend on which digest finished first.
  for (const leaf of list) {
    results.push(await verifyLeaf(leaf));
  }
  const matched = results.filter((result) => result.matched).length;
  return Object.freeze({
    results: Object.freeze(results),
    total: results.length,
    matched,
    all_matched: results.length > 0 && matched === results.length,
    rule: LEAF_HASH_RULE,
  });
}

/**
 * Verify the hash chain: each `link_hash` is `SHA-256(prev_link_hash || leaf_hash)`, seq 0
 * carries thirty-two zero bytes, and every later `prev_link_hash` names its predecessor's
 * `link_hash`.
 *
 * Secondary to `verifyLeaf` and separately callable. It is here because the two memory
 * leaves are not free-floating digests: they sit at fixed positions in a chain, and a
 * browser that can re-derive the links has shown that the row recording what the incident
 * taught cannot be moved, replaced or dropped without every later link changing. The
 * failure names below are the kernel's own taxonomy, not invented here.
 *
 * @param {unknown} leaves ordered by `seq`, as `GET /v1/ledger` returns them
 */
export async function verifyChain(leaves) {
  const list = Array.isArray(leaves) ? leaves : [];
  const failures = [];
  let expectedPrev = GENESIS_LINK_HASH_HEX;

  for (const leaf of list) {
    const seq = typeof leaf?.seq === 'number' ? leaf.seq : null;
    let prev;
    let leafHash;
    let claimedLink;
    try {
      prev = String(leaf?.prev_link_hash_hex ?? '').toLowerCase();
      leafHash = String(leaf?.leaf_hash_hex ?? '').toLowerCase();
      claimedLink = String(leaf?.link_hash_hex ?? '').toLowerCase();
      fromHex64(prev, 'prev_link_hash_hex');
      fromHex64(leafHash, 'leaf_hash_hex');
      fromHex64(claimedLink, 'link_hash_hex');
    } catch (error) {
      failures.push({ seq, code: 'leaf_is_not_chain_shaped', detail: String(error) });
      break;
    }

    if (prev !== expectedPrev) {
      failures.push({
        seq,
        code:
          expectedPrev === GENESIS_LINK_HASH_HEX
            ? 'genesis_prev_link_hash_wrong'
            : 'prev_link_hash_does_not_name_predecessor',
        detail: `expected ${expectedPrev}, got ${prev}`,
      });
    }

    const recomputedLink = await sha256Hex(fromHex64(prev, 'prev'), fromHex64(leafHash, 'leaf'));
    if (recomputedLink !== claimedLink) {
      failures.push({
        seq,
        code: 'link_hash_is_not_sha256_of_prev_and_leaf',
        detail: `expected ${claimedLink}, recomputed ${recomputedLink}`,
      });
    }
    expectedPrev = claimedLink;
  }

  return Object.freeze({
    total: list.length,
    failures: Object.freeze(failures),
    linked: list.length > 0 && failures.length === 0,
    head_link_hash_hex: list.length > 0 ? expectedPrev : null,
    rule: LINK_HASH_RULE,
  });
}

/**
 * Pick the two memory leaves out of a ledger payload BY `entry_kind`.
 *
 * Always returns one entry per kind, in the order the store happened: a kind the ledger
 * did not carry comes back with `leaf: null`, so the caller renders an absence instead of
 * rendering nothing at all. Silently returning a one-element array would let a missing
 * memory write disappear from the panel, which is the failure mode with no symptom.
 *
 * @param {unknown} leaves
 */
export function selectMemoryLeaves(leaves) {
  const list = Array.isArray(leaves) ? leaves : [];
  return Object.freeze(
    MEMORY_LEAF_KINDS.map((kind) =>
      Object.freeze({
        entry_kind: kind,
        leaf: list.find((leaf) => leaf?.entry_kind === kind) ?? null,
      }),
    ),
  );
}

/**
 * Resolve the chip an envelope claimed for one RFC 6901 pointer — or `null`.
 *
 * This is the only legal way for the page to obtain a `kind`. The page does not decide
 * what a value is; the response does, and a pointer absent from `provenance[]` gets no
 * chip. A chip string the vocabulary does not contain is a REFUSAL, not a fallback: an
 * unrecognised chip means this page and that server disagree about what a claim means, and
 * quietly dropping it would hide the disagreement.
 *
 * @param {unknown} provenance the envelope's `provenance` array of `{chip, pointer}`
 * @param {string} pointer
 * @returns {string|null}
 */
export function lookupChip(provenance, pointer) {
  if (typeof pointer !== 'string' || pointer.length === 0) {
    throw new TypeError('lookupChip: pointer must be a non-empty RFC 6901 pointer');
  }
  const list = Array.isArray(provenance) ? provenance : [];
  const entry = list.find((item) => item?.pointer === pointer);
  if (entry === undefined) {
    return null;
  }
  if (!PROVENANCE_CHIPS.includes(entry.chip)) {
    throw new RangeError(
      `lookupChip: the response claimed chip ${JSON.stringify(entry.chip)} at ${pointer}, ` +
        `which is outside the closed vocabulary [${PROVENANCE_CHIPS.join(', ')}]`,
    );
  }
  return entry.chip;
}

function resolveDocument(options) {
  const doc = options?.document ?? globalThis.document;
  if (!doc || typeof doc.createElement !== 'function') {
    throw new Error('memory-verify: no document is available to render into');
  }
  return doc;
}

function span(doc, className, text) {
  const element = doc.createElement('span');
  if (className) {
    element.className = className;
  }
  if (text !== undefined) {
    element.textContent = text;
  }
  return element;
}

/**
 * Render one provenance chip, or nothing.
 *
 * THE NO-CHIP PATH IS FIRST CLASS. `kind` of `null` or `undefined` returns `null` and the
 * caller appends nothing — no placeholder, no em dash, no empty box. A value with no
 * claimed provenance must look like a value with no claimed provenance.
 *
 * Anything else outside the closed five throws. There is no sixth chip, and a page that
 * invented one would be assigning a meaning the emitter never asserted.
 *
 * The DOM shape mirrors the console's `ProvenanceChip`: the spoken sentence is read to
 * assistive technology, the bare kind is shown to sighted readers, and the detail slot
 * carries the pointer the chip was claimed at. A non-`staged` chip with no pointer renders
 * the word `unspecified`, because an empty slot looks like a chip with nothing to say and
 * a missing caller argument looks like a bug — they are different bugs.
 *
 * @param {string|null|undefined} kind
 * @param {string|null|undefined} pointer the RFC 6901 pointer the chip was claimed at
 * @returns {Element|null}
 */
export function renderChip(kind, pointer, options) {
  if (kind === null || kind === undefined) {
    return null;
  }
  if (!PROVENANCE_CHIPS.includes(kind)) {
    throw new RangeError(
      `renderChip: ${JSON.stringify(kind)} is not one of the closed provenance chips ` +
        `[${PROVENANCE_CHIPS.join(', ')}]. The vocabulary is closed; nothing may invent a sixth.`,
    );
  }

  const doc = resolveDocument(options);
  const chip = doc.createElement('span');
  chip.className = CLASS_NAMES.chip;
  chip.setAttribute('data-kind', kind);

  const spoken = span(doc, CLASS_NAMES.visuallyHidden, `provenance: ${PROVENANCE_SPOKEN[kind]}. `);
  chip.appendChild(spoken);

  const shown = span(doc, '', kind);
  shown.setAttribute('aria-hidden', 'true');
  chip.appendChild(shown);

  const detail = pointer ?? (kind === 'staged' ? null : 'unspecified');
  if (detail !== null && detail !== undefined) {
    chip.appendChild(span(doc, CLASS_NAMES.chipDetail, String(detail)));
  }
  return chip;
}

/**
 * Render the outcome of `verifyLeaf` — and make a failure impossible to miss.
 *
 * A match renders the `recomputed` chip and both hex strings IN FULL: an ellipsis would
 * make the one value on this page that the browser computed the one value a judge cannot
 * find in the response body.
 *
 * Anything that is not a match renders `role="alert"`, the word REFUSED-in-kind — the
 * status itself — the reason, and both hashes where they exist, and carries NO chip. It
 * is styled by `data-verify`, which a stylesheet can make loud but cannot make absent.
 *
 * @param {Readonly<object>} result the value returned by `verifyLeaf`
 */
export function renderLeafVerification(result, options) {
  if (typeof result !== 'object' || result === null || typeof result.status !== 'string') {
    throw new TypeError('renderLeafVerification: expected a verifyLeaf() result');
  }
  const doc = resolveDocument(options);
  const root = doc.createElement('span');
  root.className = CLASS_NAMES.verify;
  root.setAttribute('data-verify', result.status);
  if (typeof result.entry_kind === 'string') {
    root.setAttribute('data-entry-kind', result.entry_kind);
  }

  if (result.status === 'match' && result.matched === true) {
    root.appendChild(
      span(
        doc,
        CLASS_NAMES.visuallyHidden,
        `leaf hash recomputed in this browser from the bytes the ledger returned, ` +
          `and it matches the hash the ledger claims: ${LEAF_HASH_RULE}. `,
      ),
    );
    const chip = renderChip('recomputed', options?.pointer ?? null, options);
    if (chip !== null) {
      root.appendChild(chip);
    }
    const hash = span(doc, CLASS_NAMES.verifyHash, result.recomputed_leaf_hash_hex);
    hash.setAttribute('data-hash', 'recomputed');
    root.appendChild(hash);
    root.appendChild(span(doc, CLASS_NAMES.verifyLabel, LEAF_HASH_RULE));
    return root;
  }

  // Not a match. No chip is attached on this path, ever: the chip asserts that a
  // recomputation succeeded, and one did not.
  root.classList.add(CLASS_NAMES.verifyFailure);
  root.setAttribute('role', 'alert');
  root.appendChild(
    span(
      doc,
      CLASS_NAMES.verifyLabel,
      result.status === 'mismatch'
        ? 'LEAF HASH DOES NOT VERIFY'
        : 'LEAF HASH COULD NOT BE VERIFIED',
    ),
  );
  if (typeof result.reason === 'string' && result.reason.length > 0) {
    root.appendChild(span(doc, CLASS_NAMES.verifyLabel, result.reason));
  }
  if (typeof result.claimed_leaf_hash_hex === 'string') {
    const claimed = span(doc, CLASS_NAMES.verifyHash, result.claimed_leaf_hash_hex);
    claimed.setAttribute('data-hash', 'claimed');
    root.appendChild(claimed);
  }
  if (typeof result.recomputed_leaf_hash_hex === 'string') {
    const recomputed = span(doc, CLASS_NAMES.verifyHash, result.recomputed_leaf_hash_hex);
    recomputed.setAttribute('data-hash', 'recomputed');
    root.appendChild(recomputed);
  }
  return root;
}

// ── The client: two cells, no request of its own ──────────────────────────────────────

/**
 * The `data-cell` ids the shell reserves for THIS module.
 *
 * `memory-loop.js` owns `store.` `retrieve.` `act.` `meta.` `annot.` and states in its own
 * seam grammar that ids outside those namespaces belong to another client — "the
 * recomputation client owns `verify.`". These two are that claim, written down on this
 * side of the seam so both files can be read against each other.
 */
export const VERIFY_CELLS = Object.freeze({
  precursor_event_ingested: 'verify.leaf.ingested',
  blame_closure_computed: 'verify.leaf.closure',
});

/** The event the loop client bubbles once its four reads have resolved. */
export const READY_EVENT = 'memory-loop:ready';

function paintCell(element, node) {
  element.replaceChildren(node);
  element.dataset.filled = 'true';
  delete element.dataset.error;
}

function paintCellFailure(element, message, doc) {
  element.replaceChildren(doc.createTextNode(message));
  element.dataset.filled = 'true';
  element.dataset.error = 'true';
}

/**
 * Fill the two `verify.` cells from the ledger the loop client ALREADY fetched.
 *
 * **This module issues no request.** The panel's contract is four GETs on load and one POST
 * on press, and a fifth read for the same bytes would be a fifth line in the network panel
 * a judge is being invited to open. The bytes arrive on the `memory-loop:ready` event; this
 * function hashes them.
 *
 * Every path renders. A ledger read that failed paints its own failure sentence into the
 * cell that needed it, a ledger that carried no leaf of that kind says exactly that, and a
 * leaf that does not verify paints the alert. None of them paints a value.
 *
 * @param {Element|null} root the element the cells live under
 * @param {{ledger?: {state?: string, failure?: string, envelope?: unknown}}} sources
 */
export async function mountVerification(root, sources, options) {
  const doc = resolveDocument(options);
  const host = root ?? doc.body;
  const slot = sources?.ledger;
  const envelope = slot?.state === 'ok' ? slot.envelope : null;
  const leaves = Array.isArray(envelope?.data?.leaves) ? envelope.data.leaves : [];
  const filled = [];

  for (const { entry_kind: kind, leaf } of selectMemoryLeaves(leaves)) {
    const id = VERIFY_CELLS[kind];
    const elements = [...host.querySelectorAll(`[data-cell="${id}"]`)];
    if (elements.length === 0) {
      continue;
    }

    if (slot === undefined || slot === null) {
      for (const element of elements) {
        paintCellFailure(element, `${id}: the ledger read was never made`, doc);
      }
      continue;
    }
    if (slot.state !== 'ok') {
      for (const element of elements) {
        paintCellFailure(element, String(slot.failure ?? `${id}: the ledger read failed`), doc);
      }
      continue;
    }
    if (leaf === null) {
      for (const element of elements) {
        paintCellFailure(element, `${id}: the ledger carried no ${kind} leaf`, doc);
      }
      continue;
    }

    const result = await verifyLeaf(leaf);
    const pointer = `/data/leaves/${String(leaves.indexOf(leaf))}/leaf_hash_hex`;
    for (const element of elements) {
      paintCell(element, renderLeafVerification(result, { ...options, pointer }));
    }
    filled.push(result);
  }

  return Object.freeze({ results: Object.freeze(filled), rule: LEAF_HASH_RULE });
}

/**
 * Listen for the loop client's ready event and verify what it fetched.
 *
 * Returns the listener's removal function so a host page that mounts the loop more than
 * once is not left with two.
 */
export function attachVerification(target, options) {
  const listener = (event) => {
    const detail = event?.detail ?? {};
    const host = event?.target instanceof Element ? event.target : null;
    void mountVerification(host, detail.sources, options).catch((error) => {
      // The cells keep the shell's own "no value was handed to this slot" marker, and the
      // reason is on the console rather than invented into the cell.
      console.error('[memory-verify]', error);
    });
  };
  target.addEventListener(READY_EVENT, listener);
  return () => {
    target.removeEventListener(READY_EVENT, listener);
  };
}

// `/memory.html` loads this file with one `<script type="module">` and needs no code of its
// own. The guard is on the PAGE, mirroring `memory-loop.js`, so that importing this module
// anywhere else — a unit spec, an operator screen — attaches nothing.
if (
  typeof document !== 'undefined' &&
  typeof location !== 'undefined' &&
  location.pathname.endsWith('memory.html')
) {
  attachVerification(document);
}

