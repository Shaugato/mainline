// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

/**
 * THE DEMO DRIVER, PINNED AGAINST THE WAY IT ACTUALLY WENT WRONG.
 *
 * On 2026-08-14 a founder opened the deployed console and read a sentence that had been
 * true when it was written and was false when he read it: that `app.py`'s route table
 * *"declares the four kernel POSTs and no demo route, so the endpoint 404s"*. The route
 * had been on the table since 2026-08-13 and the live URL answers **503 `dsn_unset`** —
 * a reachable route refusing for a named reason. Nothing in this repository was checking
 * the console's prose about other files, so nothing noticed.
 *
 * That is what this file is for (lead ruling **R6**, `docs/leads/console-live-plan.md`).
 * Four obligations, and each one fails loudly rather than quietly:
 *
 *   1. EVERY REPOSITORY PATH THE MODULE NAMES IS READ OFF DISK. A remedy line that sends
 *      a reader to a file that has moved is the same defect with a different noun.
 *   2. NO SENTENCE CLAIMS A 404 THE WIRE DOES NOT PRODUCE — asserted over the array
 *      literal AND over the rendered panel, because a reader reads the render.
 *   3. THE NOT-DECLARED PANEL IS UNREACHABLE WITH THE REAL REGISTRY, while keeping its
 *      own render covered against a STUBBED one. The honest fallback keeps its test; it
 *      merely stops being what a judge sees.
 *   4. THE EXHIBITS COME FROM THE PAYLOAD (D18). Proven by planting SQLSTATEs that are
 *      not the demo's own and requiring the screen to show what was planted — a module
 *      carrying literals would keep printing `23514` and pass every test that expected it.
 *
 * ── WHY THE PROSE IS READ AS SOURCE AND NOT AS AN EXPORT ─────────────────────────
 *
 * `DECLARATION_GAP` is deliberately not exported: `react-refresh/only-export-components`
 * is a real rule about a real hazard, and exporting an array purely so a test can reach it
 * routes around it rather than respecting it. What a judge would read is the file, so the
 * file is what is read here — the same discipline `tests/unit/app/composition.test.tsx`
 * applies to the same array.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { RESOURCES } from '../../../src/data/resources';
import { TransportError, type MainlineTransport } from '../../../src/data/transport';
import {
  DEMO_GATE_RUN,
  DeclarationGapPanel,
  DemoDriver,
  GateRunReport,
  type GateRunData,
} from '../../../src/features/gate/DemoDriver';
import { GateTransportContext } from '../../../src/features/gate/transport-context';
import { REPO_ROOT, nodeFs } from '../data/_support';

const MODULE = 'src/features/gate/DemoDriver.tsx';

// ── Reading the module as bytes ────────────────────────────────────────────

async function moduleSource(): Promise<string> {
  const fs = await nodeFs();
  return fs.readFileSync(MODULE, 'utf8');
}

/**
 * The `DECLARATION_GAP` array literal, and nothing else in the file.
 *
 * The module docstring QUOTES the false sentence in order to record what was corrected
 * and why. That quotation is the repair, not a relapse, so a scan for the false claim
 * must be scoped to the prose a reader is shown rather than run over the whole file.
 */
function declarationGapSource(file: string): string {
  const start = file.indexOf('const DECLARATION_GAP');
  expect(
    start,
    'DECLARATION_GAP must still exist: it is the honest fallback panel’s prose, and lead ' +
      'ruling R2 keeps it for a build that ever strips the declaration.',
  ).toBeGreaterThan(-1);
  const end = file.indexOf('\n];', start);
  expect(end).toBeGreaterThan(start);
  return file.slice(start, end);
}

/**
 * Every repository path a chunk of text names.
 *
 * An extension is required, so `POST /v1/demo/gate-run` and the SSM parameter name
 * `/mainline/demo/cockroach_dsn` are not mistaken for files — they are not files, and a
 * check that failed on them would be deleted within a week.
 *
 * `tsx` precedes `ts` in the alternation because a regex alternation is ordered: with
 * `ts` first, `composition.test.tsx` matches as `composition.test.ts`, which does not
 * exist, and the check fails on a file that is present. Measured while writing this.
 *
 * A specifier beginning with a dot is an IMPORT, not a claim about the repository, and
 * TypeScript already resolves those; they are dropped rather than resolved twice.
 */
const PATH_PATTERN = /(?:[\w.@-]+\/)+[\w.@-]+\.(?:tsx|ts|py|json|md|css|sh|ps1)/g;

function pathsNamedIn(text: string): readonly string[] {
  const named = new Set<string>();
  for (const match of text.matchAll(PATH_PATTERN)) {
    const value = match[0];
    // An import specifier: TypeScript resolves those, and resolving them twice teaches
    // nothing.
    if (value.startsWith('.')) continue;
    // A TAIL of something longer — `…/contracts/1.0/gate-run.schema.json` is a schema
    // `$id`, not a file. A repository path in this prose starts where the match starts;
    // a URL fragment has a slash immediately in front of it.
    if (text.charAt(match.index - 1) === '/') continue;
    named.add(value);
  }
  return [...named].sort();
}

/**
 * Where a named path is allowed to be.
 *
 * The module writes paths in three registers and all three are legitimate: repo-relative
 * (`docs/leads/ui.md`), console-relative (`src/data/resources.ts` — the file's own
 * neighbours), and app-relative (`demo-api/tests/…`). Vitest's working directory is the
 * console workspace, which is what a relative read resolves against.
 */
const ROOTS: readonly string[] = ['', REPO_ROOT, `${REPO_ROOT}verticals/mainline/apps/`];

async function unresolvable(paths: readonly string[]): Promise<readonly string[]> {
  const fs = await nodeFs();
  return paths.filter((path) => !ROOTS.some((root) => fs.existsSync(`${root}${path}`)));
}

// ── 1. The prose is checked against the tree ───────────────────────────────

describe('every file the driver names is a file that exists', () => {
  it('resolves every repository path in the remedy list', async () => {
    const gap = declarationGapSource(await moduleSource());
    const named = pathsNamedIn(gap);

    // A vacuous pass is the failure mode this test has to survive: a regex that stopped
    // matching would report "every path resolved" over an empty list. The remedy list
    // names five files today and the count is a floor, not a fixture.
    expect(named.length, `no path was found in DECLARATION_GAP: ${gap}`).toBeGreaterThanOrEqual(5);
    expect(named).toContain('verticals/mainline/apps/console/src/data/resources.ts');
    expect(named).toContain('verticals/mainline/apps/console/src/data/contracts.ts');
    expect(named).toContain('verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py');

    expect(await unresolvable(named)).toEqual([]);
  });

  it('resolves every repository path the module names anywhere, comments included', async () => {
    // Wider than R6 requires, deliberately. The sentence that shipped false was prose
    // about another file; a comment that goes stale the same way is the same defect one
    // edit away from being rendered.
    const named = pathsNamedIn(await moduleSource());
    expect(named.length).toBeGreaterThanOrEqual(10);
    expect(await unresolvable(named)).toEqual([]);
  });

  it('names this very test file, so the claim that it is pinned is itself checked', async () => {
    expect(pathsNamedIn(await moduleSource())).toContain('tests/unit/gate/demo-driver.test.tsx');
  });
});

// ── 2. No sentence claims a 404 the wire does not produce ──────────────────

/**
 * Every occurrence of `404` that is not a DENIAL of one.
 *
 * A blanket ban on the digits would forbid the correction itself — *"a reachable route
 * refusing for a named reason, never a 404"* is the sentence that replaced the false one,
 * and it has to be sayable. So each occurrence is read with its lead-in: a `404` reached
 * through "never", "not" or "rather than" is a denial; anything else is a claim about the
 * wire, and the wire answers **503 `dsn_unset`**, measured 2026-08-14.
 */
function claimsA404(text: string): readonly string[] {
  const offenders: string[] = [];
  const pattern = /404/g;
  let match = pattern.exec(text);
  while (match !== null) {
    const lead = text.slice(Math.max(0, match.index - 60), match.index);
    if (!/\b(?:never|not|rather than)\b[^.]*$/i.test(lead)) {
      offenders.push(`${lead}${text.slice(match.index, match.index + 24)}`);
    }
    match = pattern.exec(text);
  }
  return offenders;
}

describe('the driver does not claim a refusal the wire never sent', () => {
  it('carries no 404 claim in the prose a reader is shown', async () => {
    const gap = declarationGapSource(await moduleSource());

    expect(claimsA404(gap)).toEqual([]);
    expect(gap).not.toMatch(/declares the four kernel POSTs and no demo route/);
    expect(gap).not.toMatch(/is not (?:yet )?routed/);

    // What replaced it is the measurement, and the measurement names its own cause.
    expect(gap).toMatch(/503 dsn_unset/);
    expect(gap).toMatch(/ALREADY DONE/);
  });

  it('renders no 404 claim either, which is the half a source scan cannot see', () => {
    render(<DeclarationGapPanel resources={strippedRegistry()} />);
    const panel = screen.getByTestId('demo-driver-not-declared');

    expect(claimsA404(panel.textContent ?? '')).toEqual([]);
    expect(panel).toHaveTextContent('503 dsn_unset');

    // And it still tells the reader what to restore, which is the only reason to keep it.
    const remedies = within(panel).getAllByRole('listitem');
    expect(remedies).toHaveLength(3);
    expect(panel).toHaveTextContent('src/data/resources.ts');
    expect(panel).toHaveTextContent('src/data/contracts.ts');
  });
});

// ── 3. Unreachable in this build, still covered ────────────────────────────

/**
 * The registry a build that stripped the declaration would ship: today's, minus the one
 * key. Built from the REAL registry rather than invented, so a rename of any other
 * resource cannot leave this stub describing a console nobody ships.
 */
function strippedRegistry(): ReadonlyMap<string, unknown> {
  const stripped = new Map<string, unknown>(RESOURCES);
  stripped.delete(DEMO_GATE_RUN);
  expect(stripped.size).toBe(RESOURCES.size - 1);
  return stripped;
}

/** A transport that is present and would refuse to be called at mount. */
function idleTransport(mode: 'live' | 'replay'): MainlineTransport {
  return {
    describe: () => ({
      mode,
      source: mode === 'live' ? 'https://demo.example.test/api' : 'https://demo.example.test/bundle/',
      bundleDigestPrefix: null,
      staged: false,
      stagedNote: null,
    }),
    exchange: () =>
      Promise.reject(new Error('the driver must not exchange before a control is pressed')),
  };
}

describe('the not-declared panel is unreachable with the real registry', () => {
  it('is not what the shipped registry produces', () => {
    // The registry is authoritative, and it is asserted directly rather than inferred
    // from the absence of a panel — an absent panel could also mean an absent render.
    expect(RESOURCES.has(DEMO_GATE_RUN)).toBe(true);

    render(
      <GateTransportContext.Provider value={idleTransport('live')}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );

    expect(screen.queryByTestId('demo-driver-not-declared')).toBeNull();
    expect(screen.getByTestId('demo-driver')).toBeInTheDocument();
  });

  it('is exactly what a registry without the key produces', () => {
    // The fallback keeps its own coverage. It is rendered against a stubbed registry
    // rather than by deleting the real declaration, because a suite that can strip the
    // shipped registry is one accident away from testing a console nobody ships.
    const stripped = strippedRegistry();
    render(<DeclarationGapPanel resources={stripped} />);

    const panel = screen.getByTestId('demo-driver-not-declared');
    expect(panel).toHaveTextContent(DEMO_GATE_RUN);
    expect(panel).toHaveTextContent(String(stripped.size));
    expect(panel).toHaveTextContent('D7');
  });
});

// ── 4. The four controls, in both transports ───────────────────────────────

describe('the four controls are one composition, not two code paths', () => {
  it.each(['live', 'replay'] as const)('offers all four under %s', (mode) => {
    // D7, as stated in src/app/source-select.ts: LIVE and REPLAY are one line of
    // composition and one badge, NEVER a code path. A control shown in LIVE and hidden
    // in REPLAY would be the second code path, and hiding it is the tempting fix,
    // because no bundle carries a gate-run frame yet.
    render(
      <GateTransportContext.Provider value={idleTransport(mode)}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );

    for (const control of ['merge', 'forge', 'admit', 'all']) {
      expect(screen.getByTestId(`demo-control-${control}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId('demo-driver')).toHaveTextContent('POST /v1/demo/gate-run');
  });

  it('renders a REPLAY bundle’s honest absence verbatim rather than hiding the control', async () => {
    // The correct REPLAY rendering TODAY, and a named gap rather than a defect: no
    // bundle carries a POST /v1/demo/gate-run frame, capturing one needs a live run
    // against the cloud, and that needs a secret this wave does not hold. src/data/
    // bundle.ts refuses by name; the driver shows the refusal without editorialising.
    const detail =
      'bundle "demo-cloud" has no frame for this request. It captured a different set of ' +
      'exchanges; it is not incomplete for this one.';
    const transport: MainlineTransport = {
      describe: () => ({
        mode: 'replay',
        source: 'https://demo.example.test/bundle/',
        bundleDigestPrefix: 'a1b2c3d4',
        staged: true,
        stagedNote: 'staged capture',
      }),
      exchange: () =>
        Promise.reject(
          new TransportError('missing_frame', `POST /v1/demo/gate-run ${DEMO_GATE_RUN}`, detail),
        ),
    };

    const user = userEvent.setup();
    render(
      <GateTransportContext.Provider value={transport}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    await user.click(screen.getByTestId('demo-control-all'));

    const failed = await screen.findByTestId('demo-run-failed');
    expect(failed).toHaveTextContent('missing_frame');
    expect(within(failed).getByText(detail)).toBeInTheDocument();
    // The control is still there to press again. An absence is a state, not a dead end.
    expect(screen.getByTestId('demo-control-all')).toBeInTheDocument();
  });

  it('performs no exchange until a human presses something', async () => {
    // `enabled: declared && reveal !== null`. A driver that ran on mount would make the
    // demo a page that fires a transaction at anybody who opens the URL.
    const transport = idleTransport('live');
    render(
      <GateTransportContext.Provider value={transport}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('demo-driver')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('demo-run-failed')).toBeNull();
    expect(screen.queryByTestId('gate-run-report')).toBeNull();
  });
});

// ── 5. D18 — every exhibit comes from the payload ──────────────────────────

/**
 * A payload whose exhibits are DELIBERATELY NOT THE DEMO'S OWN.
 *
 * `23514` / `gate_closed_when_issued` and `P0001` / `mainline.fn_permit_merge_gate` are
 * the codes this demo exists to show, and they appear in the module as the expectation
 * each control was WRITTEN AGAINST — printed on the button, beside what came back. That
 * is the comparison the screen is for. It is also exactly what would let a literal hide:
 * a module that rendered its own expectation instead of the payload would satisfy a test
 * that expected the real codes.
 *
 * So this fixture plants codes no beat of this demo can produce. If any of them fails to
 * reach the screen, or if the real ones appear beside them, the exhibits are not coming
 * from the payload.
 */
function plantedRun(): GateRunData {
  const beat = (
    ordinal: number,
    name: string,
    outcome: string,
    sqlstate: string,
    constraint: string | null,
    constraintSource: 'reported' | 'parsed' | 'absent' | null,
  ): GateRunData['beats'][number] => ({
    ordinal,
    name,
    label: `beat ${ordinal}, as the fixture describes it`,
    expected: { outcome },
    outcome,
    sqlstate,
    constraint,
    constraint_source: constraintSource,
    message: `PLANTED MESSAGE FOR BEAT ${ordinal}`,
    matched_expectation: true,
    elapsed_ms: ordinal,
    statement: `SELECT ${ordinal}`,
    observed: { planted_ordinal: ordinal },
    note: null,
  });

  const fingerprint = {
    row_counts: { 'mainline.permit': 7 },
    subject_row_counts: {
      'mainline.merge_record': 0,
      'mainline.permit_event': 2,
      'mainline.disposition': 1,
    },
    permit_row: {
      state: 'planted',
      head_seq: 9,
      gate_epoch: 2,
      open_blocking: 5,
      unmet_floor_count: 5,
      countersigned_count: 0,
      merged_commit: null,
    },
  } as const;

  return {
    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
    run_id: 'planted-not-the-demo',
    generated_at: '2026-08-14T00:00:00Z',
    outcome: 'completed',
    verdict: 'PROVEN',
    failures: [],
    persisted: false,
    elapsed_ms: 10,
    transaction: {
      isolation: 'SERIALIZABLE',
      disposition: 'rolled_back',
      opened_logical_timestamp: '1786000000000000000.0000000000',
      closed_logical_timestamp: '1786000000000000000.0000000000',
      single_transaction: true,
      savepoints: ['gate_run_beat_2'],
      retry_sqlstate: null,
      canonicalisation: 'trappoint-canon/1.0',
    },
    subject: {
      subject_kind: 'permit',
      subject_id: '00000000-0000-4000-8000-000000000000',
      external_ref: 'planted/fixture',
      state: 'planted',
      head_seq: 9,
      gate_epoch: 2,
      open_blocking: 5,
      open_blocking_derived: 5,
      blocking_check_id: null,
      exposure_receipt_id: null,
      site_code: 'PLANT-00',
    },
    beats: [
      beat(1, 'read', 'read', '01000', null, null),
      beat(2, 'merge', 'refused', '42501', 'planted_check_not_the_real_one', 'reported'),
      beat(3, 'projection_drift_attack', 'refused', 'P0002', 'planted.fn_not_the_real_one', 'parsed'),
      beat(4, 'admit', 'admitted', '02000', null, null),
    ],
    persistence_check: {
      before: fingerprint,
      after: fingerprint,
      identical: true,
      self_persisted: false,
      self_evidence: {
        minted_disposition_id: 'planted-disposition-id',
        minted_disposition_rows_after_rollback: 0,
        subject_row_counts_before: fingerprint.subject_row_counts,
        subject_row_counts_after: fingerprint.subject_row_counts,
        permit_row_identical: true,
      },
      concurrent_writes: null,
      tables: ['mainline.permit'],
      note: 'PLANTED NOTE, carried verbatim.',
    },
  };
}

describe('the exhibits are the payload’s, not the module’s', () => {
  it('renders planted SQLSTATEs and constraint names, and none of the demo’s own', () => {
    const run = plantedRun();
    render(<GateRunReport run={run} reveal="all" />);
    const report = screen.getByTestId('gate-run-report');

    expect(screen.getByTestId('gate-run-beat-2-sqlstate')).toHaveTextContent('42501');
    expect(screen.getByTestId('gate-run-beat-2-constraint')).toHaveTextContent(
      'planted_check_not_the_real_one',
    );
    expect(screen.getByTestId('gate-run-beat-3-sqlstate')).toHaveTextContent('P0002');
    expect(screen.getByTestId('gate-run-beat-3-constraint')).toHaveTextContent(
      'planted.fn_not_the_real_one',
    );
    expect(screen.getByTestId('gate-run-beat-4-sqlstate')).toHaveTextContent('02000');

    // EVERY exhibit on the report, read off the primitives' own data attributes and
    // compared against the payload as a whole list. An extra exhibit would be one this
    // module invented; a missing one would be a beat whose evidence it dropped; and the
    // demo's own codes cannot appear, because this run did not produce them.
    //
    // Scoped to the exhibits rather than to the report's text, deliberately: an
    // UNMODELLED sqlstate makes `Sqlstate` print `spec/errors.md` §1.1's closed set,
    // which NAMES 23514 and P0001. That sentence is the primitive being honest about
    // what the spec covers, and a text-level ban would have failed on it — measured.
    const sqlstates = [...report.querySelectorAll('[data-sqlstate]')].map((node) =>
      node.getAttribute('data-sqlstate'),
    );
    expect(sqlstates).toEqual(run.beats.map((planted) => planted.sqlstate));

    const constraints = [...report.querySelectorAll('[data-constraint]')].map((node) =>
      node.getAttribute('data-constraint'),
    );
    expect(constraints).toEqual(
      run.beats.map((planted) => planted.constraint).filter((name) => name !== null),
    );
  });

  it('renders the message verbatim and the observed keys as the payload’s own names', () => {
    render(<GateRunReport run={plantedRun()} reveal="all" />);
    expect(screen.getByTestId('gate-run-beat-3-message').textContent).toBe(
      'PLANTED MESSAGE FOR BEAT 3',
    );
    expect(screen.getByTestId('gate-run-beat-3-observed')).toHaveTextContent('planted_ordinal');
  });

  it('separates a PARSED exhibit from a reported one on constraint_source alone', () => {
    // The weakened-diagnosis paragraph keys on `constraint_source`, never on the code —
    // a run whose exhibits were INFERRED must never look like one whose exhibits were
    // REPORTED. Beat 3 is `parsed` here and carries a code that is not P0001, so a branch
    // that chose the paragraph by SQLSTATE would put it on the wrong beat or on neither.
    render(<GateRunReport run={plantedRun()} reveal="all" />);
    expect(screen.getByTestId('gate-run-beat-3-parsed')).toHaveTextContent(/WEAKENED/);
    expect(screen.queryByTestId('gate-run-beat-2-parsed')).toBeNull();
  });

  it('contains no branch that chooses a sentence from a code', async () => {
    // D18, enforced by what the file does not contain. The exhibits are rendered through
    // Sqlstate and ConstraintName; nothing may compare a SQLSTATE or a constraint name
    // and pick prose from the result.
    const file = await moduleSource();
    const code = file
      .split(/\r?\n/)
      .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
      .join('\n');

    // A comparison against a STRING is the defect; `beat.sqlstate !== null` is the
    // presence test that decides whether there is an exhibit to render at all, and it
    // reads no code. The two are distinguished by what is on the right-hand side.
    expect(code).not.toMatch(/\bsqlstate\b\s*[=!]==\s*['"]/i);
    expect(code).not.toMatch(/\bconstraint\b\s*[=!]==\s*['"]/i);
    expect(code).not.toMatch(/[=!]==\s*['"](?:23514|P0001|00000)['"]/);
    expect(code).not.toMatch(/\.(?:includes|startsWith|match)\(\s*['"](?:23514|P0001)['"]/);
  });
});

// ── 6. R10 — the persistence reading is the contract's, widened ────────────

describe('the persistence check shows the field the verdict keys on', () => {
  it('renders self_persisted and concurrent_writes beside identical, removing neither', () => {
    render(<GateRunReport run={plantedRun()} reveal="all" />);
    const persistence = screen.getByTestId('gate-run-persistence');

    expect(persistence).toHaveTextContent('self_persisted');
    expect(persistence).toHaveTextContent('identical');
    expect(persistence).toHaveTextContent('concurrent_writes');
    expect(persistence).toHaveTextContent('tables compared');
    expect(persistence).toHaveTextContent('PLANTED NOTE, carried verbatim.');
  });

  it('carries the run-scoped evidence self_persisted was computed from', () => {
    render(<GateRunReport run={plantedRun()} reveal="all" />);
    const self = screen.getByTestId('gate-run-persistence-self');
    expect(self).toHaveTextContent('planted-disposition-id');
    expect(self).toHaveTextContent('rows carrying it after the rollback');
  });

  it('walks the permit row’s columns rather than listing them in this module', () => {
    // Beat 3 mutates a COLUMN, which no count can see, so the columns are the reading
    // that catches it. They are walked from the payload: a column the contract adds
    // appears on screen without an edit here, and a column it drops disappears.
    const run = plantedRun();
    render(<GateRunReport run={run} reveal="all" />);
    for (const column of Object.keys(run.persistence_check.before.permit_row ?? {})) {
      expect(screen.getByTestId(`gate-run-fingerprint-permit_row.${column}`)).toBeInTheDocument();
    }
  });

  it('shows the fingerprint only under RUN ALL, where the run’s own witnesses live', () => {
    render(<GateRunReport run={plantedRun()} reveal={2} />);
    expect(screen.queryByTestId('gate-run-persistence')).toBeNull();
    expect(screen.queryByTestId('gate-run-fingerprint')).toBeNull();
  });
});
