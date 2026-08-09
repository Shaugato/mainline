// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `buildClauseDiff` — one payload in, one model out, with no clock and no randomness.
 *
 * Two things make this more than a formatter.
 *
 * ── 1. IT REFUSES TO DIFF THE WRONG TWO ROWS ─────────────────────────────────────
 *
 * `clause_version.parent_version` names the commit this version edits. If the payload
 * supplies a DIFFERENT ancestor, the diff between them is a picture of an edit that never
 * happened — and it is indistinguishable, on screen, from a real one. So the model
 * refuses: no text, no anchors, no CAT, no scalars, and a discrepancy naming both
 * commits. The verdict is still rendered, because the verdict is the database's and this
 * console does not get to suppress it.
 *
 * That is the same move the product makes at the gate: a precondition checked BEFORE the
 * thing is shown, rather than a caveat printed underneath it.
 *
 * ── 2. EVERY FINDING CITES AN AUTHORITY ──────────────────────────────────────────
 *
 * A finding whose `authority` slot is empty is an opinion. Each one below names a file, a
 * section, or a database object that makes the observation a discrepancy rather than a
 * preference — most sharply `witness_guard_expectation`, which fires when a lattice
 * `weaken` arrives with no witness rows. `docs/leads/algorithms.md` D8 says
 * `fn_delta_witness_guard` REFUSES that insert with P0001, so a payload carrying one is
 * telling us something about itself. The console states the contradiction and names the
 * guard. It does NOT decide whether the guard is missing, the payload is stale, or the
 * bytes were fabricated — deciding that from a rendering layer would be exactly the
 * composed claim D5 forbids.
 */

import type {
  ClauseDiffInput,
  ClauseDiffModel,
  ClauseVersion,
  Comparability,
  Finding,
} from '../model';
import { diffAnchors, diffCat, diffScalars } from './structure';
import { diffCanonText } from './text-diff';
import { bindWitnesses, findUnwitnessed, type Observations } from './witness';

// ── Authorities ────────────────────────────────────────────────────────────

const A_CLAUSE_VERSION = 'ARCHITECTURE.md §5.3 · mainline.clause_version';
const A_CONTRACT = 'contracts/clause.schema.json · $defs.clause_version';
const A_DELTA_CONTRACT = 'contracts/clause.schema.json · $defs.delta_verdict';
const A_WITNESS_GUARD =
  'docs/leads/algorithms.md D8 · mainline.fn_delta_witness_guard (P0001) · MI14';
const A_BLOODLINE = 'ARCHITECTURE.md §5.3 (M2) · blood_root / blood_size, an append-only MMR';

// ── Comparability ──────────────────────────────────────────────────────────

/**
 * Whether these two rows may be diffed at all.
 *
 * The check is on `commit_id`, not on `gen` and not on `clause_uuid`: the commit id is the
 * identity of a version, `gen` is denormalised for bisect ordering, and `ordinal` is
 * presentation only and never identity (ARCHITECTURE.md §5.3).
 */
export function comparabilityOf(
  version: ClauseVersion,
  parent: ClauseVersion | null,
): Comparability {
  const named = version.parent_version ?? null;

  if (parent === null) {
    return named === null ? { kind: 'origin_version' } : { kind: 'parent_unresolved', named };
  }
  if (named === null || named !== parent.commit_id) {
    return { kind: 'parent_mismatch', named, supplied: parent.commit_id };
  }
  return { kind: 'comparable', parentCommit: parent.commit_id };
}

// ── The build ──────────────────────────────────────────────────────────────

export interface BuildOptions {
  /** Forwarded to the text engine. Present so the degraded path is reachable in a test. */
  readonly maxDiffCells?: number;
}

export function buildClauseDiff(
  input: ClauseDiffInput,
  options: BuildOptions = {},
): ClauseDiffModel {
  const { version, parent, delta } = input;
  const comparability = comparabilityOf(version, parent);
  const comparable = comparability.kind === 'comparable' && parent !== null;

  const text = comparable
    ? diffCanonText(
        parent.canon_text,
        version.canon_text,
        options.maxDiffCells === undefined ? {} : { maxCells: options.maxDiffCells },
      )
    : null;
  const anchors = comparable ? diffAnchors(parent.anchor_set, version.anchor_set) : null;
  const cat = comparable ? diffCat(parent, version) : null;
  const scalars = comparable ? diffScalars(parent, version) : [];

  const observations: Observations = { text, anchors, cat, scalars, comparable };
  const witnesses = bindWitnesses(delta.witnesses, delta.minimal, observations);
  const unwitnessed = findUnwitnessed(witnesses, observations);

  const findings = collectFindings(input, comparability, comparable ? parent : null, {
    text,
    witnesses,
  });

  return {
    clauseUuid: input.clauseUuid,
    versionCommit: version.commit_id,
    parentCommit: comparability.kind === 'comparable' ? comparability.parentCommit : null,
    comparability,
    verdict: {
      delta: delta.delta,
      basis: delta.basis,
      model: version.delta_model ?? null,
      promptVersion: version.delta_prompt_version ?? null,
      column: version.control_delta,
      columnBasis: version.delta_basis,
    },
    canonText: {
      // The ancestor's text is carried only when it is the ancestor this version names.
      // Showing the wrong row's prose beside the right row's verdict is the same defect
      // as diffing them, one hop earlier.
      parent: comparable ? parent.canon_text : null,
      version: version.canon_text,
    },
    text,
    anchors,
    cat,
    scalars,
    witnesses,
    unwitnessed,
    findings,
    severity: {
      versionSevMax: version.sev_max,
      parentSevMax: comparable ? parent.sev_max : null,
      versionBloodSize: version.blood_size ?? null,
      parentBloodSize: comparable ? (parent.blood_size ?? null) : null,
    },
  };
}

// ── Findings ───────────────────────────────────────────────────────────────

function collectFindings(
  input: ClauseDiffInput,
  comparability: Comparability,
  parent: ClauseVersion | null,
  observed: {
    readonly text: ClauseDiffModel['text'];
    readonly witnesses: ClauseDiffModel['witnesses'];
  },
): readonly Finding[] {
  const { version, delta } = input;
  const out: Finding[] = [];

  // ── Comparability ────────────────────────────────────────────────────────
  if (comparability.kind === 'parent_mismatch') {
    out.push({
      code: 'parent_mismatch',
      level: 'discrepancy',
      title: 'This payload’s ancestor is not the ancestor this version names',
      detail:
        `clause_version.parent_version names commit ${comparability.named ?? '(none)'}, but the ` +
        `payload supplied commit ${comparability.supplied} as the parent. No diff is shown: a ` +
        'comparison between these two rows would depict an edit that never happened, and it ' +
        'would look exactly like one that did.',
      authority: `${A_CONTRACT} · ${A_CLAUSE_VERSION}`,
    });
  }
  if (comparability.kind === 'parent_unresolved') {
    out.push({
      code: 'parent_unresolved',
      level: 'observation',
      title: 'The ancestor version was not carried in this payload',
      detail:
        `clause_version.parent_version names commit ${comparability.named}, and the read API ` +
        'resolved no `parent` member for it. The verdict and its witnesses are shown; nothing ' +
        'on this screen has been compared against anything.',
      authority: `${A_CONTRACT} — \`parent\` is optional and may be null`,
    });
  }

  // ── The verdict against the columns ──────────────────────────────────────
  if (delta.delta !== version.control_delta) {
    out.push({
      code: 'verdict_disagrees_with_column',
      level: 'discrepancy',
      title: 'The delta verdict and the clause_version column disagree',
      detail:
        `The DeltaVerdict says "${delta.delta}"; clause_version.control_delta says ` +
        `"${version.control_delta}". These are two renderings of the same fact and they must match.`,
      authority: `${A_DELTA_CONTRACT} · ${A_CLAUSE_VERSION}`,
    });
  }
  if (delta.basis !== version.delta_basis) {
    out.push({
      code: 'basis_disagrees_with_column',
      level: 'discrepancy',
      title: 'The delta basis and the clause_version column disagree',
      detail:
        `The DeltaVerdict says basis "${delta.basis}"; clause_version.delta_basis says ` +
        `"${version.delta_basis}".`,
      authority: `${A_DELTA_CONTRACT} · ${A_CLAUSE_VERSION}`,
    });
  }

  // ── The witness guard ────────────────────────────────────────────────────
  const guarded = delta.delta === 'weaken' || delta.delta === 'remove';
  if (guarded && delta.basis === 'lattice' && observed.witnesses.availability !== 'present') {
    out.push({
      code: 'witness_guard_expectation',
      level: 'discrepancy',
      title: 'A lattice weaken arrived with no witness rows',
      detail:
        `The verdict is "${delta.delta}" on basis "lattice", and this payload carries ` +
        `${
          observed.witnesses.availability === 'unavailable'
            ? 'no witness member at all (witnesses: null)'
            : 'an empty witness list (witnesses: [])'
        }. fn_delta_witness_guard refuses that insert with P0001, so a version in this state ` +
        'should not exist. The console cannot tell you which of the possible causes applies — ' +
        'a cluster without the guard installed, a read API that dropped the rows, or bytes that ' +
        'were never written by a kernel. It reports the contradiction and stops.',
      authority: A_WITNESS_GUARD,
    });
  }
  if (observed.witnesses.availability === 'present' && observed.witnesses.minimal === null) {
    out.push({
      code: 'minimality_unestablished',
      level: 'observation',
      title: 'Minimality of the witness set was not established',
      detail:
        'The emitter set `minimal` to null, which the contract defines as "did not establish", ' +
        'not as "false". The witness set below may or may not be a minimal unsatisfiable subset; ' +
        'nothing on this screen claims that it is.',
      authority: A_DELTA_CONTRACT,
    });
  }

  for (const bound of observed.witnesses.witnesses) {
    if (bound.state === 'no_observed_change') {
      out.push({
        code: 'witness_names_unchanged_field',
        level: 'observation',
        title: `Witness ${bound.witness.rule_id} names a field this diff saw no change at`,
        detail:
          `The row names "${bound.witness.field}" and asserts ` +
          `"${bound.witness.from_repr}" → "${bound.witness.to_repr}". Comparing the two versions ` +
          'in this payload, the console observed no change there. The row is shown verbatim ' +
          'either way.',
        authority: A_DELTA_CONTRACT,
      });
    }
    if (bound.state === 'unresolvable_field') {
      out.push({
        code: 'witness_field_unresolvable',
        level: 'observation',
        title: `Witness ${bound.witness.rule_id} names a field this console does not recognise`,
        detail:
          `"${bound.witness.field}" is not in the console's field vocabulary, so nothing was ` +
          'attached to it. The row is rendered verbatim. Guessing at a target would be the ' +
          'console inventing a correspondence between a database row and a screen element.',
        authority: 'src/features/diff/engine/witness.ts — the vocabulary is closed and declared',
      });
    }
  }

  // ── Parent-relative observations, only where there is a comparable parent ─
  if (parent !== null) {
    if (parent.clause_uuid !== version.clause_uuid) {
      out.push({
        code: 'clause_uuid_disagrees',
        level: 'discrepancy',
        title: 'The two versions belong to different clauses',
        detail:
          `The ancestor is clause ${parent.clause_uuid}; this version is clause ` +
          `${version.clause_uuid}. A clause version chain never changes clause_uuid — a control ` +
          'that moved between clauses is a split or a merge and is recorded as identity residue.',
        authority: `${A_CLAUSE_VERSION} · mainline.identity_residue`,
      });
    }
    if (parent.gen >= version.gen) {
      out.push({
        code: 'generation_not_increasing',
        level: 'discrepancy',
        title: 'The generation did not increase from the ancestor',
        detail:
          `The ancestor is gen ${parent.gen} and this version is gen ${version.gen}. gen is ` +
          'denormalised from commit_obj for bisect ordering, so a descendant must sit strictly ' +
          'later than the version it edits.',
        authority: A_CLAUSE_VERSION,
      });
    }
    const parentBlood = parent.blood_size ?? null;
    const versionBlood = version.blood_size ?? null;
    if (parentBlood !== null && versionBlood !== null && versionBlood < parentBlood) {
      out.push({
        code: 'blood_size_decreased',
        level: 'observation',
        title: 'The bloodline accumulator shrank',
        detail:
          `blood_size went from ${parentBlood} to ${versionBlood}. The M2 accumulator is a ` +
          'Merkle mountain range that is appended to, so a decrease is worth reading the ' +
          'lineage for.',
        authority: A_BLOODLINE,
      });
    }
    if (version.sev_max < parent.sev_max) {
      out.push({
        code: 'severity_decreased',
        level: 'observation',
        title: 'The worst ancestral severity fell between the two versions',
        detail:
          `sev_max went from ${parent.sev_max} to ${version.sev_max}. sev_max is projected from ` +
          'the blame closure by a trigger and is never chosen by a writer, so this reflects a ' +
          'change in the closure — a refuted edge, or a different ancestry — rather than an edit.',
        authority: `${A_CLAUSE_VERSION} — sev_max is PROJECTED (P2)`,
      });
    }
    if (observed.text !== null && observed.text.identical && delta.delta !== 'restate') {
      out.push({
        code: 'text_identical_under_non_restate',
        level: 'observation',
        title: 'The canonical text is byte-identical and the verdict is not `restate`',
        detail:
          `canon_text is identical between the two versions and the verdict is "${delta.delta}". ` +
          'If that is right, the difference the verdict is about lives in cat_json or anchor_set ' +
          'rather than in the prose; both are shown below.',
        authority: A_DELTA_CONTRACT,
      });
    }
  }

  // Discrepancies first, observations after, each keeping the order above. A stable
  // partition rather than a sort: a comparator would let two findings swap places
  // between runs and the model must serialise identically every time.
  return [
    ...out.filter((finding) => finding.level === 'discrepancy'),
    ...out.filter((finding) => finding.level === 'observation'),
  ];
}
