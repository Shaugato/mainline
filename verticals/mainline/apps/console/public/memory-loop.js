// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
//
// The `LicenseRef-` form, deliberately: the Functional Source License is not on the SPDX
// list, so REUSE 3.3 requires it, and `scripts/qa/check_reuse.py`'s policy counts the bare
// spelling as a divergence under a ratchet that may fall and may not rise. A new file
// carrying the bare spelling would push that number up by one.

/**
 * memory-loop.js — the data client for `/memory.html`.
 *
 * WHAT THIS FILE IS
 * -----------------
 * A plain ES module. No framework, no bundler, no dependency, no build step. It lives in
 * `console/public/`, so Vite copies it to `dist/` verbatim: it never enters the module
 * graph, never enters `dist/.vite/manifest.json`, and therefore adds ZERO bytes to the
 * entry chunk the deployed origin serves under a 136 KiB per-response ceiling
 * (`docs/demo/memory-visible-plan.md`, ruling R-M2).
 *
 * It makes the page a REAL CLIENT OF THE REAL KERNEL: four GETs on mount, one POST on
 * press, and every character it writes into the page came out of one of those five
 * response bodies. Nothing here composes a refusal, a SQLSTATE, a count, a hash or a
 * latency. If a judge opens devtools, the five exchanges are there and every value on
 * screen is `Ctrl-F`-able inside one of them.
 *
 * THE RULINGS THIS FILE IMPLEMENTS (docs/demo/memory-visible-plan.md §2)
 * ---------------------------------------------------------------------
 * R-M3  Chips are RENDERED, never chosen. Every chip beside a value is the chip the
 *       response's own `provenance[]` claimed for that RFC 6901 pointer. A pointer the
 *       envelope did not claim gets NO chip and no substitute — `envelope.py` says
 *       "unclaimed provenance is better than a comfortable default", and this module has
 *       no vocabulary of its own to fall back to.
 * R-M4  A number computed in this browser gets NO chip and appears only as an annotation
 *       that names itself as arithmetic, beside both operands.
 * R-M5  The severity / virulence / closure_gen equality is computed across TWO separate
 *       responses and rendered unchipped as `match` or `DIFFERS`, with both operands in
 *       the text.
 * R-M6  `statement_refs[].text` is rendered byte for byte. Where `text` is null the page
 *       renders `kind`, `object` and the literal words "statement text not returned by
 *       this endpoint". No statement from a migration or a seed is ever pasted into that
 *       gap — a query path we assert is worth less than one the server hands us.
 * R-M7  ONE POST fills the ACT column; the four beats already happened inside one
 *       SERIALIZABLE transaction, so splitting them would destroy that property. Each
 *       beat renders its OWN `elapsed_ms` from the payload. The progressive reveal is
 *       constructed INSIDE the scope that already holds the parsed body — there is
 *       exactly one timer call site in this file and it is unreachable until the response
 *       has resolved — and `?reveal=off` fills all four beats at once so a judge can
 *       prove in one keystroke that every value was already in the response.
 * R-M8  ZERO hardcoded identifiers. `GET /v1/demo/subjects` is called FIRST and every
 *       other request is addressed from the payload it returns. There is no identifier
 *       literal in this file: the deployed subjects are not the ones `scenario.py`
 *       derives, so a pasted identifier would produce a page that works today and lies
 *       tomorrow.
 * R-M10 Failure RENDERS. A failed GET puts its HTTP status and its path in the cell that
 *       needed it. A cell never falls back to a previously fetched value, a fixture value
 *       or a default. `NOT PROVEN` renders as NOT PROVEN with every `failures[]` string
 *       printed. A truthful red beats a fabricated green.
 * R-M12 `mount(element, { base, subjects })` is exported, so the operator-screens lead can
 *       host this loop inside a real operator screen with one script tag. Loaded from
 *       `/memory.html` the module mounts itself.
 *
 * THE SEAM WITH THE PAGE (memory-visible-plan.md §4)
 * -------------------------------------------------
 * The shell (`memory.html` / `memory.css`) owns the DOM and the styling; this module owns
 * the filling. They meet on `data-cell` attributes and nowhere else. Every id below is
 * filled from the source and pointer named beside it. An id inside this module's
 * namespaces (`store.` `retrieve.` `act.` `meta.` `annot.`) that is NOT in the grammar
 * below is painted with a loud error AND makes `mount()` throw; so does an id that is in
 * the grammar but whose pointer the response did not carry. A missing cell is loud, never
 * blank. Ids OUTSIDE those namespaces belong to another module and are left untouched:
 * `memory-verify.js` owns `verify.` and fills those cells itself when it hears this
 * module's `memory-loop:ready` event, from the ledger bytes this module fetched.
 *
 *   store.event.<member>            GET blocking-checks   /data/checks/0/precursor/<member>
 *                                   (`ref` is an alias for `external_ref`)
 *   store.edge.<member>             GET ancestry          /data/blame_edges/0/<member>
 *   store.closure.<member>          GET ancestry          /data/closure/<member>
 *                                   (`gen` → closure_gen, `ancestors` → ancestor_count)
 *   store.leaf.ingested.<member>    GET ledger            the leaf whose entry_kind is
 *   store.leaf.closure.<member>                           precursor_event_ingested /
 *                                                         blame_closure_computed —
 *                                                         FOUND BY entry_kind, never by
 *                                                         array index
 *   retrieve.sql.<name>             statement_refs        see SQL_DISCLOSURES; the text is
 *                                                         verbatim, the null case is stated
 *   retrieve.armed.<member>         GET blocking-checks   /data/checks/0/<member>
 *   retrieve.recall.<member>        GET recall-run        /data/<member>, and
 *                                                         /data/counts/<member> for n_*
 *   retrieve.match.severity         two responses         equality marker, no chip
 *   retrieve.match.virulence
 *   retrieve.match.closure_gen
 *   annot.gap.event_to_check        two columns           day gap, annotation, no chip
 *   annot.gap.recall_to_check       two columns           second gap, annotation, no chip
 *   act.beat<N>.<member>            POST gate-run         /data/beats/<N-1>/<member>,
 *                                                         including observed.<path>
 *   act.verdict                     POST gate-run         /data/verdict
 *   act.failures                    POST gate-run         /data/failures (every string)
 *   act.self_persisted              POST gate-run         /data/persistence_check/self_persisted
 *                                                         — NEVER `identical`, which is a
 *                                                         statement about the database and
 *                                                         not about this run
 *   act.single_transaction          POST gate-run         /data/transaction/single_transaction
 *   meta.received_at                client clock          when the POST body finished arriving
 *   meta.generated_at               POST gate-run         /data/generated_at
 *   meta.elapsed_ms                 POST gate-run         /data/elapsed_ms
 *
 * WHAT THIS MODULE WRITES INTO THE DOM, AND NOTHING ELSE
 * ------------------------------------------------------
 * Text nodes and elements it builds with `createElement`. No HTML string is ever assigned
 * or parsed by this module, so nothing a payload carries can become markup. Plus:
 *
 *   `<span class="chip" data-chip="…">`  inside a filled cell, when and only when the
 *                                        envelope claimed a chip for that pointer
 *   `data-error="true"`                  on a cell that got a status and a path instead
 *                                        of a value
 *   `data-state="refused|admitted|failed|pending"`  the shell's accent hook, set from the
 *                                        beat's own `outcome` and never from a guess
 *   `data-live="true"`                   on the `.col` a request is filling right now
 *   `data-filled="true"`                 on any cell this module has written to
 *   `data-memory-loop-error="…"`         on the mount root when a press failed loudly
 *   events `memory-loop:ready` and `memory-loop:gate-run`, both bubbling
 *
 * QUERY PARAMETERS
 * ----------------
 *   ?reveal=off   fill all four beats the instant the response resolves (R-M7.4).
 *   ?reveal=<ms>  set the reveal step; capped, and never rendered as a duration.
 *   ?base=<url>   point the client at another origin — accepted only for the page's own
 *                 origin or a loopback host, because a page on this origin that renders
 *                 JSON from somewhere else is exactly the fabricated exhibit this whole
 *                 plan exists to refuse.
 */

// ── Addressing ──────────────────────────────────────────────────────────────────────
//
// Path templates, filled from GET /v1/demo/subjects. The braces are the whole point:
// there is no identifier in this file, and `subjects.py` argues the rule better than this
// comment can — "the only component that can name a subject without inventing one is the
// component that holds the rows".

const ENDPOINTS = Object.freeze({
  subjects: '/v1/demo/subjects',
  checks: '/v1/permits/{permit_id}/blocking-checks',
  ancestry: '/v1/clauses/{clause_uuid}/ancestry',
  recall: '/v1/recall-runs/{run_id}',
  ledger: '/v1/ledger',
  gate: '/v1/demo/gate-run',
});

/** Which slot of the addressing payload each read is addressed by. */
const ADDRESSED_BY = Object.freeze({
  checks: 'permit_id',
  ancestry: 'clause_uuid',
  recall: 'run_id',
});

/** How a source is named in a failure sentence, so a red cell says which read failed. */
const SOURCE_LABEL = Object.freeze({
  subjects: 'GET /v1/demo/subjects',
  checks: 'GET blocking-checks',
  ancestry: 'GET ancestry',
  recall: 'GET recall-run',
  ledger: 'GET /v1/ledger',
  gate: 'POST /v1/demo/gate-run',
});

/** The two ledger leaves the STORE column is made of, addressed by `entry_kind`. */
const LEAF_KINDS = Object.freeze({
  ingested: 'precursor_event_ingested',
  closure: 'blame_closure_computed',
});

/**
 * The statement disclosures, each naming the source read and the `statement_refs` entry
 * to find in it BY ITS `object`. The text that lands on screen is whatever the server put
 * in `text` — or, where the server declined, the stated gap. Nothing here is a statement.
 */
const SQL_DISCLOSURES = Object.freeze({
  view: { source: 'ancestry', object: 'mainline.clause_blame_current' },
  recall: { source: 'recall', object: 'mainline_meas.recall_run' },
  disposition: { source: 'checks', object: 'mainline.disposition' },
  constraint: { source: 'ancestry', object: 'pg_catalog.pg_constraint' },
  blocking_check: { source: 'checks', object: 'mainline.blocking_check' },
  clause_version: { source: 'checks', object: 'mainline.clause_version' },
  event: { source: 'checks', object: 'mainline.event' },
  permit: { source: 'checks', object: 'mainline.permit' },
});

/** R-M6, verbatim: what the page says where the endpoint returned no statement text. */
const NO_STATEMENT_TEXT = 'statement text not returned by this endpoint';

/**
 * R-M5.2. Each marker compares one value from the armed obligation with one value from
 * the blame closure — two columns, two SEPARATE HTTP responses a judge can see in
 * devtools. The check's severity is not an independent number; it IS the closure's
 * number, because `fn_check_project` overwrites it on the way in.
 */
const MATCH_PAIRS = Object.freeze({
  severity: {
    left: ['checks', '/checks/0/severity'],
    right: ['ancestry', '/closure/max_severity'],
  },
  virulence: {
    left: ['checks', '/checks/0/virulence'],
    right: ['ancestry', '/closure/virulence'],
  },
  closure_gen: {
    left: ['checks', '/checks/0/closure_gen'],
    right: ['ancestry', '/closure/closure_gen'],
  },
});

/**
 * R-M4. Both operands are already on screen in their own chipped cells; the gap is
 * annotation, in its own register, naming itself as arithmetic over them.
 */
const GAP_PAIRS = Object.freeze({
  event_to_check: {
    unit: 'days',
    from: ['checks', '/checks/0/precursor/occurred_at'],
    to: ['checks', '/checks/0/materialised_at'],
  },
  occurred_to_materialised: {
    unit: 'days',
    from: ['checks', '/checks/0/precursor/occurred_at'],
    to: ['checks', '/checks/0/materialised_at'],
  },
  recall_to_check: {
    unit: 'seconds',
    from: ['recall', '/started_at'],
    to: ['checks', '/checks/0/materialised_at'],
  },
  started_to_materialised: {
    unit: 'seconds',
    from: ['recall', '/started_at'],
    to: ['checks', '/checks/0/materialised_at'],
  },
});

const GAP_NOTE = 'arithmetic over the two columns above; not a stored value';

/** Aliases, so the shell can use the short names §4 uses without losing the pointer. */
const EVENT_ALIASES = Object.freeze({ ref: 'external_ref' });
const CLOSURE_ALIASES = Object.freeze({ gen: 'closure_gen', ancestors: 'ancestor_count' });
const RECALL_ALIASES = Object.freeze({ policy: 'policy_version' });

/** Cell ids this module answers for. Anything else here is a defect, loudly. */
const OWNED_NAMESPACE = /^(store|retrieve|act|meta|annot)\./;

/**
 * The events this module dispatches on its mount root, both bubbling.
 *
 * `memory-loop:ready` is a CONTRACT, not a courtesy: `memory-verify.js` listens for it
 * (its own `READY_EVENT`), reads `detail.sources.ledger` and recomputes the two memory
 * leaves' hashes from the bytes that read returned. `memory-loop:gate-run` carries the
 * POST's slot for anything that wants to watch the ACT column settle.
 */
const READY_EVENT = 'memory-loop:ready';
const GATE_RUN_EVENT = 'memory-loop:gate-run';

/** How long one reveal step lasts. Never displayed, never labelled a latency (R-M7.2). */
const DEFAULT_REVEAL_MS = 650;
const MAX_REVEAL_MS = 4000;

// ── Failure kinds ───────────────────────────────────────────────────────────────────

/**
 * A read did not answer. This RENDERS in the cell that needed it, with the status and the
 * path (R-M10), and it does not throw: the page is still telling the truth.
 */
class SourceUnavailable extends Error {}

/**
 * The page and the payload disagree: an id nobody declared, or a pointer the response did
 * not carry. This renders AND throws, because a cell that cannot be filled is a defect in
 * this module or in the shell, and silence would let it ship.
 */
class CellContractError extends Error {}

// ── RFC 6901 ────────────────────────────────────────────────────────────────────────

const MISSING = Object.freeze({ found: false, value: undefined });

/** Split an RFC 6901 pointer into unescaped tokens. */
function pointerTokens(pointer) {
  if (pointer === '') return [];
  if (typeof pointer !== 'string' || pointer[0] !== '/') {
    throw new CellContractError(`${pointer} is not an RFC 6901 pointer`);
  }
  return pointer
    .slice(1)
    .split('/')
    .map((token) => token.replace(/~1/g, '/').replace(/~0/g, '~'));
}

/** Escape one token for use inside a pointer built from a cell id. */
function pointerToken(name) {
  return String(name).replace(/~/g, '~0').replace(/\//g, '~1');
}

/**
 * Read *pointer* out of *root*. Returns `{found, value}` — because `null` IS a value in
 * these payloads (`latency_ms` is a null column with a `db:column` chip on it) and
 * "absent" is a different sentence that has to be able to throw.
 */
export function readPointer(root, pointer) {
  let node = root;
  for (const token of pointerTokens(pointer)) {
    if (Array.isArray(node)) {
      if (!/^(0|[1-9][0-9]*)$/.test(token)) return MISSING;
      const index = Number(token);
      if (index >= node.length) return MISSING;
      node = node[index];
      continue;
    }
    if (node === null || typeof node !== 'object') return MISSING;
    if (!Object.prototype.hasOwnProperty.call(node, token)) return MISSING;
    node = node[token];
  }
  return { found: true, value: node };
}

/**
 * The chip the ENVELOPE claimed for *pointer*, or `null` (R-M3).
 *
 * Exact claims win over sweeping ones, which is the behaviour `envelope.Provenance`
 * documents from the emitting side: `blocking_checks` claims `/checks/0` as `db:column`
 * and `/checks/0/open` as `derived`, and the second must not be swallowed by the first.
 * Where a pointer is claimed by neither itself nor an ancestor, the answer is `null` and
 * the caller renders NO chip. This module never invents one, and there is no sixth chip.
 */
export function resolveChip(provenance, pointer) {
  if (!Array.isArray(provenance)) return null;
  let inherited = null;
  let inheritedLength = -1;
  for (const entry of provenance) {
    if (!entry || typeof entry.pointer !== 'string' || typeof entry.chip !== 'string') continue;
    if (entry.pointer === pointer) return entry.chip;
    if (pointer.startsWith(`${entry.pointer}/`) && entry.pointer.length > inheritedLength) {
      inherited = entry.chip;
      inheritedLength = entry.pointer.length;
    }
  }
  return inherited;
}

// ── Rendering values ────────────────────────────────────────────────────────────────

/**
 * A payload value as text. Strings pass through untouched — including the `SYNTHETIC — `
 * prefixes, which are column values and are not stripped, trimmed or styled away
 * (R-M13) — and `null` renders as the word `null`, because the column really is null and
 * a blank cell would be a different claim.
 */
function textOf(value) {
  if (value === null) return 'null';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  return JSON.stringify(value);
}

/** Thousands separators, computed here rather than by a locale, so the page is stable. */
function grouped(n) {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// ── Painting ────────────────────────────────────────────────────────────────────────

function clear(element) {
  element.textContent = '';
  element.removeAttribute('data-error');
  element.removeAttribute('data-state');
}

/**
 * Write one rendering into one element: the text, then the chip the envelope supplied.
 * The chip is a child `<span class="chip" data-chip="...">` so the shell can style it by
 * attribute; where the envelope claimed nothing, nothing is added.
 */
function paint(element, rendering) {
  clear(element);
  element.append(document.createTextNode(rendering.text));
  if (rendering.chip) {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.dataset.chip = rendering.chip;
    chip.textContent = rendering.chip;
    element.append(' ', chip);
  }
  element.dataset.filled = 'true';
}

/** Paint a failure: the status and the path, in the cell that needed them (R-M10). */
function paintFailure(element, message) {
  clear(element);
  element.append(document.createTextNode(message));
  element.dataset.error = 'true';
  element.dataset.state = 'failed';
  element.dataset.filled = 'true';
}

/**
 * Every string in `failures[]`, printed — R-M10. An empty array says so in words rather
 * than going blank, because a blank cell and a clean run must not look the same.
 *
 * A list element gets list items; anything else (the shell's `<p class="verdict__failures">`)
 * gets one numbered span per failure with a line break between, which needs no cooperation
 * from a stylesheet to stay readable.
 */
function paintFailures(element, failures) {
  clear(element);
  element.dataset.count = String(failures.length);
  element.dataset.filled = 'true';
  if (failures.length === 0) {
    element.append(document.createTextNode('failures[] is empty (0)'));
    return;
  }
  const tag = element.tagName;
  if (tag === 'UL' || tag === 'OL') {
    for (const failure of failures) {
      const item = document.createElement('li');
      item.textContent = String(failure);
      element.append(item);
    }
    return;
  }
  failures.forEach((failure, index) => {
    if (index > 0) element.append(document.createElement('br'));
    const line = document.createElement('span');
    line.className = 'failure';
    line.textContent = `${index + 1}. ${failure}`;
    element.append(line);
  });
}

/**
 * The shell offers two hooks it styles and no client sets yet (`memory.css`, "THE CONTRACT
 * WITH THE CLIENT"). Both are set here because both are true statements about this page:
 * `data-live` marks the column a request is filling RIGHT NOW — plan §3's "marker naming
 * which column is live" — and `data-state` gives a refusal the accent it earns.
 */
function setLive(root, column, live) {
  const element = root.querySelector(`[data-column="${column}"]`);
  if (!element) return;
  if (live) element.setAttribute('data-live', 'true');
  else element.removeAttribute('data-live');
}

/** `refused` / `admitted` / `failed` — from the beat's own outcome, never from a guess. */
function beatState(outcome) {
  if (outcome === 'refused') return 'refused';
  if (outcome === 'admitted') return 'admitted';
  if (outcome === 'error' || outcome === 'skipped') return 'failed';
  return null;
}

// ── HTTP ────────────────────────────────────────────────────────────────────────────

/**
 * One GET. Never throws: it returns either the envelope or a failure sentence carrying
 * the HTTP status and the path, which is what the cells that needed it will render.
 */
async function getJson(base, path) {
  const url = `${base}${path}`;
  let response;
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: { accept: 'application/json' },
      cache: 'no-store',
      credentials: 'omit',
    });
  } catch (cause) {
    const detail = cause && cause.message ? cause.message : 'request failed';
    return { state: 'failed', failure: `GET ${path} — no response (${detail})` };
  }
  const text = await response.text();
  let body = null;
  try {
    body = JSON.parse(text);
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail =
      body && body.error && typeof body.error.detail === 'string' ? ` — ${body.error.detail}` : '';
    return { state: 'failed', failure: `HTTP ${response.status} GET ${path}${detail}` };
  }
  if (body === null || typeof body !== 'object') {
    return {
      state: 'failed',
      failure: `HTTP ${response.status} GET ${path} — the body did not parse as JSON`,
    };
  }
  return { state: 'ok', envelope: body, status: response.status, path };
}

// ── The addressing payload ──────────────────────────────────────────────────────────

/**
 * Turn the subjects envelope into "which identifier addresses which read", including the
 * reason a subject is missing when it is — `subjects.py` puts that reason in `absent[]`,
 * and it is the database's account of its own gap rather than ours.
 */
function addressFrom(slot) {
  if (slot.state !== 'ok') {
    return { ok: false, failure: `${SOURCE_LABEL.subjects} failed: ${slot.failure}` };
  }
  const data = slot.envelope && typeof slot.envelope === 'object' ? slot.envelope.data : null;
  if (!data || typeof data !== 'object') {
    return { ok: false, failure: `${SOURCE_LABEL.subjects} carried no data object` };
  }
  const absent = Array.isArray(data.absent) ? data.absent : [];
  return {
    ok: true,
    slot(name) {
      const value = data[name];
      return typeof value === 'string' && value !== '' ? value : null;
    },
    reason(subject) {
      const entry = absent.find((item) => item && item.subject === subject);
      return entry && typeof entry.reason === 'string'
        ? `${SOURCE_LABEL.subjects} reports ${subject} absent from ${entry.relation}: ${entry.reason}`
        : `${SOURCE_LABEL.subjects} carried no ${subject} identifier`;
    },
  };
}

/** Which `absent[].subject` names the slot a read is addressed by. */
const SLOT_SUBJECT = Object.freeze({
  permit_id: 'permit',
  clause_uuid: 'clause',
  run_id: 'recall_run',
});

/** Fetch one addressed read, or turn the missing identifier into the failure to render. */
function fetchAddressed(base, key, address) {
  if (!address.ok) {
    return Promise.resolve({
      state: 'failed',
      failure: `${address.failure} — nothing to address ${SOURCE_LABEL[key]} with`,
    });
  }
  const slotName = ADDRESSED_BY[key];
  const identifier = address.slot(slotName);
  if (identifier === null) {
    return Promise.resolve({ state: 'failed', failure: address.reason(SLOT_SUBJECT[slotName]) });
  }
  const path = ENDPOINTS[key].replace(`{${slotName}}`, encodeURIComponent(identifier));
  return getJson(base, path);
}

/** The ledger is site-scoped, and the site code comes from the same addressing payload. */
function fetchLedger(base, address) {
  if (!address.ok) {
    return Promise.resolve({
      state: 'failed',
      failure: `${address.failure} — nothing to address ${SOURCE_LABEL.ledger} with`,
    });
  }
  const siteCode = address.slot('site_code');
  const path =
    siteCode === null
      ? ENDPOINTS.ledger
      : `${ENDPOINTS.ledger}?site_code=${encodeURIComponent(siteCode)}`;
  return getJson(base, path);
}

// ── Reading a cell out of a response ────────────────────────────────────────────────

function envelopeOf(sources, key) {
  const slot = sources[key];
  if (!slot) throw new SourceUnavailable(`${SOURCE_LABEL[key]} was never requested`);
  if (slot.state !== 'ok') throw new SourceUnavailable(slot.failure);
  return slot.envelope;
}

/** One value and its chip, both out of the same envelope, addressed by one pointer. */
function fromEnvelope(sources, key, pointer) {
  const envelope = envelopeOf(sources, key);
  const hit = readPointer(envelope.data, pointer);
  if (!hit.found) {
    throw new CellContractError(`${SOURCE_LABEL[key]} carried no value at /data${pointer}`);
  }
  return {
    text: textOf(hit.value),
    chip: resolveChip(envelope.provenance, pointer),
    value: hit.value,
  };
}

/** The same, with the payload's own unit named beside the number. */
function millisecondsFrom(sources, key, pointer) {
  const rendering = fromEnvelope(sources, key, pointer);
  if (typeof rendering.value !== 'number') return rendering;
  return { ...rendering, text: `${rendering.text} ms` };
}

/**
 * A statement disclosure (R-M6). The text is whatever the server returned, byte for byte:
 * never retyped, never reformatted. Where the server returned none, the gap is STATED —
 * and it is forbidden to paste a statement from a migration or a seed into it.
 */
function fromStatementRefs(sources, key, object) {
  const envelope = envelopeOf(sources, key);
  const refs = envelope.statement_refs;
  if (!Array.isArray(refs)) {
    throw new CellContractError(`${SOURCE_LABEL[key]} carried no statement_refs array`);
  }
  const ref = refs.find((entry) => entry && entry.object === object);
  if (!ref) {
    throw new CellContractError(
      `${SOURCE_LABEL[key]} carried no statement_ref whose object is ${object}`
    );
  }
  if (typeof ref.text === 'string') return { text: ref.text, chip: null, value: ref.text };
  return {
    text: `${ref.kind} ${ref.object} — ${NO_STATEMENT_TEXT}`,
    chip: null,
    value: null,
  };
}

/** The ledger leaf whose `entry_kind` is *kind* — found by kind, never by array index. */
function leafIndex(sources, kind) {
  const envelope = envelopeOf(sources, 'ledger');
  const leaves = envelope.data && Array.isArray(envelope.data.leaves) ? envelope.data.leaves : null;
  if (leaves === null) {
    throw new CellContractError(`${SOURCE_LABEL.ledger} carried no leaves array`);
  }
  const index = leaves.findIndex((leaf) => leaf && leaf.entry_kind === kind);
  if (index < 0) {
    throw new CellContractError(
      `${SOURCE_LABEL.ledger} returned no leaf whose entry_kind is ${kind}`
    );
  }
  return index;
}

/** R-M5.2 — the same value, arriving in two responses, marked as matching or not. */
function matchMarker(sources, name) {
  const pair = MATCH_PAIRS[name];
  const left = fromEnvelope(sources, pair.left[0], pair.left[1]);
  const right = fromEnvelope(sources, pair.right[0], pair.right[1]);
  const same = Object.is(left.value, right.value);
  return {
    text: same
      ? `match · ${left.text} = ${right.text}`
      : `DIFFERS · ${left.text} ≠ ${right.text}`,
    chip: null,
  };
}

/** R-M4 — a gap between two rendered columns, in the annotation register, with no chip. */
function gapAnnotation(sources, name) {
  const pair = GAP_PAIRS[name];
  const from = fromEnvelope(sources, pair.from[0], pair.from[1]);
  const to = fromEnvelope(sources, pair.to[0], pair.to[1]);
  const started = Date.parse(String(from.value));
  const ended = Date.parse(String(to.value));
  if (Number.isNaN(started) || Number.isNaN(ended)) {
    throw new CellContractError(
      `the gap ${name} needs two timestamps and read ${from.text} → ${to.text}`
    );
  }
  const millis = ended - started;
  const measure =
    pair.unit === 'days'
      ? `${grouped(Math.floor(millis / 86400000))} days`
      : `${grouped(millis / 1000)} seconds`;
  return { text: `${measure} apart — ${GAP_NOTE}`, chip: null };
}

/**
 * Resolve one `data-cell` id into `{text, chip}`.
 *
 * Throws `SourceUnavailable` when the read that would have answered it did not answer —
 * the caller renders that in the cell. Throws `CellContractError` when the id is not one
 * this module answers for, or when the response carried no value at the pointer — the
 * caller renders THAT too, and then throws, because it is a defect rather than an outage.
 */
function renderCell(id, sources) {
  let match;

  if ((match = /^store\.event\.(.+)$/.exec(id))) {
    const member = EVENT_ALIASES[match[1]] ?? match[1];
    return fromEnvelope(sources, 'checks', `/checks/0/precursor/${pointerToken(member)}`);
  }
  if ((match = /^store\.edge\.(.+)$/.exec(id))) {
    return fromEnvelope(sources, 'ancestry', `/blame_edges/0/${pointerToken(match[1])}`);
  }
  if ((match = /^store\.closure\.(.+)$/.exec(id))) {
    const member = CLOSURE_ALIASES[match[1]] ?? match[1];
    return fromEnvelope(sources, 'ancestry', `/closure/${pointerToken(member)}`);
  }
  if ((match = /^store\.leaf\.([a-z_]+)\.(.+)$/.exec(id))) {
    const named = LEAF_KINDS[match[1]];
    const kind = named ?? (Object.values(LEAF_KINDS).includes(match[1]) ? match[1] : null);
    if (kind === null) {
      throw new CellContractError(
        `store.leaf.${match[1]} names no leaf; the panel shows ${Object.keys(LEAF_KINDS).join(' and ')}`
      );
    }
    const index = leafIndex(sources, kind);
    return fromEnvelope(sources, 'ledger', `/leaves/${index}/${pointerToken(match[2])}`);
  }

  if ((match = /^retrieve\.sql\.(.+)$/.exec(id))) {
    const disclosure = SQL_DISCLOSURES[match[1]];
    if (!disclosure) {
      throw new CellContractError(
        `retrieve.sql.${match[1]} names no disclosure; declared: ${Object.keys(SQL_DISCLOSURES).join(', ')}`
      );
    }
    return fromStatementRefs(sources, disclosure.source, disclosure.object);
  }
  if ((match = /^retrieve\.armed\.(.+)$/.exec(id))) {
    return fromEnvelope(sources, 'checks', `/checks/0/${pointerToken(match[1])}`);
  }
  if ((match = /^retrieve\.recall\.counts\.(.+)$/.exec(id))) {
    return fromEnvelope(sources, 'recall', `/counts/${pointerToken(match[1])}`);
  }
  if ((match = /^retrieve\.recall\.(n_.+)$/.exec(id))) {
    return fromEnvelope(sources, 'recall', `/counts/${pointerToken(match[1])}`);
  }
  if ((match = /^retrieve\.recall\.(.+)$/.exec(id))) {
    const member = RECALL_ALIASES[match[1]] ?? match[1];
    return fromEnvelope(sources, 'recall', `/${pointerToken(member)}`);
  }
  if ((match = /^retrieve\.match\.(.+)$/.exec(id))) {
    if (!MATCH_PAIRS[match[1]]) {
      throw new CellContractError(
        `retrieve.match.${match[1]} names no pair; declared: ${Object.keys(MATCH_PAIRS).join(', ')}`
      );
    }
    return matchMarker(sources, match[1]);
  }

  if ((match = /^(?:annot|store|retrieve)\.gap\.(.+)$/.exec(id))) {
    if (!GAP_PAIRS[match[1]]) {
      throw new CellContractError(
        `gap ${match[1]} names no pair of columns; declared: ${Object.keys(GAP_PAIRS).join(', ')}`
      );
    }
    return gapAnnotation(sources, match[1]);
  }

  if ((match = /^act\.beat\.?([1-9][0-9]*)\.(.+)$/.exec(id))) {
    const ordinal = Number(match[1]);
    const path = match[2].split('.').map(pointerToken).join('/');
    const pointer = `/beats/${ordinal - 1}/${path}`;
    return match[2] === 'elapsed_ms'
      ? millisecondsFrom(sources, 'gate', pointer)
      : fromEnvelope(sources, 'gate', pointer);
  }
  if (id === 'act.verdict') return fromEnvelope(sources, 'gate', '/verdict');
  if (id === 'act.self_persisted') {
    // NEVER `identical`: that reading is ten unscoped whole-table counts and answers
    // "did the database move". This one answers "did anything THIS RUN wrote survive",
    // which is the claim the panel makes and the one the verdict keys on.
    return fromEnvelope(sources, 'gate', '/persistence_check/self_persisted');
  }
  if (id === 'act.single_transaction') {
    return fromEnvelope(sources, 'gate', '/transaction/single_transaction');
  }
  if (id === 'act.failures') {
    const envelope = envelopeOf(sources, 'gate');
    const hit = readPointer(envelope.data, '/failures');
    if (!hit.found || !Array.isArray(hit.value)) {
      throw new CellContractError(`${SOURCE_LABEL.gate} carried no failures array at /data/failures`);
    }
    return { failures: hit.value.map((entry) => String(entry)) };
  }

  if (id === 'meta.generated_at') return fromEnvelope(sources, 'gate', '/generated_at');
  if (id === 'meta.elapsed_ms') return millisecondsFrom(sources, 'gate', '/elapsed_ms');
  if (id === 'meta.received_at') {
    const slot = sources.gate;
    if (!slot) throw new SourceUnavailable(`${SOURCE_LABEL.gate} was never requested`);
    if (slot.state !== 'ok') throw new SourceUnavailable(slot.failure);
    // The client's own receipt clock, per R-M7.1. It is not a database timestamp and it
    // carries no chip; the shell's disclosure line says whose clock it is.
    return { text: `${slot.receivedAt.toISOString().slice(11)} · client clock`, chip: null };
  }

  throw new CellContractError(
    `${id} is not a data cell this module fills; see the registry at the top of memory-loop.js`
  );
}

/** Which cells this module fills from the POST rather than from the four GETs. */
function isActCell(id) {
  return id.startsWith('act.') || id.startsWith('meta.');
}

// ── Filling ─────────────────────────────────────────────────────────────────────────

/**
 * Fill every element carrying *id*. Returns a breach sentence when the id or the pointer
 * is a defect, and `null` otherwise — including when the read simply did not answer,
 * which is rendered rather than raised.
 */
function fill(id, elements, sources) {
  let rendering;
  try {
    rendering = renderCell(id, sources);
  } catch (error) {
    const message =
      error instanceof CellContractError
        ? `CELL ${id}: ${error.message}`
        : error instanceof SourceUnavailable
          ? error.message
          : `CELL ${id}: ${error && error.message ? error.message : String(error)}`;
    for (const element of elements) paintFailure(element, message);
    return error instanceof SourceUnavailable ? null : message;
  }
  for (const element of elements) {
    if (rendering.failures) paintFailures(element, rendering.failures);
    else paint(element, rendering);
  }
  return null;
}

/** Every `data-cell` under *root*, grouped by id. */
function collectCells(root) {
  const cells = new Map();
  const found = [...root.querySelectorAll('[data-cell]')];
  if (root.hasAttribute && root.hasAttribute('data-cell')) found.unshift(root);
  for (const element of found) {
    const id = element.getAttribute('data-cell');
    if (!id) continue;
    if (!cells.has(id)) cells.set(id, []);
    cells.get(id).push(element);
  }
  return cells;
}

// ── The reveal ──────────────────────────────────────────────────────────────────────

/**
 * How long one reveal step lasts, from `?reveal=`. `off` (or `0`) means the four beats
 * are filled the instant the response resolves — R-M7.4, which lets a judge with devtools
 * open prove in one keystroke that every value was already in the one response.
 */
function revealStep(search, override) {
  if (typeof override === 'number') return override > 0 ? Math.min(override, MAX_REVEAL_MS) : 0;
  const raw = new URLSearchParams(search).get('reveal');
  if (raw === null) return DEFAULT_REVEAL_MS;
  if (raw === 'off' || raw === '0' || raw === 'false' || raw === 'none') return 0;
  const asked = Number(raw);
  return Number.isFinite(asked) && asked > 0 ? Math.min(asked, MAX_REVEAL_MS) : DEFAULT_REVEAL_MS;
}

// ── The base URL ────────────────────────────────────────────────────────────────────

/**
 * Where `/v1/*` lives. Same origin by default — the deployed Function URL serves this page
 * and the API, and `app._response` deliberately sets no `access-control-allow-origin`, so
 * same origin is the only arrangement a browser can read at all.
 *
 * `?base=` exists for local development and is restricted to this page's own origin or a
 * loopback host ON PURPOSE: a page on this origin rendering JSON fetched from somewhere
 * else would be precisely the fabricated exhibit this plan refuses.
 */
function resolveBase(explicit, here) {
  if (typeof explicit === 'string') return explicit.replace(/\/+$/, '');
  const asked = new URLSearchParams(here.search).get('base');
  if (!asked) return '';
  const candidate = new URL(asked, here.href);
  const loopback = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(candidate.hostname);
  if (candidate.origin !== here.origin && !loopback) {
    throw new Error(
      `?base=${asked} points at ${candidate.origin}, which is neither this page's origin ` +
        'nor a loopback host. This page renders only what its own kernel answered.'
    );
  }
  return `${candidate.origin}${candidate.pathname}`.replace(/\/+$/, '');
}

// ── mount ───────────────────────────────────────────────────────────────────────────

/**
 * Make *element* a client of the kernel.
 *
 * @param {Element} element  the subtree carrying the `data-cell` attributes.
 * @param {{base?: string, subjects?: object, revealMs?: number}} [options]
 *   `base` overrides the origin `/v1/*` is fetched from; `subjects` lets a host page hand
 *   over an addressing payload it has already fetched (envelope or bare data), which is
 *   the one thing an operator screen is likely to have in hand already; `revealMs`
 *   overrides `?reveal=`.
 * @returns {Promise<object>} a controller: `{ base, cells, sources, runGate, reload }`.
 * @throws when a `data-cell` id in this module's namespaces is unknown, or when a read
 *   answered and carried no value at the pointer that cell declares. Both are painted
 *   into the page first, so the failure is on screen as well as on the console.
 */
export async function mount(element, options = {}) {
  const root = element ?? document.body;
  const here = typeof location === 'undefined' ? new URL('http://localhost/') : location;
  const base = resolveBase(options.base, here);
  const cells = collectCells(root);
  const sources = {};
  const breaches = [];

  const mine = new Map();
  for (const [id, elements] of cells) {
    // Ids outside this module's namespaces belong to another client on the same page —
    // the recomputation module owns `verify.` — and are not this module's to touch.
    if (!OWNED_NAMESPACE.test(id)) continue;
    mine.set(id, elements);
  }

  const controller = {
    base,
    cells: mine,
    sources,
    element: root,
    runGate: null,
    inflight: false,
  };

  // The button is wired BEFORE anything is fetched, so a read that fails still leaves a
  // page whose ACT column works — the four beats do not depend on the four GETs.
  const button = findButton(root);
  const runGate = () => runGateOnce(root, controller, button, options);
  controller.runGate = runGate;
  // One listener per control, even if this page mounts the loop twice: two listeners on
  // one button would send two POSTs for one press, and this endpoint is a real request
  // against the real kernel rather than something to fire speculatively.
  if (button && button.dataset.loopWired !== 'true') {
    button.dataset.loopWired = 'true';
    button.addEventListener('click', () => {
      runGate().catch((error) => report(root, error));
    });
  }

  setLive(root, 'store', true);
  setLive(root, 'retrieve', true);

  // R-M8: the addressing payload is asked for FIRST, and everything else is addressed out
  // of what it returned. Nothing below names a subject this file knew before it ran.
  sources.subjects = options.subjects
    ? { state: 'ok', envelope: normaliseSubjects(options.subjects) }
    : await getJson(base, ENDPOINTS.subjects);

  const address = addressFrom(sources.subjects);
  const [checks, ancestry, recall, ledger] = await Promise.all([
    fetchAddressed(base, 'checks', address),
    fetchAddressed(base, 'ancestry', address),
    fetchAddressed(base, 'recall', address),
    fetchLedger(base, address),
  ]);
  sources.checks = checks;
  sources.ancestry = ancestry;
  sources.recall = recall;
  sources.ledger = ledger;

  for (const [id, elements] of mine) {
    if (isActCell(id)) continue; // filled on press, from the one POST
    const breach = fill(id, elements, sources);
    if (breach) breaches.push(breach);
  }
  setLive(root, 'store', false);
  setLive(root, 'retrieve', false);

  // THE READY EVENT IS LOAD-BEARING, not a courtesy. `memory-verify.js` attaches
  // `attachVerification(document)` on this page and answers `memory-loop:ready` by
  // recomputing the two memory leaves' hashes from `canon_bytes_b64` and painting its own
  // `verify.leaf.*` cells. It makes no request of its own, so the ledger read it verifies
  // is THIS one — which is the point: the browser re-derives the hash of the bytes the
  // judge just watched arrive. It bubbles, and `detail.sources` carries the slot shape
  // `{state, failure, envelope}` that module reads. Neither the shape nor the name changes
  // without the other file.
  root.dispatchEvent(
    new CustomEvent(READY_EVENT, { bubbles: true, detail: { base, sources } })
  );

  if (breaches.length > 0) {
    throw new CellContractError(
      `memory-loop: ${breaches.length} data cell(s) could not be filled — ${breaches.join(' | ')}`
    );
  }
  return controller;
}

/** A host page may hand over the envelope or just its `data`; both are addressing. */
function normaliseSubjects(supplied) {
  if (supplied && typeof supplied === 'object' && supplied.data && typeof supplied.data === 'object') {
    return supplied;
  }
  return { data: supplied, provenance: [] };
}

/**
 * The control that runs the gate. The shell's own button wins; where the shell declares
 * none, one is created so the page is filmable standing alone (R-M12).
 */
function findButton(root) {
  const declared = root.querySelector('[data-action="gate-run"]');
  if (declared) return declared;
  // A lone unlabelled button is unambiguous and is adopted. Several are not, and adopting
  // one of them would wire a real POST to a control somebody meant for something else.
  const buttons = root.querySelectorAll('button');
  if (buttons.length === 1) {
    buttons[0].dataset.action = 'gate-run';
    return buttons[0];
  }
  const host = root.querySelector('[data-column="act"]') ?? root;
  const created = document.createElement('button');
  created.type = 'button';
  created.className = 'act-run';
  created.dataset.action = 'gate-run';
  created.textContent = 'RUN THE GATE';
  host.append(created);
  return created;
}

function report(root, error) {
  if (root && root.setAttribute) {
    root.setAttribute('data-memory-loop-error', error && error.message ? error.message : String(error));
  }
  console.error('[memory-loop]', error);
}

// ── The ACT column: one POST, four beats ────────────────────────────────────────────

/**
 * Press once, POST once, and fill the ACT column from the ONE response.
 *
 * The four beats already happened inside one `SERIALIZABLE` transaction before this
 * function saw a byte of them; three POSTs would have destroyed
 * `transaction.single_transaction`, which is the property the column exists to show. The
 * reveal below is a display order over values that had all arrived — it is constructed
 * inside the scope holding the parsed body, there is exactly one timer call site in this
 * file, and it cannot run before the response resolves or gate a request.
 */
async function runGateOnce(root, controller, button, options) {
  if (controller.inflight) return;
  controller.inflight = true;
  if (button) button.disabled = true;

  // Every ACT cell is emptied before the request goes out. A second press must never leave
  // a value from the first one on screen while a new run is in flight (R-M10), and an empty
  // cell is exactly what the shell renders as an em dash.
  const actCells = [...controller.cells].filter(([id]) => isActCell(id));
  for (const [id, elements] of actCells) {
    for (const element of elements) {
      clear(element);
      element.dataset.state = 'pending';
      if (id === 'act.verdict') {
        element.append(document.createTextNode(`${SOURCE_LABEL.gate} — awaiting response`));
      }
    }
  }
  setLive(root, 'act', true);

  const path = ENDPOINTS.gate;
  let response;
  let text;
  try {
    response = await fetch(`${controller.base}${path}`, {
      method: 'POST',
      headers: { accept: 'application/json', 'content-type': 'application/json' },
      body: '{}',
      cache: 'no-store',
      credentials: 'omit',
    });
    text = await response.text();
  } catch (cause) {
    const detail = cause && cause.message ? cause.message : 'request failed';
    controller.sources.gate = { state: 'failed', failure: `POST ${path} — no response (${detail})` };
    finishGate(root, controller, actCells, button);
    return;
  }

  // ── The response has RESOLVED. Everything below holds the parsed body. ─────────────
  const receivedAt = new Date();
  let body = null;
  try {
    body = JSON.parse(text);
  } catch {
    body = null;
  }
  const data = body && typeof body === 'object' ? body.data : null;
  if (!data || typeof data !== 'object') {
    controller.sources.gate = {
      state: 'failed',
      failure: `HTTP ${response.status} POST ${path} — the body carried no data object`,
    };
    finishGate(root, controller, actCells, button);
    return;
  }
  controller.sources.gate = {
    state: 'ok',
    envelope: body,
    status: response.status,
    path,
    receivedAt,
  };

  const beats = Array.isArray(data.beats) ? data.beats : [];
  const breaches = [];
  const beatOf = (id) => {
    const match = /^act\.beat\.?([1-9][0-9]*)\./.exec(id);
    return match ? Number(match[1]) : null;
  };
  const paintGroup = (predicate) => {
    for (const [id, elements] of actCells) {
      if (!predicate(id)) continue;
      const breach = fill(id, elements, controller.sources);
      if (breach) breaches.push(breach);
      const ordinal = beatOf(id);
      const state = ordinal === null ? null : beatState(beats[ordinal - 1]?.outcome);
      for (const element of elements) {
        // A refused beat is accented as refused because the payload says it was refused.
        if (state !== null && !element.dataset.error) element.dataset.state = state;
        // The status a body arrived with, beside the verdict that body carried. The
        // verdict is still the payload's own word — it is not overwritten by the status.
        if (id === 'act.verdict' && !response.ok) {
          element.prepend(document.createTextNode(`HTTP ${response.status} · `));
        }
      }
    }
  };

  // The receipt line goes up FIRST, before any beat, so the page states when the single
  // response arrived and every beat that appears afterwards is visibly older than it.
  paintGroup((id) => id.startsWith('meta.'));

  const step = revealStep(pageSearch(), options.revealMs);
  const finalCells = (id) => beatOf(id) === null && !id.startsWith('meta.');
  if (step === 0 || beats.length === 0) {
    // `?reveal=off`, R-M7.4: all four beats at once, from the response already in hand.
    paintGroup((id) => beatOf(id) !== null);
    paintGroup(finalCells);
    finishGate(root, controller, actCells, button, breaches);
    return;
  }

  const reveal = (ordinal) => {
    paintGroup((id) => beatOf(id) === ordinal);
    if (ordinal < beats.length) {
      // THE ONLY TIMER IN THIS FILE. It is lexically inside the scope that holds the
      // parsed body, it cannot be reached until the response has resolved, and it gates
      // no request — it orders the painting of values that have all already arrived.
      setTimeout(() => reveal(ordinal + 1), step);
      return;
    }
    paintGroup(finalCells);
    try {
      finishGate(root, controller, actCells, button, breaches);
    } catch (error) {
      report(root, error);
    }
  };
  reveal(1);
}

/** The page's own query string, read at the moment it is needed and nowhere cached. */
function pageSearch() {
  return typeof location === 'undefined' ? '' : location.search;
}

function finishGate(root, controller, actCells, button, breaches = []) {
  controller.inflight = false;
  if (button) button.disabled = false;
  setLive(root, 'act', false);
  if (controller.sources.gate && controller.sources.gate.state !== 'ok') {
    // R-M10: the status and the path go in every cell that needed them. No cell keeps a
    // value from an earlier press, a fixture or a default.
    for (const [id, elements] of actCells) {
      const breach = fill(id, elements, controller.sources);
      if (breach) breaches.push(breach);
    }
  }
  root.dispatchEvent(
    new CustomEvent(GATE_RUN_EVENT, {
      bubbles: true,
      detail: { source: controller.sources.gate },
    })
  );
  if (breaches.length > 0) {
    throw new CellContractError(
      `memory-loop: ${breaches.length} ACT cell(s) could not be filled — ${breaches.join(' | ')}`
    );
  }
}

// ── Self-mount ──────────────────────────────────────────────────────────────────────
//
// `/memory.html` loads this file with one `<script type="module">` and needs no code of
// its own. Any OTHER page — an operator screen hosting the loop — imports `mount` and
// calls it, so the check below is on the page, not on the presence of the element.

const SELF_MOUNT_PAGE = 'memory.html';

if (
  typeof document !== 'undefined' &&
  typeof location !== 'undefined' &&
  location.pathname.endsWith(SELF_MOUNT_PAGE)
) {
  const start = () => {
    const host = document.querySelector('[data-memory-panel]') ?? document.body;
    mount(host).catch((error) => report(host, error));
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
}
