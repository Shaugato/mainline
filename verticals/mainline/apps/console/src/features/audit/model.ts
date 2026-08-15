// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The audit surface's view model.
 *
 * ── WHY THIS FILE KNOWS NO COLUMN NAMES ───────────────────────────────────────────
 *
 * The `mainline_audit.v_*` column contracts belong to the recall and MCP domains, not to
 * the console (`docs/leads/ui.md` §4). `contracts/audit.schema.json` therefore describes a
 * GENERIC tabular shape — columns declared by the payload, rows positional against them —
 * and this module renders whatever arrives. Inventing a column list here would be the
 * console asserting something about a view it does not own, and it would break silently
 * the first time another domain added a column.
 *
 * ── WHY THE CAPS ARE A FIRST-CLASS FIELD ──────────────────────────────────────────
 *
 * ARCHITECTURE.md §17: each view is designed to return ≤ 25 rows and ≤ 10 KiB, and *these
 * views are a product surface and their size limit is a functional requirement*. A payload
 * that does not state the caps it ran under cannot be read as complete, so `capState`
 * below distinguishes four situations rather than showing a row count:
 *
 *   `within`      returned fewer rows and bytes than the caps
 *   `at-row-cap`  returned exactly the row cap — the result is very likely TRUNCATED
 *   `at-byte-cap` returned at or above the byte cap — same
 *   `unstated`    no caps were declared, so completeness is unknowable from here
 */

export interface AuditColumn {
  readonly name: string;
  readonly sql_type?: string | null;
}

export type AuditCell = string | number | boolean | null;

export interface AuditLimits {
  readonly row_cap: number;
  readonly byte_cap: number;
  readonly rows_returned: number;
  readonly bytes_returned: number;
}

export interface AuditTruncationFlag {
  readonly column: string;
  readonly complete: boolean;
}

export interface AuditView {
  readonly view: string;
  readonly columns: readonly AuditColumn[];
  readonly rows: readonly (readonly AuditCell[])[];
  readonly limits: AuditLimits;
  readonly truncation_flag: AuditTruncationFlag | null;
  readonly statement?: string | null;
}

export interface McpCall {
  readonly action_id: string;
  readonly agent_role: string;
  readonly tool: string;
  readonly transport: string;
  readonly model_id?: string | null;
  readonly prompt_version?: string | null;
  readonly subject_kind?: string | null;
  readonly subject_id?: string | null;
  readonly statement?: string | null;
  readonly plan_fragment?: string | null;
  readonly input_sha256?: string | null;
  readonly output_sha256?: string | null;
  readonly granted_scopes: readonly string[];
  readonly outcome: 'ok' | 'refused' | 'error' | 'abstained';
  readonly sqlstate?: string | null;
  readonly latency_ms?: number | null;
  readonly at: string;
}

export interface UnreachableProbe {
  readonly schema_name: string;
  readonly probe: string;
  readonly outcome: 'refused' | 'reachable' | 'not_probed';
  readonly sqlstate?: string | null;
}

export interface AuditPayload {
  readonly views: readonly AuditView[];
  readonly calls: readonly McpCall[];
  readonly unreachable?: readonly UnreachableProbe[];
}

// ── Which views carried rows ───────────────────────────────────────────────

export interface ViewCarriage {
  /** Views that returned at least one row, in the order the payload declared them. */
  readonly carrying: readonly AuditView[];
  /** Views that returned none, in the order the payload declared them. */
  readonly empty: readonly AuditView[];
  /**
   * Every view the payload carried, the ones with rows first.
   *
   * A RENDERING ORDER AND NOTHING ELSE. `carrying.length + empty.length === views.length`
   * is asserted by the test for this function, because the failure mode of a "put the
   * interesting ones first" helper is that it quietly becomes a filter and a reader never
   * learns that a view was read and came back empty.
   */
  readonly ordered: readonly AuditView[];
  readonly total: number;
  /** Verbatim. Rendered above the tables so a reader learns the ratio before scrolling. */
  readonly detail: string;
}

/**
 * How many of the views this payload carried came back with rows — and, crucially, what
 * that does NOT mean.
 *
 * This exists because of a measured misreading: the first view rendered was empty, and a
 * reader who scrolled it concluded that the whole surface was empty when six of fourteen
 * views carried rows. The remedy is a stated ratio and a reading order, never a hidden
 * view and never a softer sentence about the empty ones — `ViewTable` still prints *"An
 * empty aggregate is a statement about what was reachable under the caps above, not a
 * statement that nothing exists"* over every one of them, unchanged.
 */
export function readCarriage(views: readonly AuditView[]): ViewCarriage {
  const carrying = views.filter((view) => view.rows.length > 0);
  const empty = views.filter((view) => view.rows.length === 0);
  const total = views.length;

  const detail =
    total === 0
      ? 'No view was carried at all. That is a claim that nothing was read, not a claim that ' +
        'nothing exists.'
      : empty.length === 0
        ? `All ${total} view(s) this payload carried returned at least one row.`
        : `${carrying.length} of the ${total} view(s) this payload carried returned at least ` +
          `one row; ${empty.length} returned none. The ones with rows are printed first and ` +
          'the empty ones follow — that is a reading order and not a filter: every view the ' +
          'payload carried is below, each with its own caps and its own completeness flag. An ' +
          'empty aggregate is a statement about what was reachable under the caps that view ' +
          'declares, not a statement that nothing exists.';

  return { carrying, empty, ordered: [...carrying, ...empty], total, detail };
}

// ── Caps ───────────────────────────────────────────────────────────────────

export type CapState = 'within' | 'at-row-cap' | 'at-byte-cap' | 'unstated';

export interface CapReading {
  readonly state: CapState;
  /** Verbatim, rendered without paraphrase. */
  readonly detail: string;
}

/**
 * The caps, as one sentence a reader who has never met a row cap can act on.
 *
 * It goes BESIDE `capReading().detail`, never instead of it: the exact numbers stay, in
 * their own element, at their own precision (R8). What this adds is the fact a lay reader
 * is missing — that these are limits the read-only auditor account runs under for every
 * question it asks, rather than a property of the data it happened to find.
 *
 * Every number in it comes off `view.limits`. Nothing is written down here, so a view that
 * declares different caps gets a sentence about the caps it declares.
 */
export function capsPlain(view: AuditView): string {
  const limits = view.limits;
  if (limits.row_cap <= 0 || limits.byte_cap <= 0) {
    return (
      'This view did not say what limits it was read under, so nothing here tells you whether ' +
      'what you are looking at is all of it.'
    );
  }
  return (
    `The read-only account that asked this question is allowed at most ${limits.row_cap} rows ` +
    `and ${limits.byte_cap} bytes in the answer, every time it asks. This answer came back with ` +
    `${limits.rows_returned} row(s) and ${limits.bytes_returned} bytes.`
  );
}

export function capReading(view: AuditView): CapReading {
  const limits = view.limits;
  if (limits.row_cap <= 0 || limits.byte_cap <= 0) {
    return {
      state: 'unstated',
      detail:
        'this view declared no usable caps, so nothing here says whether the result is ' +
        'complete. A payload that does not state the caps it ran under cannot be read as ' +
        'complete.',
    };
  }
  if (limits.rows_returned >= limits.row_cap) {
    return {
      state: 'at-row-cap',
      detail:
        `${limits.rows_returned} rows returned against a cap of ${limits.row_cap}. The result is ` +
        'AT the cap, which means rows were very probably discarded. The Managed MCP surface ' +
        'caps a SELECT at 25 rows; a view that reaches it is a view whose aggregate is ' +
        'incomplete, not a view with exactly that many groups.',
    };
  }
  if (limits.bytes_returned >= limits.byte_cap) {
    return {
      state: 'at-byte-cap',
      detail:
        `${limits.bytes_returned} bytes returned against a cap of ${limits.byte_cap}. The ` +
        'response reached the 10 KiB ceiling, so it was cut.',
    };
  }
  return {
    state: 'within',
    detail:
      `${limits.rows_returned} of at most ${limits.row_cap} rows and ${limits.bytes_returned} of ` +
      `at most ${limits.byte_cap} bytes. The read finished inside both caps.`,
  };
}

// ── Completeness ───────────────────────────────────────────────────────────

export interface CompletenessReading {
  readonly known: boolean;
  readonly complete: boolean;
  /** Verbatim. */
  readonly detail: string;
}

/**
 * Every row carries `ancestry_complete` or its truncation flag — or the view says it
 * declares none, which is rendered as a claim about the VIEW rather than about the data.
 */
export function completeness(view: AuditView): CompletenessReading {
  const flag = view.truncation_flag;
  if (flag === null) {
    return {
      known: false,
      complete: false,
      detail:
        'this view makes no completeness claim: it declares no ancestry_complete column and no ' +
        'equivalent truncation flag. Read every number below as a statement about what was ' +
        'reachable, not about what exists.',
    };
  }
  return {
    known: true,
    complete: flag.complete,
    detail: flag.complete
      ? `every row this view aggregated had a complete blame closure (${flag.column} = true).`
      : `at least one row this view aggregated had a TRUNCATED blame closure (${flag.column} = ` +
        'false). The aggregate is an undercount, and by how much is not knowable from here.',
  };
}

// ── The MCP call log ───────────────────────────────────────────────────────

export interface CallTally {
  readonly total: number;
  readonly ok: number;
  readonly refused: number;
  readonly error: number;
  readonly abstained: number;
  /** Roles seen, sorted. Each maps 1:1 to the SQL role that executed the call. */
  readonly roles: readonly string[];
  /** Distinct granted scopes, sorted. */
  readonly scopes: readonly string[];
  /** True when no call carried a write verb in its granted scopes. */
  readonly readOnly: boolean;
  /** The scopes that made `readOnly` false, if any. */
  readonly writeScopes: readonly string[];
}

/**
 * Write verbs, matched against the granted scopes as recorded.
 *
 * This is a READING of the log, not an enforcement: the console cannot stop an agent from
 * writing, and saying it could would be exactly the kind of claim this screen exists to
 * make inspectable. What the reading gives a reader is the ability to see, rather than be
 * told, that the audit account was granted SELECT and nothing else — and to see it go
 * false the moment somebody grants more.
 */
const WRITE_VERBS = ['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'ALL'];

export function tallyCalls(calls: readonly McpCall[]): CallTally {
  const scopes = new Set<string>();
  const writeScopes = new Set<string>();
  for (const call of calls) {
    for (const scope of call.granted_scopes) {
      scopes.add(scope);
      const verb = scope.split(':').at(-1)?.toUpperCase() ?? '';
      if (WRITE_VERBS.includes(verb)) writeScopes.add(scope);
    }
  }
  return {
    total: calls.length,
    ok: calls.filter((call) => call.outcome === 'ok').length,
    refused: calls.filter((call) => call.outcome === 'refused').length,
    error: calls.filter((call) => call.outcome === 'error').length,
    abstained: calls.filter((call) => call.outcome === 'abstained').length,
    roles: [...new Set(calls.map((call) => call.agent_role))].sort(),
    scopes: [...scopes].sort(),
    readOnly: writeScopes.size === 0,
    writeScopes: [...writeScopes].sort(),
  };
}

// ── The negative assertion ─────────────────────────────────────────────────

export interface UnreachableReading {
  readonly probes: readonly UnreachableProbe[];
  /** True when every listed schema was actually probed AND refused. */
  readonly allRefused: boolean;
  /** Verbatim. */
  readonly detail: string;
}

/**
 * `mainline_qa` must be unreachable, and an EMPTY array is not evidence of that.
 *
 * `contracts/audit.schema.json` says it outright: *an empty array is a claim that nothing
 * was checked, not a claim that nothing is reachable*. The three outcomes are therefore
 * kept distinct all the way to the screen — `refused` is the assertion, `not_probed` is an
 * absence, and `reachable` is a finding that would end the deployment.
 */
// ── Why an empty result is empty ───────────────────────────────────────────

/**
 * WHAT THIS SCREEN SAYS BESIDE A ZERO, AND WHAT IT IS FORBIDDEN TO SAY.
 *
 * Ruling R3: *an empty result must say why it is empty, in a sentence, and must never be
 * filled.* Measured against the live URL on 2026-08-15, `GET /v1/audit` answers 200 with
 * fourteen views — six carrying one row each, eight carrying none — `calls: []`, and one
 * `unreachable` entry whose `probe` field says, in the emitter's own words, that the demo
 * API connects as the demo's own read role and not as the Managed-MCP service account.
 * Every one of those zeros is TRUE and none of them is repaired here.
 *
 * The defect this repairs is that the screen threw that sentence away everywhere except
 * one panel at the bottom of the page. A reader who scrolled an empty aggregate met "No
 * rows" with nothing beside it and had no way to tell a fact about this deployment from a
 * claim about the world.
 *
 * ── THE LINE THIS FUNCTION WILL NOT CROSS ────────────────────────────────────────
 *
 * The probe sentence explains why `mainline_qa` was NOT PROBED. It does not say why any
 * particular view came back empty, and this function does not pretend that it does. What
 * it returns is:
 *
 *   • the CATEGORY of the emptiness — a fact about what was reachable here, never a claim
 *     that no such record exists; and
 *   • the kernel's own sentence about this deployment, quoted VERBATIM (R8) so a reader
 *     can judge for themselves how far it reaches.
 *
 * No branch below picks a sentence based on a code, composes a reason the payload did not
 * carry, or attributes a cause the emitter did not state.
 */
export interface EmptinessReason {
  /** The console's own sentence about what a zero here is and is not. */
  readonly category: string;
  /** The kernel's sentences, verbatim, in payload order. Empty when it carried none. */
  readonly quoted: readonly string[];
  /** What the reader is looking at when `quoted` is empty. Never reassuring. */
  readonly unquoted: string | null;
}

const EMPTY_IS_ABOUT_THIS_DEPLOYMENT =
  'and here is the reason there are none, which is a fact about this deployment and not about ' +
  'any record.';

export function emptinessReason(probes: readonly UnreachableProbe[]): EmptinessReason {
  const quoted = probes.map((probe) => probe.probe).filter((sentence) => sentence.trim() !== '');
  return {
    category: EMPTY_IS_ABOUT_THIS_DEPLOYMENT,
    quoted,
    unquoted:
      quoted.length > 0
        ? null
        : 'This payload carried no sentence about what the account that produced it can and ' +
          'cannot reach, so nothing here explains the zero beyond the zero itself. That is a ' +
          'gap in what you are being shown, not a finding about any record.',
  };
}

export function readUnreachable(probes: readonly UnreachableProbe[]): UnreachableReading {
  if (probes.length === 0) {
    return {
      probes,
      allRefused: false,
      detail:
        'No negative probe was carried at all. That is a claim that nothing was checked, not a ' +
        'claim that nothing is reachable. In particular, nothing here shows that mainline_qa — ' +
        'which holds the per-named-person deliberation measures and for which no MCP service ' +
        'account is ever issued — is out of reach.',
    };
  }
  const reachable = probes.filter((probe) => probe.outcome === 'reachable');
  const notProbed = probes.filter((probe) => probe.outcome === 'not_probed');
  if (reachable.length > 0) {
    return {
      probes,
      allRefused: false,
      detail:
        `${reachable.length} schema(s) that must be unreachable ARE reachable from the audit ` +
        `account: ${reachable.map((probe) => probe.schema_name).join(', ')}. This is a finding ` +
        'against the deployment, not against this payload.',
    };
  }
  if (notProbed.length > 0) {
    return {
      probes,
      allRefused: false,
      detail:
        `${notProbed.length} schema(s) were listed but not probed ` +
        `(${notProbed.map((probe) => probe.schema_name).join(', ')}). A listed-but-unprobed ` +
        'schema establishes nothing.',
    };
  }
  return {
    probes,
    allRefused: true,
    detail:
      `${probes.length} probe(s) ran and every one was refused by the database. The refusal is ` +
      'the assertion: the audit account asked, and the SQLSTATE came back.',
  };
}
