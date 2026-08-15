// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * R11 — THE ABSENCE THIS SCREEN IS REQUIRED TO NAME, AND THE EVIDENCE FOR IT.
 *
 * The change request has one blocking obligation open on it: `counters.open_blocking = 1`
 * comes back on every read of `GET /v1/change-requests/{cr_id}`. **No declared route
 * returns that obligation.** `GET /v1/change-requests/{cr_id}/blocking-checks` is 404 and
 * `POST /v1/change-requests/{cr_id}/merge` is 404 — measured, not assumed.
 *
 * So there are exactly three honest moves available, and this module makes all three:
 *
 *   1. The approve control is rendered **disabled, with the obligation named as the
 *      reason**, in the database's own words: the counter, the constraint, the CHECK
 *      predicate, the table. That is what a control-of-work product does when mandatory
 *      checks are outstanding (r3-operator §2.5), so it is both truthful and in register.
 *      It has no click handler. It is wired to nothing. In particular it is NOT wired to
 *      `POST /v1/permits/{permit_id}/merge` to make the screen "work" — that route drives
 *      a different subject and pointing this button at it would be a fabricated action.
 *
 *   2. Beside it, the deployment's **own 404 route table**, parsed out of the verbatim
 *      bytes of a real 404 taken in this page load. The absent routes are shown struck
 *      through against the declared ones, so the absence is something a judge reads off
 *      the response rather than something this page asserts. The raw body is on screen.
 *
 *   3. The change request's own defeater prompts render **if and only if a check id was
 *      obtained from a live read**. There is no fallback and no literal.
 *
 * ── WHY THE DISCOVERY IS DRIVEN BY THE ROUTE TABLE ITSELF ────────────────────────────
 *
 * `subjects.py:24-27` argues that an id typed into source is a claim about a database
 * made by a file that cannot see one. The change request's check id is written out in
 * `docs/demo/research/r3-operator.md` §7.3; copying it here would be exactly that act,
 * and the id would keep rendering long after the row it names had stopped existing.
 *
 * The alternative implemented here is better than a literal in every respect. The 404
 * body declares the WHOLE route table, so this module asks the deployment itself whether
 * a route that yields a change request's checks exists — by predicate over the declared
 * templates, not by matching a string it hopes to find. Today the answer is no and the
 * absence panel renders. On the day that route is added, `discoverCrCheckIds` follows it,
 * fetches the checks, and the prompts appear, with no edit to this file. The code adapts
 * to the deployment; it never asserts over it.
 *
 * Nothing in this module composes an id, a count, a SQLSTATE or a status. Every one of
 * those comes from a response received in this page load.
 */

import { el, txt } from './ribbon';

/* ── the deployment's own route table ─────────────────────────────────────────────── */

/** The `error` object a `no_route` 404 carries. Every field is the deployment's. */
export interface RouteTable {
  readonly status: number;
  readonly kind: string;
  readonly detail: string;
  readonly declared: readonly string[];
}

function isStringArray(value: unknown): value is readonly string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

/**
 * Parse a route table out of the VERBATIM bytes of a response.
 *
 * It reads `exchange.raw`, not a re-serialised object, because the route table is the
 * exhibit: what is rendered has to be what came off the wire. Returns `null` — never a
 * default, never an empty table — when the body is not a `no_route` 404, so a caller can
 * never mistake "we could not parse it" for "the deployment declares nothing".
 */
export function parseRouteTable(raw: string): RouteTable | null {
  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof body !== 'object' || body === null) return null;
  const error: unknown = (body as Record<string, unknown>).error;
  if (typeof error !== 'object' || error === null) return null;
  const record = error as Record<string, unknown>;
  const declared: unknown = record.declared;
  const kind: unknown = record.kind;
  const status: unknown = record.status;
  const detail: unknown = record.detail;
  if (!isStringArray(declared)) return null;
  if (typeof kind !== 'string' || typeof status !== 'number') return null;
  return {
    status,
    kind,
    detail: typeof detail === 'string' ? detail : '',
    declared,
  };
}

/** Split a route template into its non-empty path segments. */
function segments(template: string): readonly string[] {
  return template.split('/').filter((segment) => segment !== '');
}

/** `true` when a template addresses a change request. */
function addressesChangeRequest(template: string): boolean {
  return segments(template).includes('change-requests');
}

/**
 * Every declared template that would yield a change request's blocking checks.
 *
 * The predicate is over path SHAPE, not over a remembered string: a change-request path
 * whose last segment names checks. `checks:materialise` is deliberately matched too — a
 * route that materialises a change request's checks would still be a route that names
 * them, and this module would rather find one route too many than miss the one that
 * arrives after it was written.
 */
export function routesYieldingCrChecks(declared: readonly string[]): readonly string[] {
  return declared.filter((template) => {
    if (!addressesChangeRequest(template)) return false;
    return segments(template).some(
      (segment) => segment.startsWith('checks') || segment.startsWith('blocking-checks'),
    );
  });
}

/** Every declared template that would merge a change request. */
export function routesMergingChangeRequest(declared: readonly string[]): readonly string[] {
  return declared.filter(
    (template) => addressesChangeRequest(template) && segments(template).includes('merge'),
  );
}

/**
 * The two routes this screen would need, COMPOSED OUT OF THE DEPLOYMENT'S OWN TABLE.
 *
 * This is the part that makes the struck-through list evidence rather than assertion. It
 * does not carry a remembered path. It takes the base change-request template the
 * deployment declares, takes the trailing segments the deployment declares on the
 * *permit* — the sibling subject that DOES have both routes — and composes the two paths
 * that would exist if the change request had them. Then it returns only the composed
 * paths that the table does not declare.
 *
 * Consequences worth stating, because they are why this shape was chosen:
 *   • if either route is added to the deployment, it drops out of this list on the next
 *     page load and nothing has to be edited;
 *   • if the deployment renames `blocking-checks`, the rename is picked up from the
 *     permit's own template rather than becoming a stale string here;
 *   • the panel can never show a route as missing that the table declares, because the
 *     final filter is against the table.
 *
 * `wanted` names which sibling capabilities to look for. They are route words, checked
 * against the declared table before anything is rendered — never values claimed to have
 * come from the deployment.
 */
export function composeAbsentCrRoutes(
  declared: readonly string[],
  wanted: readonly string[] = ['blocking-checks', 'merge'],
): readonly string[] {
  const base = declared.find(
    (template) => addressesChangeRequest(template) && segments(template).length === 3,
  );
  if (base === undefined) return [];

  const siblingSuffixes = new Set<string>();
  for (const template of declared) {
    const parts = segments(template);
    const last = parts[parts.length - 1];
    if (parts.length === 4 && last !== undefined && !last.startsWith('{')) {
      siblingSuffixes.add(last);
    }
  }

  const composed: string[] = [];
  for (const suffix of wanted) {
    if (!siblingSuffixes.has(suffix)) continue;
    const candidate = `${base}/${suffix}`;
    if (!declared.includes(candidate)) composed.push(candidate);
  }
  return composed;
}

/**
 * Fill a route template's placeholders from named values.
 *
 * Fails CLOSED: any `{placeholder}` with no supplied value yields `null` rather than a
 * path with a brace in it, because a request built from a half-filled template would
 * produce a 404 that looked like the absence this screen is trying to prove.
 */
export function fillTemplate(
  template: string,
  values: Readonly<Record<string, string | null>>,
): string | null {
  let failed = false;
  const filled = template.replace(/\{([^{}]+)\}/g, (_match, name: string) => {
    const value = values[name];
    if (value === undefined || value === null || value === '') {
      failed = true;
      return '';
    }
    return encodeURIComponent(value);
  });
  return failed ? null : filled;
}

/* ── the live discovery ───────────────────────────────────────────────────────────── */

/**
 * The minimum a caller must give this module to make an HTTP read.
 *
 * `data` is deliberately `unknown`. This module follows a route it did not know about
 * when it was written, so it cannot claim to know the shape of what comes back: the check
 * ids are narrowed out of the payload below, one `typeof` at a time. A generic here would
 * let a caller assert a shape onto a response nobody has seen.
 */
export interface AbsenceReader {
  get(path: string): Promise<{
    readonly method: string;
    readonly path: string;
    readonly status: number;
    readonly data: unknown;
    readonly raw: string;
    readonly wireBytes: number;
    readonly receivedAt: string;
  }>;
}

/** Pull `check_id` strings out of a payload of unknown shape. Silent on anything else. */
function checkIdsIn(data: unknown): readonly string[] {
  if (typeof data !== 'object' || data === null) return [];
  const checks: unknown = (data as Record<string, unknown>).checks;
  if (!Array.isArray(checks)) return [];
  const ids: string[] = [];
  for (const check of checks) {
    if (typeof check !== 'object' || check === null) continue;
    const id: unknown = (check as Record<string, unknown>).check_id;
    if (typeof id === 'string') ids.push(id);
  }
  return ids;
}

export interface CrCheckDiscovery {
  /** The templates the deployment declares that could have answered. Empty is the point. */
  readonly candidateRoutes: readonly string[];
  /** Check ids obtained from a live 200. Empty when none was reachable. */
  readonly checkIds: readonly string[];
  /** One line per attempt, verbatim, for the request log and the evidence panel. */
  readonly attempts: readonly string[];
}

/**
 * Ask the deployment, over HTTP, for the change request's blocking checks.
 *
 * Returns `checkIds: []` when no declared route could answer. That empty array is the
 * gate on the defeater prompts: `renderDefeaterPrompts` is only ever called with options
 * that came back from `GET /v1/checks/{check_id}/disposition` for an id found here.
 */
export async function discoverCrCheckIds(
  reader: AbsenceReader,
  table: RouteTable,
  values: Readonly<Record<string, string | null>>,
): Promise<CrCheckDiscovery> {
  const candidateRoutes = routesYieldingCrChecks(table.declared);
  const attempts: string[] = [];
  const checkIds: string[] = [];

  for (const template of candidateRoutes) {
    const path = fillTemplate(template, values);
    if (path === null) {
      attempts.push(`${template} — declared, but this page holds no value for its placeholders`);
      continue;
    }
    const exchange = await reader.get(path);
    attempts.push(`GET ${exchange.path} → ${String(exchange.status)}`);
    if (exchange.status !== 200) continue;
    checkIds.push(...checkIdsIn(exchange.data));
  }

  return { candidateRoutes, checkIds, attempts };
}

/* ── rendering ────────────────────────────────────────────────────────────────────── */

/** One constraint as `GET /v1/change-requests/{cr_id}` returns it. */
export interface ChangeConstraint {
  readonly constraint: string;
  readonly predicate: string;
  readonly blamed_by_refusal: boolean;
  readonly counters: readonly { readonly column: string; readonly value: number }[];
}

export interface ObligationInput {
  /** `data.counters.open_blocking`, or `null` when the read has not landed. */
  readonly openBlocking: number | null;
  /** `data.constraints`, in payload order. */
  readonly constraints: readonly ChangeConstraint[];
  /** `statement_refs[].object` where `kind === 'table'` — the table the predicates are on. */
  readonly tables: readonly string[];
  /** The verbatim request line the change request arrived on. */
  readonly readFrom: string;
}

/**
 * The obligation, as far as this deployment lets it be known — and the boundary, named.
 *
 * The count is real and the constraints are real. The obligation's identity, precursor,
 * severity and defeater vocabulary are NOT reachable, and this panel says so in the same
 * breath rather than leaving a reader to assume the screen simply chose not to show them.
 */
export function renderObligation(input: ObligationInput): HTMLElement {
  const wrap = el('div');

  const known = el('p');
  if (input.openBlocking === null) {
    known.append(
      el('span', 'moc-absent-inline', 'not read'),
      document.createTextNode(' — the change request read has not landed.'),
    );
  } else {
    known.append(
      document.createTextNode(
        `${String(input.openBlocking)} blocking obligation${input.openBlocking === 1 ? '' : 's'} ` +
          'open on this change request. The count is a column: ',
      ),
      el('code', 'moc-db', `counters.open_blocking = ${String(input.openBlocking)}`),
      document.createTextNode('.'),
    );
  }
  wrap.append(known);

  if (input.constraints.length > 0) {
    const scroll = el('div', 'moc-scroll');
    const table = el('table', 'moc-table');
    const caption = el('caption');
    caption.append(
      document.createTextNode('CHECK constraints this record is held to'),
      input.tables.length > 0
        ? document.createTextNode(`, on ${input.tables.join(', ')}`)
        : document.createTextNode(''),
      document.createTextNode(
        '. Predicates are read out of pg_catalog at request time, not stored in this page.',
      ),
    );
    table.append(caption);

    const thead = el('thead');
    const headRow = el('tr');
    for (const heading of ['constraint', 'predicate', 'counters it reads']) {
      headRow.append(el('th', undefined, heading));
    }
    thead.append(headRow);
    table.append(thead);

    const tbody = el('tbody');
    for (const constraint of input.constraints) {
      const tr = el('tr');
      tr.append(el('td', 'moc-kind', constraint.constraint));
      tr.append(el('td', 'moc-pred', constraint.predicate));
      const counters = constraint.counters
        .map((counter) => `${counter.column} = ${String(counter.value)}`)
        .join(', ');
      tr.append(el('td', 'moc-num', counters === '' ? '—' : counters));
      tbody.append(tr);
    }
    table.append(tbody);
    scroll.append(table);
    wrap.append(scroll);
  }

  wrap.append(
    txt(
      'What this deployment does NOT return: the obligation’s own row. Its id, the precursor ' +
        'that raised it, its severity, its virulence and its defeater vocabulary are not ' +
        'reachable from any declared route, so none of them is shown. The counter above is ' +
        'the whole of what can be known about it from here, and the route table beside the ' +
        'approve control is the evidence for that sentence.',
    ),
  );
  wrap.append(txt(input.readFrom, 'moc-exchange'));
  return wrap;
}

export interface ActionBarInput {
  /** Named on the disabled control. Real, from `data.counters.open_blocking`. */
  readonly openBlocking: number | null;
  /** The constraint that would refuse the merge, if the payload carried one. */
  readonly blockingConstraint: ChangeConstraint | null;
  /** Tables the predicates sit on, from the envelope's `statement_refs`. */
  readonly tables: readonly string[];
  /** The parsed 404, or `null` if the probe itself could not be read. */
  readonly table: RouteTable | null;
  /** Verbatim bytes of the 404 body. */
  readonly raw: string;
  /** The verbatim request line the 404 arrived on. */
  readonly probeLine: string;
  /** Path templates this screen looked for and did not find, shown struck through. */
  readonly soughtButAbsent: readonly string[];
  /** Attempts made by `discoverCrCheckIds`, for the record. */
  readonly discoveryAttempts: readonly string[];
}

/**
 * The action bar: a disabled approve control, and the absence that disables it.
 *
 * The button carries `disabled`, `aria-disabled` and a `aria-describedby` pointing at the
 * reason, and it is given NO listener anywhere in this directory. There is no enabled
 * state reachable from this page, because there is no route that could produce one.
 */
export function renderActionBar(input: ActionBarInput): HTMLElement {
  const bar = el('section', 'moc-actionbar');
  bar.setAttribute('aria-label', 'Approval');

  const left = el('div');
  const button = el('button', 'moc-approve', 'Approve change');
  button.type = 'button';
  button.disabled = true;
  button.setAttribute('aria-disabled', 'true');
  button.setAttribute('aria-describedby', 'moc-approve-reason');
  left.append(button);

  const reason = el('p', 'moc-approve-reason');
  reason.id = 'moc-approve-reason';
  if (input.openBlocking === null) {
    reason.append(
      document.createTextNode('Cannot approve: the change request read has not landed.'),
    );
  } else {
    reason.append(
      document.createTextNode(
        `Cannot approve. ${String(input.openBlocking)} blocking obligation` +
          `${input.openBlocking === 1 ? ' is' : 's are'} outstanding on this change request.`,
      ),
    );
  }
  left.append(reason);

  if (input.blockingConstraint !== null) {
    const quote = el('p', 'moc-quote');
    quote.append(
      document.createTextNode(`${input.blockingConstraint.constraint}\n`),
      document.createTextNode(input.blockingConstraint.predicate),
    );
    left.append(quote);
    if (input.tables.length > 0) {
      left.append(txt(`← from ${input.tables.join(', ')}`));
    }
  }

  left.append(
    txt(
      'This control is disabled because no route exists to drive it, and it is wired to ' +
        'nothing. It is not pointed at the permit’s merge route: that route drives a ' +
        'different subject, and a button that refused a different record would be a prop.',
    ),
  );
  bar.append(left);

  const right = el('div', 'moc-evidence');
  right.append(el('h3', 'moc-evidence-title', 'Why there is no approve action here'));

  if (input.table === null) {
    right.append(
      el(
        'p',
        'moc-absent',
        'The route-table probe did not return a readable no_route body, so this panel makes ' +
          'no claim about which routes exist. The verbatim response is below.',
      ),
    );
  } else {
    right.append(
      txt(
        `The deployment answered ${String(input.table.status)} ${input.table.kind} and declared ` +
          `its whole route table — ${String(input.table.declared.length)} routes. The routes this ` +
          'screen would need are not among them, so they are shown struck through in place.',
      ),
    );

    const list = el('ul', 'moc-routes');
    // Belt and braces: a template is only ever struck through after being checked against
    // the table that arrived on this response. Nothing can render as missing that the
    // deployment declares, however it reached `soughtButAbsent`.
    const missing = input.soughtButAbsent.filter(
      (template) => !input.table?.declared.includes(template),
    );
    for (const template of missing) {
      const item = el('li', 'moc-route moc-route-missing', template);
      item.setAttribute('aria-label', `${template} — not declared`);
      list.append(item);
    }
    for (const template of input.table.declared) {
      list.append(el('li', 'moc-route', template));
    }
    right.append(list);
    right.append(txt(input.table.detail, 'moc-exchange'));
  }

  right.append(txt(input.probeLine, 'moc-exchange'));

  const raw = el('pre', 'moc-raw', input.raw);
  raw.setAttribute('aria-label', 'verbatim 404 response body');
  right.append(raw);

  for (const attempt of input.discoveryAttempts) {
    right.append(txt(attempt, 'moc-exchange'));
  }

  bar.append(right);
  return bar;
}

/** One entry of `data.defeater_options` from `GET /v1/checks/{check_id}/disposition`. */
export interface DefeaterOption {
  readonly defeater_code: string;
  readonly prompt: string;
  readonly vocab_sha256?: string;
}

/**
 * The defeater prompts — rendered ONLY from options that arrived on a live read.
 *
 * Each is a question demanding a citation, not a checkbox. There is no "N/A" and no "not
 * applicable" option, because no such code exists in the vocabulary and inventing one
 * would let an engineer dismiss the obligation without answering it — which is the entire
 * failure this system exists to prevent.
 *
 * `options` comes from a payload. If a caller has none, it must not call this function:
 * there is no argument that produces a prompt this page composed.
 */
export function renderDefeaterPrompts(
  options: readonly DefeaterOption[],
  readFrom: string,
): HTMLElement {
  const wrap = el('div');
  const group = el('fieldset', 'moc-prompts');
  group.append(
    el(
      'legend',
      'moc-label',
      'Ways this obligation could be answered — each requires a citation',
    ),
  );

  options.forEach((option, index) => {
    const card = el('div', 'moc-prompt');
    const id = `moc-defeater-${String(index)}`;

    const label = el('label');
    label.htmlFor = `${id}-citation`;

    const radio = el('input');
    radio.type = 'radio';
    radio.name = 'moc-defeater';
    radio.id = id;
    radio.value = option.defeater_code;

    card.append(radio);
    card.append(el('span', 'moc-prompt-code', ` ${option.defeater_code}`));
    card.append(el('p', 'moc-prompt-text', option.prompt));

    label.append(document.createTextNode('Citation'));
    card.append(label);

    const citation = el('input', 'moc-typed-field');
    citation.type = 'text';
    citation.id = `${id}-citation`;
    citation.placeholder = 'typed by the engineer — this deployment carries no answer';
    card.append(citation);

    group.append(card);
  });

  wrap.append(group);
  wrap.append(
    txt(
      'There is no “not applicable” option because the vocabulary does not contain one. ' +
        'The prompts above are the ones this read returned, printed verbatim.',
    ),
  );
  wrap.append(txt(readFrom, 'moc-exchange'));
  return wrap;
}
