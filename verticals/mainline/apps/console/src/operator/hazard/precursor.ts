// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * HSG250 Figure 1 element 6 — HAZARD IDENTIFICATION, precursor half.
 *
 * WHAT THIS FILE RENDERS, AND WHERE EVERY CHARACTER OF IT CAME FROM
 * ------------------------------------------------------------------
 * The event that caused this obligation to exist, and the two ancestry facts that
 * connect it to the clause the permit relies on. Every value below arrived over HTTP in
 * the caller's page load. Nothing here composes a number, a digest, a SQLSTATE or an
 * instant, and this file contains no UUID, no hash and no timestamp literal — the one
 * literal string it does carry is a SOURCE CITATION into this repository, rendered in a
 * visually distinct register with the words "not from this response" attached, because
 * `r2-memory.md` §4.3 requires exactly that form for it and forbids showing it as data.
 *
 * THE DATE IS 2019 AND THAT IS THE POINT. `mainline.event.occurred_at` for `DEMO-INC-0001`
 * is `2019-03-14T06:20:00Z`, seeded deliberately outside any GC window. It is rendered as
 * the emitted ISO instant AND as a UTC-pinned human form; the human form is computed with
 * `Intl.DateTimeFormat(..., { timeZone: 'UTC' })`, never with a locale-default zone, so a
 * machine in Sydney and a machine in London render the same characters. The only "2024"
 * anywhere near this story lives inside a STAGED propagation payload this card never
 * reads and must never narrate.
 *
 * THIS MODULE IS THE LEAF OF THE HAZARD CARD'S MODULE GRAPH.
 * `memory-loop.ts` imports its primitives from here and `HazardCard.ts` imports both, so
 * the three files form a strict DAG with no cycle. The primitives live here rather than
 * in a fifth file because operator-systems-plan §4 enumerates this worker's paths and a
 * new one would take a path no worker owns.
 *
 * THE CHIP RULE IS W2'S, NOT OURS. `kernel/envelope.ts` `chipFor()` is an EXACT pointer
 * match and its module note forbids ancestor lookup: widening a claim on the client is
 * the console composing an evidentiary assertion. So this file never asks for a chip at a
 * pointer the payload did not claim. `GET /v1/permits/{id}/blocking-checks` claims
 * `db:column` at `/checks/0` — the whole object — and `derived` at `/checks/0/open` and
 * `/checks/0/disposition_id`. The object-level claim therefore renders ON THE BLOCK, with
 * the pointer it was claimed at printed beside it, and the fields inside render bare. A
 * reader can Ctrl-F that pointer in the raw payload; that is the whole design.
 */

import type { ProvChip } from '../kernel/envelope';

// ─────────────────────────────────────────────────────────────────────────────────────
// SHARED PRIMITIVES — imported by memory-loop.ts and HazardCard.ts
// ─────────────────────────────────────────────────────────────────────────────────────

/**
 * A provenance claim the payload actually made, at the exact pointer it made it.
 *
 * The pointer is carried, not just the chip, because the pointer is what makes the chip
 * checkable: `db:column @ /counts/n_blocking` can be grepped in the response body and
 * `db:column` on its own cannot.
 */
export interface ChipClaim {
  readonly kind: ProvChip;
  readonly pointer: string;
}

/** Exact-match chip lookup over one envelope. Supplied by `HazardCard.ts` from `chipFor`. */
export type ChipLookup = (pointer: string) => ChipClaim | null;

/**
 * Where one block of values came from, as observed on this page load.
 *
 * `observedAt` is the envelope's `observed_at` — the READ API's own clock at emission —
 * and never the browser's. A card that stamped its own clock on a server's answer would
 * be inventing the one field that says how stale the answer is.
 */
export interface SourceRef {
  readonly resource: string;
  readonly method: string;
  readonly path: string;
  readonly status: number;
  readonly wireBytes: number;
  readonly observedAt: string | null;
}

/** `document.createElement` with a class and text. `textContent` only — never `innerHTML`. */
export function el(tag: string, className?: string, text?: string): HTMLElement {
  const node = document.createElement(tag);
  if (className !== undefined) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

/**
 * One instant, in UTC, in a form an operator reads — `14 March 2019 06:20 UTC`.
 *
 * The locale is pinned to `en-GB` and the zone to `UTC` on purpose. The alternative,
 * `toLocaleString()` with host defaults, renders a different day either side of midnight
 * depending on where the reader's laptop is, and a permit-to-work screen that disagrees
 * with itself about the date of an incident is worse than one that shows the raw ISO.
 * Returns `null` for a value the payload did not carry or that is not a parseable
 * instant: absence renders as absence, never as `Invalid Date`.
 */
export function utcInstant(iso: string | null | undefined): string | null {
  if (typeof iso !== 'string' || iso.length === 0) {
    return null;
  }
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) {
    return null;
  }
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(new Date(ms));
  const at = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((part) => part.type === type)?.value ?? '';
  const day = at('day');
  const month = at('month');
  const year = at('year');
  const hour = at('hour');
  const minute = at('minute');
  if (day === '' || month === '' || year === '') {
    return null;
  }
  return `${day} ${month} ${year} ${hour}:${minute} UTC`;
}

/** Milliseconds between two emitted instants, or `null` when either is missing/unparseable. */
export function spanMs(fromIso: string | null | undefined, toIso: string | null | undefined): number | null {
  if (typeof fromIso !== 'string' || typeof toIso !== 'string') {
    return null;
  }
  const from = Date.parse(fromIso);
  const to = Date.parse(toIso);
  if (Number.isNaN(from) || Number.isNaN(to)) {
    return null;
  }
  return to - from;
}

/**
 * A span, in the largest unit that does not round — seconds when it is whole seconds,
 * days when it is whole days. Nothing here is rounded to make a sentence scan better.
 */
export function humanSpan(ms: number | null): string | null {
  if (ms === null) {
    return null;
  }
  const abs = Math.abs(ms);
  const DAY = 86_400_000;
  if (abs >= DAY && abs % DAY === 0) {
    const days = abs / DAY;
    return `${days.toLocaleString('en-GB')} days`;
  }
  if (abs >= 1000 && abs % 1000 === 0) {
    const seconds = abs / 1000;
    return `${seconds.toLocaleString('en-GB')} s`;
  }
  return `${abs.toLocaleString('en-GB')} ms`;
}

/**
 * A long hex value, shortened for the screen, with the full value kept in the `title`.
 *
 * A UUID is returned WHOLE. Every identifier in this demo world begins `dec0de00-`, so an
 * elided one — `dec0de00…0001` — tells a reader nothing and looks like four other rows;
 * the run id, the receipt id and the check id are the values a judge in devtools will
 * Ctrl-F, and they are 36 characters. Digests, which are 64, are the ones worth eliding.
 */
export function shortDigest(hex: string | null | undefined): { readonly short: string; readonly full: string } | null {
  if (typeof hex !== 'string' || hex.length === 0) {
    return null;
  }
  if (hex.length <= 20 || hex.includes('-')) {
    return { short: hex, full: hex };
  }
  return { short: `${hex.slice(0, 8)}…${hex.slice(-4)}`, full: hex };
}

/**
 * The chip row for a set of pointers, or `null` when the payload claimed none of them.
 *
 * When every claim shares one chip the row prints that chip once and lists the pointers,
 * which is the compact form. When they differ each renders its own. Pointers the payload
 * did NOT claim are simply not listed — the row never implies a claim that was not made.
 */
export function chipRow(lookup: ChipLookup, pointers: readonly string[]): HTMLElement | null {
  const claims: ChipClaim[] = [];
  for (const pointer of pointers) {
    const claim = lookup(pointer);
    if (claim !== null) {
      claims.push(claim);
    }
  }
  if (claims.length === 0) {
    return null;
  }
  const row = el('span', 'hz-chips');
  const kinds = new Set(claims.map((claim) => claim.kind));
  if (kinds.size === 1) {
    const kind = claims[0]?.kind;
    if (kind === undefined) {
      return null;
    }
    row.append(chipTag(kind));
    row.append(el('code', 'hz-ptr', claims.map((claim) => claim.pointer).join(' · ')));
    return row;
  }
  for (const claim of claims) {
    const one = el('span', 'hz-chip-pair');
    one.append(chipTag(claim.kind));
    one.append(el('code', 'hz-ptr', claim.pointer));
    row.append(one);
  }
  return row;
}

function chipTag(kind: ProvChip): HTMLElement {
  const tag = el('span', `hz-chip hz-chip--${kind.replace(':', '-')}`, kind);
  tag.setAttribute('data-chip', kind);
  return tag;
}

/** A `label · value` pair. The value is `textContent`, so a DB string renders as itself. */
export function pair(label: string, value: string, valueClass = 'hz-val'): HTMLElement {
  const wrap = el('div', 'hz-pair');
  wrap.append(el('span', 'hz-label', label));
  wrap.append(el('span', valueClass, value));
  return wrap;
}

/** The source footnote for one block: resource, request, status, wire bytes, server clock. */
export function sourceLine(source: SourceRef | null): HTMLElement | null {
  if (source === null) {
    return null;
  }
  const line = el('p', 'hz-source');
  line.append(el('span', 'hz-source-res', source.resource));
  const detail = `${source.method} ${source.path} · ${String(source.status)} · ${source.wireBytes.toLocaleString('en-GB')} B on the wire`;
  line.append(el('span', 'hz-source-req', detail));
  if (source.observedAt !== null) {
    line.append(el('span', 'hz-source-obs', `observed_at ${source.observedAt}`));
  }
  return line;
}

// ─────────────────────────────────────────────────────────────────────────────────────
// THE PRECURSOR BLOCK
// ─────────────────────────────────────────────────────────────────────────────────────

/** `data.checks[i].precursor` — `mainline.event`, joined inline by `reads.py`. */
export interface PrecursorEvent {
  readonly external_ref: string | null;
  readonly kind: string | null;
  readonly title: string | null;
  readonly occurred_at: string | null;
  readonly severity_gate: number | null;
  readonly severity_actual: number | null;
  readonly severity_potential: number | null;
  readonly severity_basis: string | null;
  readonly source_object_key: string | null;
  readonly source_sha256: string | null;
}

/** `data.checks[i]` — `mainline.blocking_check`, with the clause label joined. */
export interface PrecursorCheck {
  readonly clause_label: string | null;
  readonly clause_uuid: string | null;
  readonly commit_id: string | null;
  readonly origin: string | null;
  readonly severity: number | null;
  readonly virulence: string | null;
  readonly closure_gen: number | null;
  readonly evidence_summary: string | null;
  readonly materialised_at: string | null;
  readonly precursor: PrecursorEvent | null;
}

/** `data.closure` of `GET /v1/clauses/{uuid}/ancestry` — `mainline.clause_blame_current`. */
export interface PrecursorClosure {
  readonly max_severity: number | null;
  readonly virulence: string | null;
  readonly closure_gen: number | null;
  readonly ancestor_count: number | null;
  readonly computed_by: string | null;
  readonly computed_at: string | null;
}

/** What this block uses out of the ancestry payload, and nothing more. */
export interface PrecursorAncestry {
  readonly as_of_commit: string | null;
  readonly closure: PrecursorClosure | null;
  /** `blame_edges[0].attribution` — the investigation's own sentence, verbatim. */
  readonly attribution: string | null;
  readonly basis: string | null;
  readonly state: string | null;
}

/**
 * A citation into THIS REPOSITORY, which is not a value from any response.
 *
 * `r2-memory.md` §4.3 rules that the severity the seed supplied must be shown "as a code
 * citation with its file:line, never as a live value". This is that citation and it is
 * rendered under a heading that says so. It is pinned to a commit so that a reader who
 * checks it later checks the same bytes.
 */
export interface SeedCitation {
  readonly file: string;
  readonly line: number;
  readonly commit: string;
  readonly quoted: string;
}

export interface PrecursorInput {
  readonly check: PrecursorCheck | null;
  /** The pointer the blocking-checks payload claimed the check object at, e.g. `/checks/0`. */
  readonly checkPointer: string;
  readonly checkChip: ChipLookup;
  readonly checkSource: SourceRef | null;
  readonly ancestry: PrecursorAncestry | null;
  readonly ancestryChip: ChipLookup;
  readonly ancestrySource: SourceRef | null;
  readonly seedCitation: SeedCitation | null;
}

export interface PrecursorResult {
  /** `null` when no precursor was returned. Absence renders as nothing, never as a stub. */
  readonly element: HTMLElement | null;
  /** Machine-readable ids of the parts that had no data, for the card's absence strip. */
  readonly absent: readonly string[];
}

/**
 * Render the precursor block.
 *
 * TENSE. Every sentence about the recall and the projection is PAST — the event occurred,
 * the investigation named the clause, the obligation was materialised. Operator-systems
 * plan R17 forbids the present tense here because the rows are seeded rows, not a live
 * retrieval, and a card that said "the system is searching" would be describing software
 * that does not run on this page.
 */
export function renderPrecursor(input: PrecursorInput): PrecursorResult {
  const absent: string[] = [];
  const check = input.check;
  if (check === null) {
    return { element: null, absent: ['blocking_check'] };
  }
  const event = check.precursor;

  const block = el('div', 'hz-precursor');

  // ── the event ──────────────────────────────────────────────────────────────────────
  if (event === null) {
    absent.push('precursor_event');
  } else {
    const head = el('div', 'hz-event-head');
    head.append(el('span', 'hz-warn', '⚠'));
    if (event.external_ref !== null) {
      head.append(el('span', 'hz-ref', event.external_ref));
    }
    if (event.kind !== null) {
      head.append(el('span', 'hz-kind', event.kind));
    }
    // THE 2019 DATE. Emitted ISO first, human UTC form beside it — both from occurred_at.
    if (event.occurred_at !== null) {
      const human = utcInstant(event.occurred_at);
      if (human !== null) {
        head.append(el('span', 'hz-when', human));
      }
      head.append(el('code', 'hz-iso', event.occurred_at));
    } else {
      absent.push('precursor_event.occurred_at');
    }
    block.append(head);

    // `mainline.event.title`. The seed's `SYNTHETIC —` prefix is part of the column value
    // and it stays: it is what makes this exhibit honest rather than what weakens it.
    if (event.title !== null) {
      block.append(el('p', 'hz-title', event.title));
    }

    const sev = el('div', 'hz-sev');
    const gate = numberText(event.severity_gate);
    if (gate !== null) {
      sev.append(pair('severity gate', gate, 'hz-val hz-val--loud'));
    }
    const actual = numberText(event.severity_actual);
    if (actual !== null) {
      sev.append(pair('actual', actual));
    }
    const potential = numberText(event.severity_potential);
    if (potential !== null) {
      sev.append(pair('potential', potential));
    }
    if (event.severity_basis !== null) {
      sev.append(pair('basis', event.severity_basis));
    }
    if (sev.childElementCount > 0) {
      block.append(sev);
    }

    const src = el('div', 'hz-evsrc');
    if (event.source_object_key !== null) {
      src.append(pair('source document', event.source_object_key, 'hz-val hz-mono'));
    }
    const sha = shortDigest(event.source_sha256);
    if (sha !== null) {
      const shaPair = pair('sha256', sha.short, 'hz-val hz-mono');
      shaPair.title = sha.full;
      src.append(shaPair);
    }
    if (src.childElementCount > 0) {
      block.append(src);
    }
  }

  // ── the two ancestry sentences ─────────────────────────────────────────────────────
  const arrows = el('ul', 'hz-ancestry');

  // 1 · the investigation's own sentence, verbatim from mainline.blame_edge.attribution.
  const attribution = input.ancestry?.attribution ?? null;
  if (attribution !== null) {
    const item = el('li', 'hz-arrow');
    item.append(el('span', 'hz-quote', attribution));
    const edgeFacts: string[] = [];
    const basis = input.ancestry?.basis ?? null;
    if (basis !== null) {
      edgeFacts.push(`basis ${basis}`);
    }
    const edgeState = input.ancestry?.state ?? null;
    if (edgeState !== null) {
      edgeFacts.push(`state ${edgeState}`);
    }
    if (edgeFacts.length > 0) {
      item.append(el('span', 'hz-sub', edgeFacts.join(' · ')));
    }
    const chip = chipRow(input.ancestryChip, ['/blame_edges/0']);
    if (chip !== null) {
      item.append(chip);
    }
    arrows.append(item);
  } else {
    absent.push('blame_edge.attribution');
  }

  // 2 · which clause version this obligation is anchored to. The connective words are a
  //     field label; the two values are columns of mainline.blocking_check.
  if (check.clause_label !== null || check.commit_id !== null) {
    const item = el('li', 'hz-arrow');
    item.append(el('span', 'hz-lede', 'this obligation is anchored to the clause version this permit relies on'));
    const facts = el('span', 'hz-sub');
    if (check.clause_label !== null) {
      facts.append(el('span', 'hz-val', `clause ${check.clause_label}`));
    }
    const commit = shortDigest(check.commit_id);
    if (commit !== null) {
      const at = el('span', 'hz-val hz-mono', `at commit ${commit.short}`);
      at.title = commit.full;
      facts.append(at);
    }
    item.append(facts);
    arrows.append(item);
  }

  // 3 · the database's own summary of the link, verbatim.
  if (check.evidence_summary !== null) {
    const item = el('li', 'hz-arrow');
    item.append(el('span', 'hz-quote', check.evidence_summary));
    arrows.append(item);
  }

  if (arrows.childElementCount > 0) {
    block.append(arrows);
  }

  // ── the four nobody typed ──────────────────────────────────────────────────────────
  const overwrite = renderProjection(check, input.ancestry, input.seedCitation);
  if (overwrite !== null) {
    block.append(overwrite);
  }

  // ── provenance for the object every field above was read out of ────────────────────
  const claim = input.checkChip(input.checkPointer);
  const foot = el('div', 'hz-blockprov');
  if (claim !== null) {
    const chips = el('span', 'hz-chips');
    chips.append(chipTag(claim.kind));
    chips.append(el('code', 'hz-ptr', claim.pointer));
    foot.append(chips);
    foot.append(
      el(
        'span',
        'hz-sub',
        'claimed on the object, not on each field — every value above was read out of it',
      ),
    );
  }
  const checkSrc = sourceLine(input.checkSource);
  if (checkSrc !== null) {
    foot.append(checkSrc);
  }
  const ancestrySrc = sourceLine(input.ancestrySource);
  if (ancestrySrc !== null) {
    foot.append(ancestrySrc);
  }
  if (foot.childElementCount > 0) {
    block.append(foot);
  }

  return { element: block, absent };
}

/**
 * The projection exhibit — two payloads, side by side, and the equality between them.
 *
 * This is the payload-level form of "nobody typed the four". `fn_check_project` overwrites
 * `severity`, `virulence` and `closure_gen` on every blocking check from
 * `mainline.clause_blame_current`, so the obligation's three numbers must EQUAL the blame
 * closure's three. Both sides here are live reads of two different endpoints, and the
 * equality is computed in this browser and chipped as such by saying so in words —
 * `derived` is not claimed, because no envelope claimed it for a value this client made.
 *
 * The comparison is suppressed unless the ancestry payload's `as_of_commit` is the same
 * commit the obligation names. Comparing a closure computed for a different clause version
 * would be an exhibit that looks like proof and is not one.
 */
function renderProjection(
  check: PrecursorCheck,
  ancestry: PrecursorAncestry | null,
  citation: SeedCitation | null,
): HTMLElement | null {
  const closure = ancestry?.closure ?? null;
  const wrap = el('div', 'hz-projection');
  wrap.append(el('h4', 'hz-h4', 'the severity on this obligation was not chosen by whoever raised it'));

  const table = el('div', 'hz-grid');
  const onCheck = el('div', 'hz-grid-row');
  onCheck.append(el('span', 'hz-grid-key', 'on the obligation'));
  onCheck.append(el('span', 'hz-val hz-val--loud', numberText(check.severity) ?? '—'));
  onCheck.append(el('span', 'hz-val', check.virulence ?? '—'));
  onCheck.append(el('span', 'hz-val', `closure_gen ${numberText(check.closure_gen) ?? '—'}`));
  table.append(onCheck);

  let comparable = false;
  if (closure !== null && ancestry !== null && sameCommit(ancestry.as_of_commit, check.commit_id)) {
    comparable = true;
    const onClosure = el('div', 'hz-grid-row');
    onClosure.append(el('span', 'hz-grid-key', 'in the blame closure'));
    onClosure.append(el('span', 'hz-val hz-val--loud', numberText(closure.max_severity) ?? '—'));
    onClosure.append(el('span', 'hz-val', closure.virulence ?? '—'));
    onClosure.append(el('span', 'hz-val', `closure_gen ${numberText(closure.closure_gen) ?? '—'}`));
    table.append(onClosure);
  }
  wrap.append(table);

  if (comparable && closure !== null) {
    const equal =
      check.severity === closure.max_severity &&
      check.virulence === closure.virulence &&
      check.closure_gen === closure.closure_gen;
    const verdict = el(
      'p',
      equal ? 'hz-equal' : 'hz-unequal',
      equal
        ? 'the two rows carry the same three values — compared in this browser, from the two payloads above'
        : 'the two rows disagree — compared in this browser, from the two payloads above',
    );
    wrap.append(verdict);
    const count = numberText(closure.ancestor_count);
    const details: string[] = [];
    if (count !== null) {
      details.push(`${count} ancestor event(s) in the closure`);
    }
    if (closure.computed_by !== null) {
      details.push(`computed_by ${closure.computed_by}`);
    }
    if (closure.computed_at !== null) {
      details.push(`computed_at ${closure.computed_at}`);
    }
    if (details.length > 0) {
      wrap.append(el('p', 'hz-sub', details.join(' · ')));
    }
  }

  if (check.origin !== null) {
    wrap.append(pair('origin', check.origin, 'hz-val hz-val--origin'));
  }

  if (citation !== null) {
    const cite = el('p', 'hz-citation');
    cite.append(el('span', 'hz-citation-tag', 'source citation — this repository, not this response'));
    cite.append(el('code', 'hz-citation-code', citation.quoted));
    cite.append(el('span', 'hz-sub', `${citation.file}:${String(citation.line)} @ ${citation.commit}`));
    wrap.append(cite);
  }

  return wrap;
}

function sameCommit(a: string | null, b: string | null): boolean {
  return typeof a === 'string' && typeof b === 'string' && a.toLowerCase() === b.toLowerCase();
}

/** A number the payload carried, as text. `null` for absent — never `0` for absent. */
export function numberText(value: number | null | undefined): string | null {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : null;
}
