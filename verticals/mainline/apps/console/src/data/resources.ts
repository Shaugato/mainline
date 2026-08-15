// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The console's read surface, declared once.
 *
 * Every request the console can make is an entry in `RESOURCES`, and every entry names
 * three things: the HTTP shape (method, path template), the contract that governs the
 * response, and whether the endpoint has an owner in another domain yet.
 *
 * The last of those is not bookkeeping. `docs/leads/ui.md` §4 records that the ancestry
 * read endpoint is **unassigned** — no backend worker owes it — and the mitigation is
 * that `scripts/capture-bundle.ts` emits the payload directly from SQL so the console
 * never learns the difference. `owner: null` is that fact, written where a reader will
 * see it, rather than a comment in a document nobody opens twice.
 *
 * The canonical **request key** derived here is what makes `HttpTransport` and
 * `BundleTransport` interchangeable. It is computed from the method, the interpolated
 * path and the sorted query — never from a transport detail — so a frame captured
 * against a live kernel is addressable by a player that has never seen one. It is also
 * the frame's file name, so a bundle needs no index; an index would be a second place
 * for the truth to live.
 */

// ── Resource declarations ──────────────────────────────────────────────────

export type HttpMethod = 'GET' | 'POST';

export interface ResourceDescriptor {
  /** Stable key. Matches `envelope.resource` in the payload. */
  readonly key: string;
  readonly method: HttpMethod;
  /** Path template with `{param}` placeholders, e.g. `/v1/permits/{permit_id}`. */
  readonly template: string;
  /** Required path parameters, in template order. */
  readonly pathParams: readonly string[];
  /** Query parameters the console may send. Anything else is rejected before it is sent. */
  readonly queryParams: readonly string[];
  /** `$id` of the contract governing the response payload. */
  readonly schemaId: string;
  /** The backend domain that owes this endpoint, or `null` when nobody does yet. */
  readonly owner: string | null;
  /** One line: what this resource is for. Rendered in the audit surface. */
  readonly purpose: string;
}

const C = 'https://console.mainline.trappoint.org/contracts/1.0/';

function templateParams(template: string): readonly string[] {
  return [...template.matchAll(/\{([a-z_]+)\}/g)].map((match) => match[1] ?? '');
}

function declare(
  key: string,
  method: HttpMethod,
  template: string,
  schemaId: string,
  owner: string | null,
  purpose: string,
  queryParams: readonly string[] = [],
): ResourceDescriptor {
  return Object.freeze({
    key,
    method,
    template,
    pathParams: Object.freeze(templateParams(template)),
    queryParams: Object.freeze([...queryParams]),
    schemaId,
    owner,
    purpose,
  });
}

const DECLARED: readonly ResourceDescriptor[] = Object.freeze([
  declare(
    'permit',
    'GET',
    '/v1/permits/{permit_id}',
    `${C}permit.schema.json`,
    'kernel',
    'The permit row: seven projected counters, the gate epoch, and the six named refusals declared on the table.',
  ),
  declare(
    'change_request',
    'GET',
    '/v1/change-requests/{cr_id}',
    `${C}change-request.schema.json`,
    'kernel',
    'The second gated subject. The repository is the protected branch; the permit is one of its refs.',
  ),
  declare(
    'blocking_checks',
    'GET',
    '/v1/permits/{permit_id}/blocking-checks',
    `${C}blocking-check.schema.json`,
    'kernel',
    'Every materialised obligation attached to the subject, with the projected severity, virulence and closure generation that armed it.',
  ),
  declare(
    'disposition',
    'GET',
    '/v1/checks/{check_id}/disposition',
    `${C}disposition.schema.json`,
    'kernel',
    'The clearance lattice row governing this check, the per-check defeater vocabulary, the reading floor, and any signature already recorded.',
  ),
  declare(
    'exposure_receipt',
    'GET',
    '/v1/receipts/{receipt_id}',
    `${C}exposure.schema.json`,
    'kernel',
    'What was actually shown, to whom, when — the composite FK a disposition must land on.',
  ),
  declare(
    'clause_version',
    'GET',
    '/v1/clauses/{clause_uuid}/versions/{commit_id}',
    `${C}clause.schema.json`,
    'datamodel',
    'One clause version with its canonical text, anchor set, control delta and the witnesses behind that delta.',
  ),
  declare(
    'clause_ancestry',
    'GET',
    '/v1/clauses/{clause_uuid}/ancestry',
    `${C}ancestry.schema.json`,
    // ui.md §4: unassigned. The capture script sources it from SQL; if it is never
    // built the console is replay-only for this surface and the honesty chrome says so.
    null,
    'The blame walk: the closure row, its events and edges, and the commit chain that carried the clause across the years.',
    ['as_of'],
  ),
  declare(
    'ledger',
    'GET',
    '/v1/ledger',
    `${C}ledger.schema.json`,
    'custody',
    'Leaves, interior nodes, checkpoints, inclusion and consistency proofs, and cosignatures — the bytes the in-browser verifier recomputes.',
    ['site_code', 'from_seq', 'to_seq'],
  ),
  declare(
    'silence',
    'GET',
    '/v1/permits/{permit_id}/silence',
    `${C}silence.schema.json`,
    'recall',
    'Everything the recall declined to surface for this subject, with its arithmetic, and the Proof of Exhausted Recall receipt.',
  ),
  declare(
    'recall_run',
    'GET',
    '/v1/recall-runs/{run_id}',
    `${C}recall-run.schema.json`,
    'recall',
    'One recall run: the conservation arithmetic, the observed index plan digest, and which arms degraded.',
  ),
  declare(
    'propagation',
    'GET',
    '/v1/lessons/{lesson_id}/propagation',
    `${C}propagation.schema.json`,
    'datamodel',
    'Where the lesson travelled, where it did not, and every conflict still open.',
  ),
  declare(
    'audit',
    'GET',
    '/v1/audit',
    `${C}audit.schema.json`,
    'agents-mcp',
    'The mainline_audit.v_* aggregates and the Managed-MCP call log, with the row and byte caps each ran under.',
  ),
  declare(
    'materialise_checks',
    'POST',
    '/v1/permits/{permit_id}/checks:materialise',
    `${C}invoke.schema.json`,
    'kernel',
    'trappoint.materialise_checks() — issues the exposure receipt and materialises blocking_check rows in ONE serializable transaction.',
  ),
  declare(
    'sign_disposition',
    'POST',
    '/v1/checks/{check_id}/disposition',
    `${C}invoke.schema.json`,
    'kernel',
    'trappoint.sign_disposition() — the signature, against a lattice row that must exist.',
  ),
  declare(
    'merge_permit',
    'POST',
    '/v1/permits/{permit_id}/merge',
    `${C}invoke.schema.json`,
    'kernel',
    'trappoint.merge_permit() — the money path. The database refuses it, by name, or it commits.',
  ),
  declare(
    'suspend_permit',
    'POST',
    '/v1/permits/{permit_id}/suspend',
    `${C}invoke.schema.json`,
    'kernel',
    'trappoint.suspend_permit() — the declared path when an issued permit acquires a new precursor: suspend and fork, never rewrite.',
  ),
  // THE TEMPLATE TAKES NO PATH PARAMETER, AND THAT IS THE POINT.
  //
  // Every other transition above is addressed by a `{permit_id}` or `{check_id}` the
  // caller supplies. This one is not: the subject is the SEEDED DEMO PERMIT, resolved
  // server-side, so a stranger holding the public URL cannot point the driver at
  // somebody else's row. `resolveRequest` refuses a `path` argument for a resource that
  // declares no path parameter, which turns the guarantee into an error rather than a
  // convention.
  declare(
    'demo_gate_run',
    'POST',
    '/v1/demo/gate-run',
    `${C}gate-run.schema.json`,
    'kernel',
    'The four-beat demo run against the seeded permit — read, refused, refused under a forged counter, admitted — inside ONE serializable transaction that is rolled back.',
  ),
  // THIS IS THE ONE READ THAT ANSWERS "WHICH SUBJECT", AND IT TAKES NO PARAMETER EITHER.
  //
  // Every other GET above is addressed by an identifier the caller already holds. Nothing
  // told the console where to get one: `/v1/audit` is aggregate-first and names no
  // permit_id, so five surfaces either opened on nothing or opened on an identifier
  // somebody had typed into a `.tsx` constant — which 404s the first time a deployment
  // seeds a different history, and did, on the live URL, on three separate screens.
  //
  // The repair is not a better constant. It is this read: the kernel SELECTs the
  // identifiers back out of the demo tables and the console addresses what it is told.
  // `src/data/demo-subjects.ts` is the only caller, it caches the answer for the session,
  // and it degrades to a named absence rather than to a literal when the route is not
  // there — an older deployment answers 404 here and every surface says so in words.
  declare(
    'demo_subjects',
    'GET',
    '/v1/demo/subjects',
    `${C}subjects.schema.json`,
    'kernel',
    'Which subjects this deployment actually seeded, read back out of the demo tables — one identifier per addressed slot, null where the row is absent, and never a value the console invented.',
  ),
]);

export const RESOURCES: ReadonlyMap<string, ResourceDescriptor> = Object.freeze(
  new Map(DECLARED.map((resource) => [resource.key, resource])),
);

/**
 * The keys, as literal types.
 *
 * They are written out a second time rather than inferred from `DECLARED`, because
 * `declare()` returns a widened `ResourceDescriptor` and the literals would be lost.
 * The duplication is made safe by the assertion below, which runs at module load: the
 * two lists must be the same set, or the module refuses to initialise.
 */
export const RESOURCE_KEYS = [
  'audit',
  'blocking_checks',
  'change_request',
  'clause_ancestry',
  'clause_version',
  'demo_gate_run',
  'demo_subjects',
  'disposition',
  'exposure_receipt',
  'ledger',
  'materialise_checks',
  'merge_permit',
  'permit',
  'propagation',
  'recall_run',
  'sign_disposition',
  'silence',
  'suspend_permit',
] as const;

export type ResourceKey = (typeof RESOURCE_KEYS)[number];

{
  const declared = [...RESOURCES.keys()].sort().join(',');
  const listed = [...RESOURCE_KEYS].sort().join(',');
  if (declared !== listed) {
    throw new Error(
      `src/data/resources.ts is inconsistent with itself: RESOURCES has [${declared}] ` +
        `but RESOURCE_KEYS has [${listed}].`,
    );
  }
}

export function resourceOrThrow(key: string): ResourceDescriptor {
  const resource = RESOURCES.get(key);
  if (resource === undefined) {
    throw new Error(
      `unknown resource "${key}". Declared resources: ${[...RESOURCES.keys()].sort().join(', ')}.`,
    );
  }
  return resource;
}

// ── Request construction ───────────────────────────────────────────────────

export interface ResourceRequest {
  readonly resource: string;
  /** Path parameters. Every `{param}` in the template must be supplied. */
  readonly path?: Readonly<Record<string, string>>;
  /** Query parameters. Only the declared ones are accepted. */
  readonly query?: Readonly<Record<string, string>>;
  /** JSON body for a POST. Ignored for GET, and a GET with a body is refused. */
  readonly body?: unknown;
}

export interface ResolvedRequest {
  readonly resource: ResourceDescriptor;
  readonly method: HttpMethod;
  /** Interpolated path, no query string. */
  readonly path: string;
  /** Query pairs, sorted by name then value — the canonical order. */
  readonly query: readonly (readonly [string, string])[];
  /**
   * `${method} ${path}` plus the sorted query. Stable across transports, and the only
   * thing a replay bundle is addressed by — see the note above `urlFor`.
   */
  readonly key: string;
  readonly body: unknown;
}

/**
 * Path parameters are checked against a conservative pattern before interpolation.
 *
 * This is not input sanitisation theatre: a UUID or a hex commit id is the only thing
 * that ever goes in one of these slots, and admitting a `/` would let a caller reshape
 * the request into a different resource — which, in replay, would silently address a
 * different frame.
 */
const PATH_VALUE = /^[A-Za-z0-9._~-]{1,128}$/;

export function resolveRequest(request: ResourceRequest): ResolvedRequest {
  const resource = resourceOrThrow(request.resource);
  const supplied = request.path ?? {};

  let path = resource.template;
  for (const name of resource.pathParams) {
    const value = supplied[name];
    if (value === undefined) {
      throw new Error(`resource "${resource.key}" requires path parameter "${name}".`);
    }
    if (!PATH_VALUE.test(value)) {
      throw new Error(
        `path parameter "${name}" of resource "${resource.key}" has value ${JSON.stringify(value)}, ` +
          'which is not an unreserved token. A path parameter that could contain a separator could ' +
          'address a different resource than the one asked for.',
      );
    }
    path = path.replace(`{${name}}`, value);
  }

  for (const name of Object.keys(supplied)) {
    if (!resource.pathParams.includes(name)) {
      throw new Error(`resource "${resource.key}" has no path parameter "${name}".`);
    }
  }

  const queryEntries: (readonly [string, string])[] = [];
  for (const [name, value] of Object.entries(request.query ?? {})) {
    if (!resource.queryParams.includes(name)) {
      throw new Error(
        `resource "${resource.key}" does not declare query parameter "${name}". ` +
          `Declared: ${resource.queryParams.join(', ') || '(none)'}.`,
      );
    }
    queryEntries.push([name, value]);
  }
  queryEntries.sort((a, b) => a[0].localeCompare(b[0]) || a[1].localeCompare(b[1]));

  if (resource.method === 'GET' && request.body !== undefined) {
    throw new Error(`resource "${resource.key}" is a GET and cannot carry a body.`);
  }

  const queryString = queryEntries
    .map(([name, value]) => `${encodeURIComponent(name)}=${encodeURIComponent(value)}`)
    .join('&');
  const key = queryString === '' ? `${resource.method} ${path}` : `${resource.method} ${path}?${queryString}`;

  return {
    resource,
    method: resource.method,
    path,
    query: Object.freeze(queryEntries),
    key,
    body: request.body,
  };
}

/**
 * THE FRAME ADDRESS IS NOT DERIVED HERE, AND THAT IS DELIBERATE.
 *
 * This module used to export `framePathForKey()`, which spelled the whole request line
 * into a file name with a `~XX` escape. That name grew with the request, and on
 * 2026-08-10 the longest one measured 218 characters of repository-relative path —
 * past the point where `git clone` into an ordinary `C:\Users\…\projects\mainline`
 * produces a working tree at all on a default Windows install. No escape could have
 * fixed it: the longest request key is 132 characters BEFORE escaping, and
 * `132 + 5 + 67` already exceeds the 198-character budget a 60-character clone
 * destination leaves. See `scripts/submission/check_path_lengths.py`.
 *
 * Frames are therefore named by content address — `<METHOD>-<sha256(key)[:16]>.json` —
 * which `scripts/capture-bundle.ts` computes when it writes them. This module cannot
 * reproduce that name and does not try: `src/data/**` computes no digests, by the same
 * rule that keeps the bundle verifier injected rather than inlined. A frame is looked up
 * BY KEY instead, through `manifest.files[].key` (see `bundle.ts`), which puts the
 * request line inside the sealed set the verifier hashes rather than on a directory
 * entry nothing checks.
 */

/** Builds the URL a live transport requests, relative to a base. */
export function urlFor(resolved: ResolvedRequest, baseUrl: string): string {
  const base = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
  const query = resolved.query
    .map(([name, value]) => `${encodeURIComponent(name)}=${encodeURIComponent(value)}`)
    .join('&');
  return query === '' ? `${base}${resolved.path}` : `${base}${resolved.path}?${query}`;
}
