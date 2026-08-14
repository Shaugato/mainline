// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/* eslint-disable */
/**
 * GENERATED FILE — DO NOT EDIT.
 *
 * Produced by `node scripts/gen-types.ts` from `contracts/*.schema.json`.
 * Regenerate after any contract change; `node scripts/gen-types.ts --check` fails CI
 * when this file and the contracts have drifted apart.
 *
 * What these types DO carry: the field names, their nullability, whether they are
 * optional, and every closed vocabulary in the read model as a literal union.
 *
 * What they do NOT carry, and cannot: `pattern`, `format`, `minimum`, `maxItems`,
 * `if`/`then`/`else` and the rest of the refinement keywords. Those are enforced at
 * RUNTIME by `src/data/schema.ts` against the same contract files, on every payload,
 * before a surface sees it. A type here is a shape, not a guarantee — the guarantee is
 * the validation the transport performs, and no code in this console may treat a
 * successful compile as evidence that a payload was well formed.
 */

/** A JSON value, for positions a contract deliberately leaves open. Never `any`. */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

/** A JSON object whose members a contract does not constrain. */
export type JsonObject = { readonly [key: string]: JsonValue };

/**
 * The ONE open-map alias in the generated read model.
 *
 * It appears only where a schema declares `additionalProperties` without `properties`,
 * which in this repository happens only inside the specification-owned refusal contract
 * (`ext` and the authority-gap `key`). Everything else is a closed set of named fields.
 * Grep for `StringMap` to find every open position in the model.
 */
export type StringMap<T> = { readonly [key: string]: T };

// ──────────────────────────────────────────────────────────────────────────
// ancestry.schema.json — MAINLINE console — clause ancestry projection
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline.clause_blame_current over mainline.clause_blame_closure (ARCHITECTURE.md §5.4),
 * resolved into the events, event edges and commit chain a renderer needs. NO PERSON APPEARS
 * IN THIS CONTRACT. Events carry titles and severities; people do not. That is I15 and §11.5's
 * Attribution Rule carried into the payload, one hop before it could reach a screenshot (D15).
 */

export type AncestryResponse = ReadEnvelope & {
  readonly data: {
    readonly clause_uuid: Uuid;
    readonly as_of_commit: CommitId;
    /** The ledger checkpoint root this ancestry was closed against. It goes in the printed exhibit's caption block. */
    readonly corpus_root?: Sha256Hex | null;
    readonly closure: BlameClosure;
    readonly truncation: Truncation;
    readonly events: readonly AncestryEvent[];
    readonly event_edges: readonly EventEdge[];
    readonly blame_edges: readonly BlameEdge[];
    /** The identity-preserving reflows: every clause_version of this clause from birth to as_of_commit, oldest first. This is the third axis of the walk — the axis is TIME. */
    readonly commit_chain: readonly CommitLink[];
  };
};

/**
 * One row of mainline.clause_blame_current — the DISTINCT ON (clause_uuid, as_of_commit) view
 * taking max(closure_gen). Append-only, generation-versioned, monotone and ledgered (S2):
 * max_severity must be non-decreasing across generations, and a mass rewrite downward either
 * violates that or leaves a generation gap.
 */

export type BlameClosure = {
  readonly closure_gen: number;
  readonly ancestor_count: number;
  readonly max_severity: Severity;
  readonly virulence: VirulenceClass;
  readonly depth: number;
  readonly truncated: boolean;
  /** agent_identity of the projector. A projection with no named projector is a projection nobody owns. */
  readonly computed_by: string;
  readonly projector_ver: string;
  readonly computed_at: Timestamp;
};

export type AncestryEvent = {
  readonly event_id: Uuid;
  readonly kind: EventKind;
  readonly external_ref?: string | null;
  /** The event's own title. It names a failure, never a person. */
  readonly title: string;
  readonly occurred_at: Timestamp;
  /** Bitemporal: both, always. A 2013 event ingested in 2024 must never look like a 2024 event. */
  readonly ingested_at?: Timestamp | null;
  readonly severity_gate: Severity;
  readonly severity_basis: "coded_field" | "regulator_class" | "human_rated" | "model_rated";
  /** ICAM/bowtie normalised to one shape. control_class is the join key to a clause's CAT control class. */
  readonly control_failures?: readonly ({
    readonly control_class: string;
    readonly barrier_role: "preventive" | "recovery";
    readonly failure_mode: "absent" | "ineffective" | "bypassed" | "degraded" | "not_verified";
    readonly hazard_energy: "gravity" | "pressure" | "electrical" | "thermal" | "chemical" | "kinetic" | "biological" | "radiation";
    readonly icam_tier?: string | null;
  })[];
};

export type EventEdge = {
  readonly child_event_id: Uuid;
  readonly parent_event_id: Uuid;
  readonly relation: EventRelation;
};

/**
 * BASIS-GRADED FORCE. An inferred_semantic edge can never be 'active' (CHECK
 * inference_never_blocks), and the console must render `basis` beside every edge — an inferred
 * edge shown as though it were asserted is precisely the rubber stamp this design refuses to
 * build.
 */

export type BlameEdge = {
  readonly event_id: Uuid;
  readonly clause_uuid: Uuid;
  readonly basis: BlameBasis;
  readonly state: BlameState;
  readonly commit_id: CommitId;
  readonly p_link?: number | null;
  /** Prose a human is shown; never a bare number. */
  readonly attribution?: string | null;
  readonly evidence_quote_sha256?: Sha256Hex | null;
};

export type CommitLink = {
  readonly commit_id: CommitId;
  readonly gen: number;
  readonly committed_at: Timestamp;
  readonly control_delta: ControlDelta;
  readonly printed_label?: string | null;
  readonly sev_max?: Severity;
  readonly canon_sha256?: Sha256Hex | null;
};

// ──────────────────────────────────────────────────────────────────────────
// audit.schema.json — MAINLINE console — audit views and MCP calls
// ──────────────────────────────────────────────────────────────────────────

/**
 * ARCHITECTURE.md §17. The v_* views are a PRODUCT SURFACE whose size limit is a functional
 * requirement: each returns <= 25 rows and <= 10 KiB and carries ancestry_complete or an
 * equivalent truncation flag. Their column contracts belong to the recall and MCP domains, not
 * to the console, so this schema describes the GENERIC tabular shape — columns declared by the
 * payload, rows positional against them — and the audit surface renders whatever columns
 * arrive. Inventing a column list here would be the console asserting something about a view
 * it does not own.
 */

export type AuditResponse = ReadEnvelope & {
  readonly data: {
    readonly views: readonly AuditView[];
    readonly calls: readonly McpCall[];
    /** The negative assertion beside the positive ones: schemas the MCP service account must NOT be able to reach (mainline_qa above all). An empty array is a claim that nothing was checked, not a claim that nothing is reachable. */
    readonly unreachable?: readonly ({
      readonly schema_name: string;
      readonly probe: string;
      readonly outcome: "refused" | "reachable" | "not_probed";
      readonly sqlstate?: string | null;
    })[];
  };
};

export type AuditView = {
  /** Fully qualified view name, e.g. mainline_audit.v_open_gate_summary. */
  readonly view: string;
  readonly columns: readonly ({
    readonly name: string;
    readonly sql_type?: string | null;
  })[];
  /** Positional against `columns`. Values are rendered as strings, numbers, booleans or null exactly as the driver produced them; the console does not coerce. */
  readonly rows: readonly (readonly (string | number | boolean | null)[])[];
  /** The caps the read ran under. The Managed MCP surface caps a SELECT at 25 rows and a response at 10 KiB; a payload that does not state the caps it ran under cannot be read as complete. */
  readonly limits: {
    readonly row_cap: number;
    readonly byte_cap: number;
    readonly rows_returned: number;
    readonly bytes_returned: number;
  };
  /** The name of the column in this view that carries ancestry_complete or its equivalent, and its value. Null when the view declares none — which the console displays as 'this view makes no completeness claim'. */
  readonly truncation_flag: {
    readonly column: string;
    readonly complete: boolean;
  } | null;
  /** The single statement that produced these rows, verbatim. The Managed MCP allows ONE statement per call, <= 16384 characters. */
  readonly statement?: string | null;
};

/**
 * One Managed-MCP round trip, from mainline_meas.agent_action. The audit screen shows what the
 * read-only account asked and what it got, so that 'the agent could not have written anything'
 * is inspectable rather than asserted.
 */

export type McpCall = {
  readonly action_id: Uuid;
  /** Maps 1:1 to the SQL role that executed it. */
  readonly agent_role: string;
  readonly tool: string;
  readonly transport: "pgwire" | "mcp" | "bedrock" | "ccloud" | "s3";
  readonly model_id?: string | null;
  readonly prompt_version?: string | null;
  readonly subject_kind?: string | null;
  readonly subject_id?: Uuid | null;
  readonly statement?: string | null;
  /** The EXPLAIN fragment returned, if any. EXPLAIN ANALYZE is not available on the Managed MCP surface, so this is a plan, never a measurement, and the console labels it so. */
  readonly plan_fragment?: string | null;
  readonly input_sha256?: Sha256Hex | null;
  readonly output_sha256?: Sha256Hex | null;
  readonly granted_scopes: readonly string[];
  readonly outcome: "ok" | "refused" | "error" | "abstained";
  readonly sqlstate?: string | null;
  readonly latency_ms?: number | null;
  readonly at: Timestamp;
};

// ──────────────────────────────────────────────────────────────────────────
// blocking-check.schema.json — MAINLINE console — blocking checks
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline.blocking_check, ARCHITECTURE.md §5.5. severity, virulence and closure_gen are
 * PROJECTIONS overwritten by fn_check_project from clause_blame_current — they are never
 * inputs (S1), and the console renders them with a db:column chip precisely because nobody who
 * wrote the check chose them.
 */

export type BlockingChecksResponse = ReadEnvelope & {
  readonly data: {
    readonly subject_kind: SubjectKind;
    readonly subject_id: Uuid;
    readonly gate_epoch: GateEpoch;
    readonly checks: readonly BlockingCheck[];
  };
};

export type BlockingCheck = {
  readonly check_id: Uuid;
  readonly subject_kind: SubjectKind;
  readonly permit_id?: Uuid | null;
  readonly cr_id?: Uuid | null;
  readonly site_id: Uuid;
  readonly clause_uuid: Uuid;
  readonly commit_id: CommitId;
  /** clause_version.printed_label, e.g. '7.3.2(b)'. Presentation only — NEVER identity. */
  readonly clause_label?: string | null;
  readonly precursor_event_id?: Uuid | null;
  readonly origin: CheckOrigin;
  readonly severity: Severity;
  readonly virulence: VirulenceClass;
  /** Which generation of the blame closure armed this check. A mass rewrite downward shows here as a generation gap (S2). */
  readonly closure_gen: number;
  readonly control_delta?: ControlDelta | null;
  readonly recall_run_id?: Uuid | null;
  /** The reranker's mechanism-citing justification, verbatim. The console never summarises it further. */
  readonly evidence_summary: string;
  readonly materialised_at: Timestamp;
  /** The STORED digest column. S5: NULLs are distinct in a unique index, so six of the eight origins would not dedupe without it. */
  readonly dedupe_key: Sha256Hex;
  /** True when no live (non-retracted) disposition references this check. Computed by the read API from the one_live_disposition partial unique index, never by the console. */
  readonly open: boolean;
  readonly disposition_id?: Uuid | null;
  /** The precursor event, denormalised for display. Carries no person's name — I15 and §11.5's Attribution Rule. */
  readonly precursor?: PrecursorEvent | null;
};

export type PrecursorEvent = {
  readonly event_id: Uuid;
  readonly kind: EventKind;
  readonly external_ref?: string | null;
  readonly title: string;
  readonly occurred_at: Timestamp;
  readonly severity_actual?: Severity | null;
  readonly severity_potential?: Severity | null;
  readonly severity_gate: Severity;
  /** CHECK model_cannot_arm: severity_gate >= 4 with basis 'model_rated' is not a representable row. An LLM's potential rating alone may never arm a blocking gate. */
  readonly severity_basis: "coded_field" | "regulator_class" | "human_rated" | "model_rated";
  /** S3 Object Lock version id of the raw bytes. A pointer a third party can follow. */
  readonly source_object_key?: string | null;
  readonly source_sha256?: Sha256Hex | null;
};

// ──────────────────────────────────────────────────────────────────────────
// bundle.schema.json — MAINLINE console — EvidenceBundle manifest
// ──────────────────────────────────────────────────────────────────────────

/**
 * The console's replay transport (D7). DISTINCT FROM spec/wire/evidence-bundle.md, which is
 * the custody bundle a stranger runs `trappoint-verify` against — that artefact is CARRIED
 * here, verbatim, under ledger/. This one is a content-addressed directory of captured HTTP
 * exchanges; the manifest is the only file whose digest is not listed inside itself, which is
 * why the manifest digest is what the honesty chrome displays.
 */

export type EvidenceBundleManifest = {
  /** MUST be 1. A player that does not recognise the version refuses to serve, rather than guessing which fields still mean what they used to. */
  readonly manifest_version: 1;
  /** Stable identity of this capture. Two bundles with the same id and different file digests are a contradiction the player reports rather than resolves. */
  readonly bundle_id: string;
  readonly captured_at: Timestamp;
  /** Provenance, not evidence. No check reads it. */
  readonly generator?: string | null;
  readonly cluster_fingerprint: ClusterFingerprint;
  /** The database schema digest the capture ran against, or a named migration head. A bundle that cannot say which schema produced it cannot be replayed against a claim about that schema. */
  readonly schema_version: string;
  /** True when any frame in this bundle is hand-authored rather than captured from a running system. Every screen fed by a staged bundle says STAGED, permanently and non-dismissibly (D16). */
  readonly staged: boolean;
  /** Required and non-null exactly when `staged` is true. */
  readonly staged_note?: string | null;
  /** The ledger checkpoint this bundle is anchored to, or null. Null means the bundle carries no custody anchor at all, which the console renders as an absence rather than as an unverified state. */
  readonly checkpoint: CheckpointRef | null;
  /** Every file in the bundle except manifest.json itself, with its digest. Paths are relative, forward-slashed, and may not contain '..' or a leading '/'. */
  readonly files: readonly FileEntry[];
};

export type NamedValue = {
  readonly name: string;
  readonly value: string;
};

export type FileEntry = {
  /** Relative, forward-slashed, no '..' and no leading '/'. Frames are named `frames/<METHOD>-<sha256(key)[:16]>.json` by scripts/capture-bundle.ts. `~` remains admitted for non-frame content only; it was the escape character of the retired request-line naming scheme, which produced 218-character repository paths that a default Windows install cannot check out (scripts/submission/check_path_lengths.py). */
  readonly path: string;
  readonly sha256: Sha256Hex;
  /** Byte length. A length mismatch is caught before a digest is computed, which is the difference between a clear error and a silent one on a truncated download. */
  readonly bytes: number;
  readonly media_type?: string | null;
  /** Frames only: the canonical request key this frame answers, verbatim, and the ONLY way a player addresses it. The file name is a content address and carries no request information, so this field is where the request line lives — inside the sealed set the verifier hashes, rather than on a directory entry nothing checks. The frame repeats its own key and the transport compares the two on every exchange, so the manifest is an index that cannot silently disagree with what it indexes. */
  readonly key?: string;
};

/**
 * What the bundle claims about the cluster behind it. `source` is load-bearing: observed =
 * read from a live cluster during capture; declared = written by hand from a recorded
 * measurement, which is a weaker claim and is displayed as one.
 */

export type ClusterFingerprint = {
  readonly source: "observed" | "declared";
  readonly product: string;
  readonly version: string;
  readonly cluster_version?: string | null;
  readonly tier?: string | null;
  /** Stated precisely. Residency claims are split in this deployment — inference in Australia, database in Singapore — and any end-to-end Australian residency claim is FALSE and must not appear on any screen fed by this bundle. */
  readonly region: string;
  /** Where the measurement behind a `declared` fingerprint is recorded. */
  readonly evidence_ref?: string | null;
};

export type CheckpointRef = {
  readonly site_code: string;
  readonly tree_size: number;
  readonly root_hex: Sha256Hex;
  /** Path inside this bundle to the verbatim signed note. It must also appear in `files`. */
  readonly note_path: string;
  /** Path to the spec/wire/evidence-bundle.md v1.0 artefact, if carried. That file is what `uvx trappoint-verify verify --bundle` consumes; this console bundle merely transports it. */
  readonly custody_bundle_path?: string | null;
};

/**
 * One captured request/response pair. Bodies are base64 so the capture is byte-for-byte: a
 * frame that stored a re-serialised JSON object would be testing our JSON writer, not the
 * server's output.
 */

export type EvidenceBundleFrame = {
  readonly frame_version: 1;
  /** The canonical request key, derived by src/data/resources.ts from method, path and sorted query. The file name is the SHA-256 content address of this string, so the frame and its name cannot drift apart without `capture-bundle.ts check` saying so; the manifest carries the same string as the player's index. */
  readonly key: string;
  readonly request: {
    readonly method: "GET" | "POST";
    readonly path: string;
    /** Ordered name/value pairs. A list rather than an object because the canonical request key sorts them itself, and because an object here would put an index signature into the generated read model. */
    readonly query?: readonly NamedValue[];
    readonly body_b64?: string | null;
  };
  readonly response: {
    readonly status: number;
    /** Only the headers the console reads — content-type and date. A capture that stored every header would carry credentials, which is why this is an allowlist enforced by the capture script and not a copy of the response. */
    readonly headers?: readonly NamedValue[];
    readonly body_b64: string;
  };
  readonly captured_at: Timestamp;
  readonly duration_ms?: number | null;
};

// ──────────────────────────────────────────────────────────────────────────
// change-request.schema.json — MAINLINE console — change request
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline.change_request, ARCHITECTURE.md §5.5. S16: making the change request a gated
 * subject is what turns 'the permit is a protected branch' into 'the repository is a protected
 * branch and the permit is one of its refs'. It has three projected counters and four named
 * refusals, not seven and seven — a smaller gate is still a gate, and pretending otherwise
 * would be a schema that lies about the DDL.
 */

export type ChangeRequestResponse = ReadEnvelope & {
  readonly data: ChangeRequest;
};

export type ChangeRequest = {
  readonly cr_id: Uuid;
  readonly site_id: Uuid;
  /** The customer's management-of-change identifier, e.g. MOC-2026-0413. */
  readonly external_ref: string;
  readonly ref_name: string;
  /** The protected branch it wants to merge into. */
  readonly target_ref: string;
  readonly state: SubjectState;
  readonly head_seq: number;
  readonly gate_epoch: GateEpoch;
  readonly merged_commit?: CommitId | null;
  readonly opened_at: Timestamp;
  readonly counters: {
    readonly open_blocking: Counter;
    readonly open_residue: Counter;
    readonly open_conflicts: Counter;
  };
  readonly constraints: readonly GateConstraint[];
};

// ──────────────────────────────────────────────────────────────────────────
// clause.schema.json — MAINLINE console — clause version and delta witness
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline.clause_version (ARCHITECTURE.md §5.3) plus the DeltaVerdict / DeltaWitness contract
 * published by the algorithms domain (mainline_domain.contracts). Decision D8 there: a
 * weaken/remove with delta_basis='lattice' whose witness rows were not written in the same
 * transaction is REFUSED by fn_delta_witness_guard with P0001 — an unexplainable weaken
 * verdict does not get to exist. When the witnesses are nonetheless absent from a payload, the
 * console renders an explicit WITNESS UNAVAILABLE state and never an inferred explanation.
 */

export type ClauseResponse = ReadEnvelope & {
  readonly data: {
    readonly clause_uuid: Uuid;
    readonly version: ClauseVersion;
    /** The ancestor version this one edits, when the read API resolved it. */
    readonly parent?: ClauseVersion | null;
    readonly delta: DeltaVerdict;
  };
};

export type ClauseVersion = {
  readonly clause_uuid: Uuid;
  /** Denormalised from commit_obj for bisect ordering. */
  readonly gen: number;
  readonly commit_id: CommitId;
  readonly site_id: Uuid;
  readonly doc_id?: Uuid | null;
  /** The level-1 archival activity code. It is also the vector-index prefix, which is why blame survives an asset-tag churn. */
  readonly activity_root: string;
  readonly parent_version?: CommitId | null;
  /** Presentation only, NEVER identity. */
  readonly ordinal?: number;
  readonly printed_label?: string | null;
  readonly raw_text?: string | null;
  /** Offsets are ALWAYS into canon_text. The console highlights spans against this string and no other. */
  readonly canon_text: string;
  readonly canon_version: number;
  readonly canon_sha256: Sha256Hex;
  /** Tags, setpoints, citations, CAS numbers, roles. An anchor dropped between versions is one of the residue reasons. */
  readonly anchor_set: readonly string[];
  readonly cat_key?: string | null;
  /** The normalised Control Assertion Tuple. Shape is owned by the algorithms domain; the console renders it as structured data and asserts nothing about its internals. */
  readonly cat_json?: JsonObject | null;
  readonly cat_confidence?: "ok" | "low" | "opaque";
  readonly control_delta: ControlDelta;
  readonly delta_basis: DeltaBasis;
  readonly delta_model?: string | null;
  readonly delta_prompt_version?: string | null;
  /** MMR root over the severity-monotone lineage accumulator (M2). */
  readonly blood_root?: Sha256Hex | null;
  readonly blood_size?: number | null;
  /** The worst severity anywhere in this version's blame lineage. Projected; never chosen. */
  readonly sev_max: Severity;
};

/**
 * One element of the minimal unsatisfiable subset behind a delta verdict. Field names mirror
 * mainline_domain.contracts.DeltaWitness exactly.
 */

export type DeltaWitness = {
  readonly rule_id: string;
  readonly field: string;
  readonly from_repr: string;
  readonly to_repr: string;
  readonly note: string;
};

/**
 * mainline_domain.contracts.DeltaVerdict. `witnesses` may be null — meaning the payload
 * carries no witness rows — which the console renders as WITNESS UNAVAILABLE. An empty array
 * is a DIFFERENT claim: the emitter says there are none.
 */

export type DeltaVerdict = {
  readonly delta: ControlDelta;
  readonly basis: DeltaBasis;
  readonly witnesses: readonly DeltaWitness[] | null;
  /** Whether the witness set is a minimal unsatisfiable subset. Null when the emitter did not establish minimality — an unproven claim of minimality is worse than none. */
  readonly minimal: boolean | null;
};

// ──────────────────────────────────────────────────────────────────────────
// common.schema.json — MAINLINE console — shared definitions
// ──────────────────────────────────────────────────────────────────────────

/**
 * RFC 4122 textual UUID, as the read API renders a UUID column.
 */

export type Uuid = string;

/**
 * A BYTES column rendered as lowercase hexadecimal, as encode(col,'hex') produces. Even
 * length, because a half byte is not a byte.
 */

export type Hex = string;

/**
 * Exactly 32 bytes of lowercase hexadecimal. Presence is not verification — the console
 * re-derives digests in a Worker (D6) and this shape says nothing about whether one matched.
 */

export type Sha256Hex = string;

/**
 * mainline.commit_obj.commit_id, hex-rendered. Never truncated for display in the wire
 * payload; truncation is a rendering decision the console makes visibly.
 */

export type CommitId = Hex;

/**
 * RFC 3339 instant. The read API renders every TIMESTAMPTZ in UTC.
 */

export type Timestamp = string;

/**
 * mainline.event severity, 0..5. 5 is a fatality.
 */

export type Severity = number;

/**
 * A projected non-negative counter. Written by a trigger from an authoritative table, never by
 * the inserter (P2).
 */

export type Counter = number;

/**
 * The subject's gate_epoch. Increments whenever the gate opens; the merge_record composite FK
 * pins it, so an issued subject's epoch physically cannot move (ARCHITECTURE.md §5.5).
 */

export type GateEpoch = number;

/**
 * The two gated subject kinds. There is no third.
 */

export type SubjectKind = "permit" | "change_request";

/**
 * mainline.subject_state, migration 0011.
 */

export type SubjectState = "draft" | "checks_materialised" | "dispositioned" | "merged" | "suspended" | "closed" | "abandoned";

/**
 * mainline.control_delta, migration 0010.
 */

export type ControlDelta = "introduce" | "strengthen" | "restate" | "weaken" | "remove";

/**
 * clause_version.delta_basis CHECK, ARCHITECTURE.md §5.3.
 */

export type DeltaBasis = "lattice" | "lattice+model" | "abstain_to_weaken" | "human";

/**
 * mainline.disposition_kind, migration 0012.
 */

export type DispositionKind = "applied" | "mitigated" | "mechanism_absent" | "escalated" | "accept_residual" | "emergency_override";

/**
 * mainline.virulence_class, migration 0013. Banded exactly once, in clause_blame_closure, and
 * projected everywhere else.
 */

export type VirulenceClass = "routine" | "serious" | "blood_major" | "blood_fatal";

/**
 * mainline.blame_basis, migration 0014. inferred_semantic can never reach state 'active'
 * (constraint inference_never_blocks).
 */

export type BlameBasis = "asserted_document" | "asserted_human" | "derived_documentary" | "inferred_semantic";

/**
 * mainline.blame_state, migration 0015.
 */

export type BlameState = "active" | "provisional" | "dormant" | "refuted";

/**
 * mainline.prop_state, migration 0016.
 */

export type PropState = "proposed" | "already_present" | "conflicted" | "adopted" | "declined" | "revoked";

/**
 * blocking_check.origin CHECK, ARCHITECTURE.md §5.5. Eight origins, closed.
 */

export type CheckOrigin = "blame_ancestry" | "weaken_over_blood" | "identity_residue" | "drift_finding" | "fleet_conflict" | "discordance_warrant" | "severity_downgrade" | "recall_probabilistic";

/**
 * mainline.event.kind CHECK, ARCHITECTURE.md §5.4.
 */

export type EventKind = "incident" | "near_miss" | "regulator_notice" | "oem_alert" | "audit_finding" | "capa";

/**
 * mainline.event_edge.relation CHECK, ARCHITECTURE.md §5.4.
 */

export type EventRelation = "recurrence_of" | "precursor_of" | "supersedes";

/**
 * permit_clause.relation CHECK. The change-request side uses cr_relation.
 */

export type ClauseRelation = "waives" | "weakens" | "relies_on" | "cites";

/**
 * D5: every gate-relevant number is rendered verbatim with a provenance chip. db:column = a
 * column the database wrote; db:constraint = the name of a CHECK/FK the database reported;
 * recomputed = the console re-derived it in a Worker from signed bytes (D6); staged =
 * hand-authored demonstration data with no cluster behind it; derived = computed by the read
 * API from columns it names in statement_refs.
 */

export type ProvenanceChip = "db:column" | "db:constraint" | "recomputed" | "staged" | "derived";

/**
 * Which chip the console must render beside which value. A pointer absent from this list has
 * NO chip and is rendered without one — an unclaimed provenance is better than a comfortable
 * default. It is a LIST rather than an object keyed by pointer so that the generated
 * TypeScript carries no open-ended index signature: the read model is a closed set of named
 * fields, and its type should say so.
 */

export type FieldProvenance = readonly ({
  /** RFC 6901 JSON Pointer into `data`. */
  readonly pointer: string;
  readonly chip: ProvenanceChip;
})[];

/**
 * Where a payload came from, named precisely enough that a reader can run it. `text` is the
 * statement VERBATIM when the bundle carries one; null when the read API declined to disclose
 * it.
 */

export type StatementRef = {
  readonly kind: "table" | "view" | "procedure" | "statement";
  readonly object: string;
  readonly text?: string | null;
  /** Path inside the evidence bundle to the verbatim round trip (sql/*.txt), when one was captured. */
  readonly sql_path?: string | null;
};

/**
 * A truncated closure must never be indistinguishable from a complete one (ARCHITECTURE.md
 * §5.4). Every payload that walks ancestry carries this.
 */

export type Truncation = {
  readonly ancestry_complete: boolean;
  readonly truncated: boolean;
  /** The ancestor cap in force when the closure was computed (512 in ARCHITECTURE.md §5.4). */
  readonly cap: number;
  readonly spilled_count?: number | null;
};

// ──────────────────────────────────────────────────────────────────────────
// disposition.schema.json — MAINLINE console — disposition
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline.disposition, mainline.clearance_legal and mainline.defeater_option, ARCHITECTURE.md
 * §5.5 and §5.0. The countersigner field exists on this screen when — and only when — the
 * clearance lattice row for (virulence, kind) sets req_second_signer. A feature flag that
 * produced the same field would pass a naive test and is exactly the lie BUILD_PLAN §3 warns
 * about, so the flag is not in this contract and cannot be.
 */

export type DispositionResponse = ReadEnvelope & {
  readonly data: {
    readonly check_id: Uuid;
    /** Projected onto the disposition from clause_blame_current (S1). It is the first half of the composite FK into clearance_legal, and it is not a field a signer chooses. */
    readonly virulence: VirulenceClass;
    /** Every clearance_legal row for this virulence. A (virulence, kind) pair ABSENT from this array is not a disallowed option — it is a NON-EXISTENT one, and attempting it produces SQLSTATE 23503 on fk_clearance. The console renders the absence as an absence. */
    readonly lattice: readonly ClearanceLegal[];
    /** Generated PER CHECK. There is no global 'not applicable' anywhere in this product. */
    readonly defeater_options: readonly DefeaterOption[];
    /** S19: t_min(R) = tau0 + (sum of tokens dispositioned against R) / rho. Breaching it does not raise — it records, projects permit.unmet_floor_count, and prices the consequence in a second signature. */
    readonly reading_floor?: ReadingFloor | null;
    /** The recorded disposition, or null when none exists yet. */
    readonly signed: Disposition | null;
  };
};

/**
 * One row of the clearance lattice. The customer's officer approved it; we did not.
 */

export type ClearanceLegal = {
  readonly virulence: VirulenceClass;
  readonly kind: DispositionKind;
  readonly req_compensating: boolean;
  readonly req_second_signer: boolean;
  readonly req_foreign_org: boolean;
  readonly req_predicate: boolean;
  readonly req_reassert: boolean;
  readonly min_signer_rank: number;
  readonly max_ttl_hours: number | null;
  readonly policy_version: string;
  readonly approved_by_sub: string;
  readonly approved_at: Timestamp;
};

export type DefeaterOption = {
  readonly check_id: Uuid;
  readonly defeater_code: string;
  /** e.g. 'which precondition of this mechanism is absent?' — the question the vocabulary answers. */
  readonly prompt: string;
  /** Pins WHICH vocabulary was offered. A disposition records the same digest, so a later regeneration cannot silently reinterpret a past signature. */
  readonly vocab_sha256: Sha256Hex;
};

export type ReadingFloor = {
  readonly tokens_cumulative: number;
  readonly rho_tokens_per_second: number;
  readonly tau0_seconds: number;
  readonly t_min_seconds: number;
  readonly elapsed_seconds: number;
  /** Positive polarity (D1), and computed by the server, not chosen. The console renders the arithmetic beside it so the number is checkable rather than believable. */
  readonly met: boolean;
};

export type Disposition = {
  readonly disposition_id: Uuid;
  readonly check_id: Uuid;
  readonly receipt_id: Uuid;
  readonly permit_id: Uuid;
  readonly kind: DispositionKind;
  readonly virulence: VirulenceClass;
  readonly closure_gen: number;
  readonly defeater_code: string;
  readonly defeater_vocab_sha256: Sha256Hex;
  /** CONSTRAINT substantive: length >= 120. The console renders it verbatim and does not truncate it on screen. */
  readonly rationale: string;
  readonly evidence_sha256: Sha256Hex;
  readonly signature: SignatureBlock;
  /** The req_* flags PROJECTED onto the disposition row by a BEFORE trigger from clearance_legal. They are on the row so a CHECK can read them; they are in this payload so the screen can prove why a field was demanded. */
  readonly requirements: {
    readonly req_compensating: boolean;
    readonly req_second_signer: boolean;
    readonly req_foreign_org: boolean;
    readonly req_predicate: boolean;
    readonly req_reassert: boolean;
    readonly min_signer_rank: number;
    readonly max_ttl_hours?: number | null;
  };
  readonly compensating_clause_uuid?: Uuid | null;
  readonly predicate_id?: Uuid | null;
  readonly reassert_by?: Timestamp | null;
  readonly expires_at?: Timestamp | null;
  /** Evidentiary asymmetry: gist may accuse, only verbatim may acquit. verbatim_floor refuses a mechanism_absent or mitigated disposition whose verbatim anchor count is below the required count. */
  readonly anchors?: {
    readonly verbatim_anchor_count: number;
    readonly required_anchors: number;
  };
  /** NEUTRAL MEASUREMENTS. Recorded, never thresholded here, and never rendered as a characterisation of a named person (I15 / the A-RULE). deliberation_seconds derives from the SERVER clock on exposure_receipt.issued_at (S7). */
  readonly measurements: {
    readonly deliberation_seconds: number;
    readonly evidence_opened: boolean;
    readonly reading_floor_met: boolean;
    readonly prior_override_count: number;
    readonly severity_snapshot: Severity;
  };
  readonly signed_at: Timestamp;
  readonly retracted_by: Uuid | null;
};

/**
 * What a signature actually is (ARCHITECTURE.md §11.4). signer_sub is carried because the
 * record names who signed; D15 forbids it becoming a visual dimension anywhere in the console
 * — never a colour, axis, facet or sort key.
 */

export type SignatureBlock = {
  readonly signer_sub: string;
  readonly signer_rank: number;
  readonly signer_org: string;
  readonly signer_credential_id: Hex;
  readonly countersigner_sub?: string | null;
  readonly countersigner_rank?: number | null;
  readonly countersigner_org?: string | null;
  readonly countersigner_credential_id?: Hex | null;
  /** COSE algorithm identifier, e.g. -7 for ES256, rendered as a string. */
  readonly signature_alg: string;
  /** CONSTRAINT uv_required: false is not a representable row. The difference between 'a token was present' and 'a person authenticated'. */
  readonly user_verified: true;
  readonly sign_count?: number | null;
};

// ──────────────────────────────────────────────────────────────────────────
// envelope.schema.json — MAINLINE console — read response envelope
// ──────────────────────────────────────────────────────────────────────────

/**
 * Every read the console performs returns this shape, over HTTP from the kernel's read API or
 * byte-for-byte out of an evidence bundle frame. The two transports are interchangeable
 * BECAUSE the envelope is the same object; if they differed here they would differ in a code
 * path, and the LIVE/REPLAY badge would be decoration.
 */

export type ReadEnvelope = {
  /** MUST be 1. A reader that does not recognise the version refuses the payload rather than guessing at it. */
  readonly envelope_version: 1;
  /** The resource key from src/data/resources.ts. The transport asserts this equals the key it asked for — a frame that answers a different question than the one asked is a tampered bundle, not a convenience. */
  readonly resource: string;
  /** The $id of the contract that governs `data`. The console looks the schema up by this value and refuses a payload naming a schema it does not hold — an unknown contract is not a forward-compatible contract. */
  readonly schema_id: string;
  /** When the read API produced this payload. Null when the emitter declined to state it; never defaulted to now(). */
  readonly observed_at?: Timestamp | null;
  /** The server's own clock at emission, carried so the honesty chrome can show server-vs-local skew (D16) without the console having to trust a header a proxy may have rewritten. */
  readonly server_date?: Timestamp | null;
  /** True when any part of `data` is hand-authored demonstration material rather than a value a cluster produced. The honesty chrome renders this; a bundle of staged frames says STAGED on every screen it feeds. */
  readonly staged: boolean;
  /** Required and non-null exactly when `staged` is true. Says what was staged and why, in the words of whoever staged it. */
  readonly staged_note?: string | null;
  /** Where the payload came from. Empty is legal and means the emitter named no source, which the console displays as an absence rather than hiding. */
  readonly statement_refs?: readonly StatementRef[];
  readonly provenance: FieldProvenance;
  /** The resource payload. Constrained by the resource contract named in schema_id, never by this file. */
  readonly data: unknown;
};

// ──────────────────────────────────────────────────────────────────────────
// exposure.schema.json — MAINLINE console — exposure receipt
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline.exposure_receipt and mainline.exposure_line, ARCHITECTURE.md §5.5. A disposition
 * composite-FKs (receipt_id, check_id) into exposure_line, so 'it never showed me' and 'I
 * signed without looking' are both violations of a foreign key. The console renders the
 * receipt beside the signature for exactly that reason.
 */

export type ExposureResponse = ReadEnvelope & {
  readonly data: ExposureReceipt;
};

export type ExposureReceipt = {
  readonly receipt_id: Uuid;
  readonly permit_id: Uuid;
  readonly actor_sub: string;
  /** SERVER clock. Deliberation derives from this, never from the browser's (S7). */
  readonly issued_at: Timestamp;
  /** ADVISORY ordering only — a provisional timestamp, and the console labels it as one. */
  readonly issued_hlc?: string | null;
  readonly expires_at: Timestamp;
  /** The ledger checkpoint root at the read timestamp. This is what proves WHAT THE SYSTEM KNEW at signing time. */
  readonly corpus_root: Sha256Hex;
  readonly silence_receipt_id: Uuid;
  readonly policy_version: string;
  readonly total_tokens: number;
  /** The Merkle digest of the exact payloads rendered to that person. It is the anchor the WebAuthn challenge reconstructs from, which is what refutes 'he signed a summary, not the warning' by arithmetic. */
  readonly receipt_digest: Sha256Hex;
  /** receipt_expiry.swept_at. The sweeper MARKS by writing a new row; exposure_receipt itself stays append-only (S28). */
  readonly swept_at?: Timestamp | null;
  readonly lines: readonly ExposureLine[];
};

export type ExposureLine = {
  readonly receipt_id: Uuid;
  readonly check_id: Uuid;
  /** sha256 of the exact text rendered for this check. The console re-derives it from the rendered string in a Worker (D6) and shows agreement or disagreement — it does not assert agreement. */
  readonly payload_digest: Sha256Hex;
  readonly tokens: number;
};

// ──────────────────────────────────────────────────────────────────────────
// gate-run.schema.json — MAINLINE demo — four-beat gate run
// ──────────────────────────────────────────────────────────────────────────

/**
 * Four beats played against the seeded permit inside ONE SERIALIZABLE transaction that is
 * rolled back: read the subject, merge and be refused, forge the projected counter and be
 * refused anyway, sign one disposition and be admitted. The payload carries what the DATABASE
 * said at each beat — SQLSTATE, constraint name, how that name was obtained — and it proves
 * rather than asserts the two properties the demo depends on: that the beats shared one
 * transaction (equal cluster logical timestamps) and that nothing persisted (a fingerprint
 * taken before and after).
 */

export type GateRunResponse = ReadEnvelope & {
  readonly data: GateRun;
};

export type GateRun = {
  /** This contract's own $id, repeated inside the payload so that a gate-run captured into an evidence bundle still names the contract that governs it once it is separated from its envelope. */
  readonly schema_id: "https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json";
  readonly run_id: UuidOrToken;
  readonly generated_at: GateRunTimestamp;
  /** completed = all four beats were attempted. retry = SQLSTATE 40001 aborted the run; the transaction was UNDECIDED, which is not a refusal, and this driver does not re-send on the caller's behalf. */
  readonly outcome: "completed" | "retry";
  /** PROVEN only when every beat matched the expectation it was written against AND the persistence check proves this run persisted nothing (`persistence_check.self_persisted` is false). It used to key on `persistence_check.identical`, which is a statement about the whole database and therefore false whenever any other caller committed a row — see that field. A run that observed something else still returns 200 and still says NOT PROVEN — a truthful red beats a fabricated green. */
  readonly verdict: "PROVEN" | "NOT PROVEN";
  /** One sentence per thing that did not hold. Empty exactly when the verdict is PROVEN. */
  readonly failures: readonly string[];
  /** Always false. The whole transaction is rolled back, including the beat that succeeded. This is the field that makes the demo safe to share with a hundred judges at once, and `persistence_check` is the evidence for it. */
  readonly persisted: false;
  readonly elapsed_ms: number;
  readonly transaction: Transaction;
  readonly subject: Subject;
  /** Exactly four, in order. The count is fixed because the narrative is fixed: refuse, refuse under attack, admit — with the reading that makes the first two legible in front of them. */
  readonly beats: readonly Beat[];
  readonly persistence_check: PersistenceCheck;
};

/**
 * How the four beats were run, with the evidence for the claim rather than the claim alone.
 */

export type Transaction = {
  /** Issued explicitly by the client on every attempt, never inherited from a pool default (spec/errors.md §2.1). On a warm Lambda the session is by definition a reused one. */
  readonly isolation: "SERIALIZABLE";
  readonly disposition: "rolled_back";
  /** cluster_logical_timestamp() read at the first beat. */
  readonly opened_logical_timestamp: string;
  /** The same builtin read after the last beat. Null when the run was aborted by 40001 before it could be read. */
  readonly closed_logical_timestamp: string | null;
  /** The two timestamps are equal. cluster_logical_timestamp() is constant within a CockroachDB transaction and moves between them, so this is a READ-ONLY witness that no beat quietly opened a transaction of its own — not an assertion the driver makes about itself. */
  readonly single_transaction: boolean;
  /** The savepoint fenced around each write beat. A constraint refusal rolls back to its own savepoint and the transaction keeps taking statements. */
  readonly savepoints: readonly string[];
  /** 40001 when the run was abandoned as undecided; null otherwise. Never a refusal code: an undecided transaction has no reason set. */
  readonly retry_sqlstate: "40001" | null;
  /** Which implementation produced a_canon_bytes and a_leaf_hash for the merge call. The procedure takes both from the CLIENT so that a third party can recompute the ledger leaf without this cluster (migration 0117), which only works if the client says which canonicaliser it used. */
  readonly canonicalisation: string;
};

/**
 * The gated subject as it stood when the run opened. Read from the database in one statement,
 * so the counters and the state describe one moment rather than several.
 */

export type Subject = {
  readonly subject_kind: "permit";
  readonly subject_id: GateRunUuid;
  readonly external_ref: string;
  readonly state: "draft" | "checks_materialised" | "dispositioned" | "merged" | "suspended" | "closed" | "abandoned";
  readonly head_seq: number;
  readonly gate_epoch: number;
  /** The PROJECTED counter — the column a trigger wrote. */
  readonly open_blocking: number;
  /** The same quantity re-derived from blocking_check LEFT JOIN disposition by the anti-join the gate itself uses. Carried separately and never reconciled: the whole product is the observation that a gate trusting the first is a gate one UPDATE disarms. */
  readonly open_blocking_derived: number;
  readonly blocking_check_id: GateRunUuid | null;
  readonly exposure_receipt_id: GateRunUuid | null;
  readonly site_code: string;
};

export type Beat = {
  readonly ordinal: number;
  readonly name: "read" | "merge" | "projection_drift_attack" | "admit";
  readonly label: string;
  /** What this beat was WRITTEN against, carried in the response so that a reader can check the driver's arithmetic instead of taking `matched_expectation` on trust. */
  readonly expected: {
    readonly outcome: BeatOutcome;
    readonly sqlstate?: string;
    readonly constraint?: string;
    readonly constraint_source?: "reported" | "parsed";
  };
  readonly outcome: BeatOutcome;
  /** Verbatim from the driver. 00000 for a beat that did not raise. Never composed. */
  readonly sqlstate: string | null;
  /** The exhibit. A constraint or unique-index name for 23514/23503/23505; the fully-qualified name of the raising object for P0001. */
  readonly constraint: string | null;
  /** reported = taken from driver diagnostics. parsed = recovered from the kernel's own `refused by <schema>.<object>` clause, which is a WEAKENED diagnosis and must be rendered as such. Every P0001 lands in the parsed case, measured: on CockroachDB v26.2.5 a PL/pgSQL RAISE carries no constraint_name and no PL/pgSQL context. */
  readonly constraint_source: "reported" | "parsed" | "absent" | null;
  /** The database's own message, verbatim apart from whitespace normalisation and the length cap. The driver never writes this sentence. */
  readonly message: string | null;
  readonly matched_expectation: boolean;
  readonly elapsed_ms: number;
  /** The parameterised SQL this beat sent, so a reader can run it themselves. */
  readonly statement: string | null;
  /** The spec/wire refusal payload, unchanged. Its minimal unsatisfiable subset and nearest admissible alternative come from trappoint.explain_refusal — the same engine that produced the refusal — so the explanation cannot disagree with it. */
  readonly refusal: RefusalPayload | null;
  readonly observed: Observed;
  /** Set only when something needs saying: a beat that was skipped, or a beat whose outcome was not the one it was written against. */
  readonly note: string | null;
};

/**
 * read = a SELECT, nothing attempted. refused = the gate said no and named what said it.
 * admitted = the transition succeeded (and was then rolled back). retry = 40001. skipped = a
 * precondition the API refuses to fabricate was absent. error = a SQLSTATE outside the
 * modelled taxonomy, reported rather than smoothed over.
 */

export type BeatOutcome = "read" | "refused" | "admitted" | "retry" | "skipped" | "error";

/**
 * What this beat saw. Every member is optional because the beats observe different things, and
 * every member that is present is a value the database produced.
 */

export type Observed = {
  readonly state?: string;
  readonly gate_epoch?: number;
  readonly head_seq?: number;
  readonly open_blocking_projected?: number;
  readonly open_blocking_derived?: number;
  readonly blocking_check_id?: GateRunUuid | null;
  readonly counters_agree?: boolean;
  readonly counter_forced_to?: number | null;
  readonly attack?: string;
  readonly disposition_id?: GateRunUuid;
  readonly disposition_kind?: "applied" | "mitigated" | "mechanism_absent" | "escalated" | "accept_residual" | "emergency_override";
  readonly open_blocking_after_signature?: number | null;
  readonly merge_record?: {
    /** SHA-256 over the sorted (check_id, disposition_id) set, computed by the SERVER from the base tables — so a completion record cannot claim a clearance set the database does not hold. */
    readonly clearance_digest: string | null;
    readonly merged_commit: string;
    readonly gate_epoch: number;
    readonly merged_at: GateRunTimestamp;
    readonly permit_state?: string;
    readonly permit_open_blocking?: number;
    readonly permit_head_seq?: number;
  } | null;
};

/**
 * The evidence for `persisted: false`. Row counts over every table the four beats can write,
 * taken before the transaction opened and after it was rolled back, plus mainline.permit's own
 * columns — because the attack beat mutates a column without changing a count. That reading is
 * `identical` and it is a statement about the DATABASE. `self_persisted` is the statement
 * about THIS RUN, and it is what the verdict keys on: a whole-table count cannot distinguish
 * 'I persisted something' from 'somebody else did', and this endpoint used to report the
 * difference as its own failure. Amended 2026-08-14 under docs/leads/cloud-hardening-final.md
 * ruling R2, which permits the contract to move only by argument on the record; the argument
 * is docs/deploy/gate-run-contract.md §3 and the reproduction that identified the writer is
 * docs/diagnosis/gate-run-fingerprint.md. NOTHING WAS NARROWED: the ten counts are unchanged,
 * no table left the list, and the run-scoped evidence was ADDED beside them.
 */

export type PersistenceCheck = {
  readonly before: Fingerprint;
  readonly after: Fingerprint;
  /** The ten unscoped counts and the permit row are byte-identical before and after. False means SOMETHING in those tables moved — not necessarily this run; read `self_persisted` and `concurrent_writes` for which. */
  readonly identical: boolean;
  /** Did anything THIS RUN wrote survive the rollback? False is the claim `persisted: false` makes, and it is proven rather than asserted: the disposition beat 4 minted is a uuid4 no other writer holds and it is absent; this subject's own merge_record / permit_event / disposition counts are unchanged; and its permit row is unchanged, which is where beat 3's out-of-band UPDATE would show. True is a defect in the gate and makes the verdict NOT PROVEN. */
  readonly self_persisted: boolean;
  readonly self_evidence: SelfEvidence;
  /** Null when `identical` is true. Otherwise the tables whose unscoped count moved while this run was open, each as [before, after]. These are ANOTHER caller's rows — a fact about the database this demo shares, reported rather than blamed on the run, and never a reason to narrow the counts above. */
  readonly concurrent_writes: StringMap<readonly number[]> | null;
  readonly tables: readonly string[];
  readonly note: string;
};

/**
 * The run-scoped readings `self_persisted` is computed from, in the payload so that a reader
 * can recompute the verdict rather than take it.
 */

export type SelfEvidence = {
  /** The uuid4 beat 4 minted for its disposition. Null when beat 4 was skipped, in which case the run wrote nothing the database accepted at all. */
  readonly minted_disposition_id: string | null;
  /** How many rows carry that identifier once the transaction is rolled back. Zero is the proof; anything else means the transaction committed. */
  readonly minted_disposition_rows_after_rollback: number;
  readonly subject_row_counts_before: SubjectRowCounts;
  readonly subject_row_counts_after: SubjectRowCounts;
  readonly permit_row_identical: boolean;
};

/**
 * The three tables a successful beat 4 writes a surviving row into, counted for THIS permit
 * only. Added beside the ten unscoped counts, never in place of them.
 */

export type SubjectRowCounts = StringMap<number>;

export type Fingerprint = {
  /** Every table the four beats can write, counted WHOLE. Unscoped on purpose and it stays unscoped: the attack beat mutates a column without changing a count, and a check that only looked where this run was expected to write could not see a write it was not expecting. */
  readonly row_counts: StringMap<number>;
  readonly subject_row_counts: SubjectRowCounts;
  readonly permit_row: {
    readonly state: string;
    readonly head_seq: number;
    readonly gate_epoch: number;
    readonly open_blocking: number;
    readonly unmet_floor_count: number;
    readonly countersigned_count: number;
    readonly merged_commit: string | null;
  } | null;
};

export type GateRunUuid = string;

export type UuidOrToken = string;

export type GateRunTimestamp = string;

// ──────────────────────────────────────────────────────────────────────────
// invoke.schema.json — MAINLINE console — kernel procedure result
// ──────────────────────────────────────────────────────────────────────────

/**
 * ARCHITECTURE.md §8.3: the kernel's API surface is six endpoints, each a thin authenticator
 * in front of exactly one server-side procedure. The console POSTs to three of them
 * (materialise_checks, sign_disposition, merge_permit) plus suspend_permit, and reads the
 * result through this contract. A REFUSED outcome carries the spec/wire refusal payload
 * UNCHANGED — D18: refusals are rendered from the payload only, never from a message the
 * console composes.
 */

export type InvokeResponse = ReadEnvelope & {
  readonly data: InvokeResult;
};

export type InvokeResult = {
  /** The server-side procedure the endpoint fronts. There is no kernel business logic that is not SQL, and this names the SQL. */
  readonly procedure: "trappoint.materialise_checks" | "trappoint.sign_disposition" | "trappoint.merge_permit" | "trappoint.suspend_permit";
  /** The status the kernel returned, carried in the payload as well as on the wire so a replayed frame and a live response are the same object. */
  readonly http_status: number;
  /** committed = the transition happened. refused = the database refused it, and `refusal` says which constraint did. retry = SQLSTATE 40001, an UNDECIDED transaction, which is not a refusal and has no reason set. */
  readonly outcome: "committed" | "refused" | "retry";
  readonly subject_kind: SubjectKind;
  readonly subject_id: Uuid;
  /** The subject's epoch at the moment of the attempt. Without it the attempt cannot be replayed. */
  readonly gate_epoch: GateEpoch;
  readonly committed?: {
    readonly merged_commit: CommitId;
    readonly merged_at: Timestamp;
    readonly clearance_digest?: Sha256Hex | null;
    readonly checkpoint_tree_size?: number | null;
    readonly ledger_seq?: number | null;
  } | null;
  readonly refusal: RefusalPayload | null;
  /** Path inside the evidence bundle to the verbatim SQL round trip (sql/*.txt) that produced this outcome, including the SQLSTATE and the constraint name as the driver reported them. Null for a live response that carried none. */
  readonly sql_round_trip?: string | null;
};

// ──────────────────────────────────────────────────────────────────────────
// ledger.schema.json — MAINLINE console — ledger leaves, nodes, checkpoints and cosignatures
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline.ledger_leaf, ledger_node, ledger_checkpoint and cosignature (ARCHITECTURE.md §5.6).
 * This contract carries BYTES, not verdicts: every hash, note and proof path below is material
 * the in-browser verifier (D6, worker verifier-custody-room) recomputes. Nothing in this
 * payload asserts that a proof held, and the console must not render one as though it did.
 */

export type LedgerResponse = ReadEnvelope & {
  readonly data: {
    readonly site_code: string;
    /** Ascending tree_size, no duplicates. */
    readonly checkpoints: readonly LedgerCheckpoint[];
    /** seq must be dense from 0. A gap MEANS tampering — there is no sequence generator in this deployment that could have produced one (CREATE SEQUENCE / nextval / SERIAL / unique_rowid are banned by a CI lint, which is load-bearing because the cluster would otherwise accept them). */
    readonly leaves: readonly LedgerLeaf[];
    /** Persisted RFC 6962 interior hashes, tile-addressable. Optional: the verifier can recompute them from the leaves, and their absence downgrades nothing. */
    readonly nodes?: readonly LedgerNode[];
    readonly inclusion_proofs: readonly InclusionProof[];
    readonly consistency_proofs?: readonly ConsistencyProof[];
    readonly cosignatures?: readonly LedgerCosignature[];
    /** Going dark stays possible and self-reports. An unreachable witness produces a debt row, never a blocked merge. */
    readonly unwitnessed_debt?: readonly ({
      readonly debt_id: Uuid;
      readonly site_code: string;
      readonly permit_id: Uuid;
      readonly incurred_at: Timestamp;
      readonly discharged_tree_size: number | null;
    })[];
  };
};

export type LedgerCheckpoint = {
  readonly site_code: string;
  readonly tree_size: number;
  readonly root_hex: Sha256Hex;
  /** The C2SP tlog-checkpoint note text VERBATIM, newlines and signature lines included — these are the signed bytes. tree_size and root_hex are redundant with it ON PURPOSE: a verifier parses the note and compares, and a disagreement is a finding. */
  readonly note: string;
  /** C2SP vkey. A bundle that carries its own trust anchor proves nothing, so a checkpoint verified against a key from this field alone is reported as PASS(self-asserted-key) — a distinct verdict. */
  readonly log_key?: string | null;
  readonly log_sig_b64?: string | null;
  /** drand round + signature. LOWER time bound. */
  readonly beacon?: JsonObject | null;
  /** RFC 3161 TimeStampToken over SHA-256(note). UPPER time bound. Null downgrades the timestamp check to SKIP(no-tsa-token). */
  readonly tsa_token_b64?: string | null;
  /** Object Lock COMPLIANCE version id. Offline this is a claim by us about our own archive, and the console labels it as one. */
  readonly s3_version?: string | null;
  /** Hash of the canonicaliser that produced the leaves. Nothing here is 'obviously SHA-256 because everything is'. */
  readonly canon_src_sha256: Sha256Hex;
  /** Projected: quorum plus trust-domain diversity satisfied. It is the database's word, not the console's arithmetic. */
  readonly admissible: boolean;
  readonly observed_at?: Timestamp | null;
};

export type LedgerLeaf = {
  readonly seq: number;
  readonly entry_id: Uuid;
  readonly entry_kind: string;
  readonly subject_id: Uuid;
  readonly payload_ver: number;
  /** RFC 8785 JCS bytes, base64. THE HASHED BYTES. A verifier that hashes `payload` instead has tested its own JSON library, not this ledger. */
  readonly canon_bytes_b64: string;
  /** A convenience rendering for humans. Never hashed. A disagreement between this and canon_bytes_b64 is how a substitution attack surfaces as a legible discrepancy rather than as nothing at all. */
  readonly payload?: unknown;
  readonly leaf_hash_hex: Sha256Hex;
  readonly link_hash_hex: Sha256Hex;
  /** Present on every leaf including seq 0, where it is 64 zeroes. An explicit genesis beats a special case, and UNIQUE (site_code, prev_link_hash) depends on it existing. */
  readonly prev_link_hash_hex: Sha256Hex;
  /** No leaf in an evidentiary bundle may be true. */
  readonly is_sandbox: boolean;
  readonly actor: string;
  readonly actor_kind: "human" | "agent" | "service" | "external";
  readonly recorded_at: Timestamp;
  readonly batch_id?: Uuid | null;
};

export type LedgerNode = {
  readonly level: number;
  readonly idx: number;
  readonly hash_hex: Sha256Hex;
};

/**
 * RFC 6962 §2.1.1. This is the proof that answers 'this was never in the log' — a proposition
 * nobody can rebut with a chain, only with a tree.
 */

export type InclusionProof = {
  readonly seq: number;
  readonly tree_size: number;
  readonly path_hex: readonly Sha256Hex[];
};

/**
 * RFC 6962 §2.1.2. Required for every consecutive checkpoint pair. This is the check that
 * catches 'delete leaf k, renumber, recompute every link_hash': the link chain recomputes
 * perfectly after that attack; the consistency proof does not.
 */

export type ConsistencyProof = {
  readonly from_size: number;
  readonly to_size: number;
  readonly path_hex: readonly Sha256Hex[];
};

export type LedgerCosignature = {
  readonly tree_size: number;
  readonly witness_id: string;
  readonly trust_domain: "regulator" | "insurer" | "union_hsr" | "external_auditor" | "operator";
  /** A claim about legal interest, not a cryptographic property. With q=1 over our own infrastructure the verdict is PASS(not-adverse), and split-view resistance MUST NOT be claimed by any screen rendered from this field. */
  readonly adverse: boolean;
  readonly sig_b64: string;
  readonly witness_key?: string | null;
  readonly received_at: Timestamp;
};

// ──────────────────────────────────────────────────────────────────────────
// permit.schema.json — MAINLINE console — permit
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline.permit, ARCHITECTURE.md §5.5. Every counter below is a PROJECTION: a trigger wrote
 * it onto the permit row from an authoritative table, and the six named CHECK constraints read
 * those columns and nothing else. The console reads them verbatim and computes none of them
 * (D5).
 */

export type PermitResponse = ReadEnvelope & {
  readonly data: Permit;
};

/**
 * One named refusal. The name IS the exhibit — 'the merge was refused by
 * boundary_certified_when_issued' is a materially better sentence than 'a counter was
 * non-zero'. `predicate` is the CHECK text as the catalog reports it; the console never
 * paraphrases it.
 */

export type GateConstraint = {
  readonly constraint: string;
  /** Verbatim CHECK expression. Null when the read API did not capture it; the console then shows the constraint name alone rather than a reconstruction. */
  readonly predicate?: string | null;
  /** The projected columns this constraint reads. Empty for a constraint over non-counter columns (merge_evidence). */
  readonly counters: readonly ({
    readonly column: string;
    readonly value: Counter;
  })[];
  /** True exactly when the refusal payload attached to this read names this constraint. It is a string comparison against the database's own word, never an evaluation of the predicate. */
  readonly blamed_by_refusal: boolean;
};

export type Permit = {
  readonly permit_id: Uuid;
  readonly site_id: Uuid;
  readonly site_code?: string | null;
  /** The customer's own work-order identifier, e.g. WO-88213. */
  readonly external_ref: string;
  /** The protected branch this permit is a ref of. */
  readonly ref_name: string;
  readonly parent_permit_id?: Uuid | null;
  readonly state: SubjectState;
  readonly head_seq: number;
  readonly gate_epoch: GateEpoch;
  readonly merged_commit?: CommitId | null;
  readonly under_hold: boolean;
  readonly slice_digest?: Sha256Hex | null;
  readonly opened_at: Timestamp;
  readonly horizon_at: Timestamp;
  /** The seven projected scalars the gate reads. P2: each is written by its own trigger from an authoritative table and RAISEs when that source is missing; none is ever supplied by a writer. */
  readonly counters: {
    readonly open_blocking: Counter;
    readonly open_residue: Counter;
    readonly open_conflicts: Counter;
    readonly open_warrants: Counter;
    readonly unmodelled_asset_count: Counter;
    readonly unmet_floor_count: Counter;
    readonly countersigned_count: Counter;
  };
  /** The named refusals declared on mainline.permit, in declaration order. Six gate constraints plus merge_evidence. */
  readonly constraints: readonly GateConstraint[];
  /** S11: an asset with no modelled energy edges is UNKNOWN, not SAFE — and unknown blocks. unmodelled_asset_count = tags_unmodelled + under_declared. */
  readonly boundary_certificate?: {
    readonly asset_graph_version: string;
    readonly tags_declared: number;
    readonly tags_resolved: number;
    readonly tags_unmodelled: number;
    readonly under_declared: number;
    readonly computed_at: Timestamp;
  } | null;
  /** Present only once the subject has merged. Its (subject_id, gate_epoch) composite FK is the epoch pin: while this row exists the database refuses any UPDATE that moves gate_epoch, so a new obligation cannot be attached to an issued permit. */
  readonly merge_record?: {
    readonly gate_epoch: GateEpoch;
    readonly merged_at: Timestamp;
    readonly merged_by: string;
    readonly merged_commit: CommitId;
    readonly clearance_digest: Sha256Hex;
    readonly checkpoint_tree_size?: number | null;
  } | null;
};

// ──────────────────────────────────────────────────────────────────────────
// propagation.schema.json — MAINLINE console — fleet propagation and merge conflicts
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline.lesson, mainline.propagation and mainline.merge_conflict (ARCHITECTURE.md §5.9).
 * Sites are downstream distributions, not replicas: a mandated RESPONSE beats mandated
 * conformity, because a setpoint that is right at one plant can be an unrevealed hazard at
 * another. only_tightenings_travel is a CHECK, not a policy — weakenings are site-local
 * trade-offs and must be re-earned locally.
 */

export type PropagationResponse = ReadEnvelope & {
  readonly data: {
    readonly lesson: Lesson;
    readonly propagations: readonly Propagation[];
    readonly conflicts: readonly MergeConflict[];
  };
};

export type Lesson = {
  readonly lesson_id: Uuid;
  readonly origin_site: Uuid;
  readonly origin_commit: CommitId;
  readonly anchor_event: Uuid;
  readonly max_severity: Severity;
  /** CHECK only_tightenings_travel restricts this to introduce, strengthen or restate. A weaken lesson is not a representable row. */
  readonly control_delta: "introduce" | "strengthen" | "restate";
  /** sha256 over the NORMALISED delta set — a git patch-id analogue, so the same change arriving by two routes is one lesson. */
  readonly patch_digest: Sha256Hex;
  readonly merge_base: CommitId;
  readonly title?: string | null;
};

export type Propagation = {
  readonly lesson_id: Uuid;
  readonly site_id: Uuid;
  readonly site_code?: string | null;
  readonly state: PropState;
  readonly score: number;
  readonly model_version: string;
  readonly proposed_at: Timestamp;
  /** Severity-scaled SLA clock. A site that has not answered is displayed as not having answered, never as compliant-by-default. */
  readonly due_by: Timestamp;
  readonly adopted_commit?: CommitId | null;
  /** Convergent evolution: the site already had the control. That is evidence FOR the site, and the console renders it as such. */
  readonly already_present_clause?: Uuid | null;
  readonly open_conflicts: Counter;
  readonly declination_kind?: ("mitigated" | "waiver" | "mechanism_absent") | null;
  readonly declination_predicate_id?: Uuid | null;
  readonly declination_expires_at?: Timestamp | null;
};

export type MergeConflict = {
  readonly conflict_id: Uuid;
  readonly lesson_id: Uuid;
  readonly site_id: Uuid;
  readonly clause_uuid: Uuid;
  readonly base_digest: Sha256Hex;
  readonly ours_digest: Sha256Hex;
  readonly theirs_digest: Sha256Hex;
  readonly resolved_commit?: CommitId | null;
  readonly resolved_by?: string | null;
  /** rerere-with-recall back-pointer. A recorded resolution is PROPOSED, never auto-applied — auto-applying a safety-text resolution is precisely the rubber-stamp accelerant this design refuses to build. */
  readonly resolution_source?: Uuid | null;
  readonly opened_at: Timestamp;
};

// ──────────────────────────────────────────────────────────────────────────
// recall-run.schema.json — MAINLINE console — recall run
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline_meas.recall_run (ARCHITECTURE.md §5.7). Two CHECK constraints on this table are
 * product claims and the console renders both as arithmetic the reader can add up:
 * candidates_conserved (n_candidates = blocking + advisory + silenced + deduped) and
 * bonded_fatalities_all_blocking (n_bonded_sev5_blocking = n_bonded_sev5 — 'a fatality in your
 * fonds is always recalled', as a positive invariant rather than a score hack).
 */

export type RecallRunResponse = ReadEnvelope & {
  readonly data: RecallRun;
};

export type RecallRun = {
  readonly run_id: Uuid;
  readonly permit_id: Uuid;
  readonly site_id: Uuid;
  readonly corpus_commit: CommitId;
  readonly policy_version: string;
  /** Hash of the EXPLAIN output ACTUALLY OBSERVED, not of the plan we hoped for. Platform ground truth F1: every ANN arm pins its index explicitly, because at demo-corpus scale an unhinted prefix-constrained query does not traverse the index at all. */
  readonly index_plan_digest: Sha256Hex;
  readonly index_generation: string;
  readonly counts: {
    readonly n_candidates: number;
    readonly n_blocking: number;
    readonly n_advisory: number;
    readonly n_silenced: number;
    readonly n_deduped: number;
    readonly n_bonded_sev5: number;
    readonly n_bonded_sev5_blocking: number;
  };
  /** Per-channel outcome. A degraded arm is displayed as degraded; the fusion never hides which channel went missing. */
  readonly arms?: readonly ({
    readonly arm: string;
    readonly degraded: boolean;
    readonly n_returned?: number | null;
    readonly index_hinted?: boolean | null;
    readonly detail?: string | null;
  })[];
  readonly arms_degraded: boolean;
  readonly started_at: Timestamp;
  readonly latency_ms?: number | null;
};

// ──────────────────────────────────────────────────────────────────────────
// refusal.schema.json — TRAPPOINT refusal payload
// ──────────────────────────────────────────────────────────────────────────

/**
 * The irreducible reason set and nearest admissible alternative emitted for every REFUSE-class
 * gate outcome. Invariant I14.
 */

export type RefusalPayload = {
  /** TRAPPOINT specification version this payload claims to satisfy. */
  readonly spec_version: string;
  readonly refusal_id: RefusalUuid;
  /** RFC 3339 UTC instant at which the refusal was observed by the emitter. */
  readonly observed_at: string;
  /** Conformance profile of the emitting deployment. */
  readonly profile?: string;
  /** Only REFUSE-class outcomes are payloads. RETRY and DENY outcomes are not refusals. */
  readonly class: "gate";
  /** The refusal code. 40001 is excluded: an undecided transaction has no reason set. */
  readonly sqlstate: "23514" | "23503" | "23505" | "P0001";
  /** The exhibit name. For 23514/23503/23505 the constraint or unique-index name reported by the driver; for P0001 the fully-qualified name of the raising trigger function, UDF or procedure. */
  readonly constraint: string;
  /** reported = taken from driver diagnostics; parsed = recovered from the message text, which is a WEAKENED diagnosis and must be rendered as such. */
  readonly constraint_source?: "reported" | "parsed";
  /** The database message verbatim, including its MAINLINE: / TRAPPOINT: prefix. */
  readonly message: string;
  /** The gated subject kind as declared in the vertical binding. */
  readonly subject_kind: string;
  readonly subject_id: RefusalUuid;
  /** The subject's gate_epoch at the moment of refusal. Without it the refusal cannot be replayed. */
  readonly gate_epoch: number;
  /** How the minimal unsatisfiable subset was obtained. */
  readonly diagnosis: "declarative" | "quickxplain" | "none";
  /** Oracle calls consumed by the QuickXplain probe loop. Zero for a declarative diagnosis. */
  readonly probe_calls: number;
  /** The minimal unsatisfiable subset: remove any one element and the transition would have been admissible. */
  readonly mus: readonly MusAtom[];
  /** The nearest admissible alternative, or null with naa_reason set. */
  readonly naa: Naa | null;
  /** Required and non-null exactly when naa is null. */
  readonly naa_reason?: ("probe_budget_exhausted" | "no_legal_verdict_exists" | "requires_human_authority" | "not_computable") | null;
  /** Pointers a third party can follow without the emitter's cooperation. */
  readonly evidence?: readonly EvidenceItem[];
  /** Vertical-specific extension object. The substrate never reads it. It MUST NOT carry any score, rating, threshold or characterisation of a named human (invariant I15). */
  readonly ext?: JsonObject;
};

export type RefusalUuid = string;

/**
 * Prefixed digest, e.g. sha256:<hex>. Presence is not verification.
 */

export type RefusalDigest = string;

export type Identifier = string;

/**
 * One fact of the irreducible reason set, tagged by kind.
 */

export type MusAtom = {
  readonly kind: "obligation";
  readonly obligation_id: RefusalUuid;
  readonly origin?: Identifier;
  readonly clause_id?: RefusalUuid;
  readonly event_id?: RefusalUuid;
  readonly severity?: number;
  readonly virulence?: Identifier;
  readonly detail?: string;
} | {
  readonly kind: "clause";
  readonly clause_id: RefusalUuid;
  readonly commit_id?: string;
  readonly relation?: Identifier;
  readonly detail?: string;
} | {
  readonly kind: "event";
  readonly event_id: RefusalUuid;
  readonly severity?: number;
  readonly detail?: string;
} | {
  readonly kind: "authority_gap";
  readonly relation: Identifier;
  readonly key: StringMap<string | number | null>;
  readonly detail?: string;
} | {
  readonly kind: "capability_gap";
  readonly capability: Identifier;
  readonly required_value?: string | number | boolean | null;
  readonly observed_value?: string | number | boolean | null;
  readonly detail?: string;
};

/**
 * Minimum-cardinality change to the attempted history that restores admissibility.
 */

export type Naa = {
  readonly kind: "dispose_obligations";
  readonly obligation_ids: readonly RefusalUuid[];
  readonly cardinality: number;
  readonly legal_kinds?: readonly Identifier[];
  readonly description: string;
} | {
  readonly kind: "substitute_kind";
  readonly legal_kinds: readonly Identifier[];
  readonly cardinality?: number;
  readonly description: string;
} | {
  readonly kind: "supply_evidence";
  readonly required: readonly Identifier[];
  readonly cardinality?: number;
  readonly description: string;
} | {
  readonly kind: "materialise_authority";
  readonly relation: Identifier;
  readonly key: StringMap<string | number | null>;
  readonly cardinality?: number;
  readonly description: string;
} | {
  readonly kind: "fork_subject";
  readonly parent_subject_id: RefusalUuid;
  readonly cardinality?: number;
  readonly description: string;
};

export type EvidenceItem = {
  readonly kind: Identifier;
  readonly ref: string;
  readonly digest?: RefusalDigest;
};

// ──────────────────────────────────────────────────────────────────────────
// silence.schema.json — MAINLINE console — silence ledger and Proof of Exhausted Recall
// ──────────────────────────────────────────────────────────────────────────

/**
 * mainline_meas.silence_ledger and mainline_meas.silence_receipt (ARCHITECTURE.md §5.7). The
 * silence ledger answers the plaintiff's actual question — 'your system knew about event X and
 * did not show it' — with arithmetic instead of an adverse inference. Its dark side is that it
 * is a complete list of every warning we chose not to give, and the console renders it in full
 * rather than as a count.
 */

export type SilenceResponse = ReadEnvelope & {
  readonly data: {
    readonly subject_kind: SubjectKind;
    readonly subject_id: Uuid;
    readonly entries: readonly SilenceEntry[];
    /** The PER receipt for the recall run that produced these silences, or null when the run issued none. */
    readonly receipt: SilenceReceipt | null;
  };
};

export type SilenceEntry = {
  readonly silence_id: Uuid;
  readonly site_id: Uuid;
  readonly source: "recall" | "fleet_appraisal" | "severity_downgrade" | "closure_truncation" | "dedup" | "delta_neutral" | "blame_lapse" | "patrol_suppression" | "ring_exclusion" | "boundary_unmodelled";
  readonly reason: "below_tau" | "model_refusal" | "dedup_sibling" | "cap_exceeded" | "truncated" | "abstained" | "bounded_negative" | "unreachable";
  readonly subject_kind: string;
  readonly subject_id: Uuid;
  readonly event_id?: Uuid | null;
  readonly severity: Severity;
  readonly score?: number | null;
  readonly threshold?: number | null;
  /** Components, model version and tau. This is the difference between 'we did not show it' and 'it scored 0.31 against a threshold of 0.45, calibrated on a temporally-blocked gold set; here is the calibration commit and its author'. */
  readonly arithmetic: JsonObject;
  readonly policy_version?: string | null;
  readonly at: Timestamp;
};

/**
 * Proof of Exhausted Recall, honestly bounded. Because the candidate leaves are SCORE-SORTED,
 * disclosing candidate_root, theta, s, n and the boundary pair with inclusion paths
 * establishes that every leaf beyond position s scored below theta — no item can be
 * hand-excluded without breaking sortedness — while revealing no suppressed content.
 */

export type SilenceReceipt = {
  readonly silence_receipt_id: Uuid;
  readonly run_id: Uuid;
  readonly permit_id: Uuid;
  readonly corpus_root: Sha256Hex;
  /** Merkle root over the score-sorted candidate multiset. */
  readonly candidate_root: Sha256Hex;
  readonly theta: number;
  readonly s: number;
  readonly n: number;
  /** Inclusion paths for leaves s and s+1. Recomputed in-browser by the verifier; this payload carries only the paths. */
  readonly boundary_proof: {
    readonly leaf_s: BoundaryLeaf;
    readonly leaf_s_plus_1: BoundaryLeaf | null;
  };
  readonly policy_version: string;
  readonly issued_at: Timestamp;
  /** The honest limit, carried as data so no exhibit can be generated without it. ANN is approximate: PER proves exhaustion of the RETRIEVAL THAT RAN, not of the corpus. */
  readonly bound: {
    readonly index_generation: string;
    readonly index_plan_digest: Sha256Hex;
    /** The bounding sentence, verbatim, to be reproduced on every exhibit rendered from this receipt. */
    readonly statement: string;
  };
};

export type BoundaryLeaf = {
  readonly index: number;
  readonly leaf_hash_hex: Sha256Hex;
  readonly score: number;
  readonly path_hex: readonly Sha256Hex[];
};
