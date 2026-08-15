// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ON-RAMP, PINNED AGAINST THE WAYS IT COULD BECOME A LIE.
 *
 * A plain-language band is the easiest place in this console to smuggle a claim: it is
 * the one part of the screen the console is allowed to word, it is the first thing a
 * judge reads, and a sentence in it looks exactly as authoritative as a constraint name.
 * `docs/leads/two-audience-ux-plan.md` R5–R8 draw the line and this file is where the
 * line is enforced:
 *
 *   1. **The SYNTHETIC marker is the seed's own bytes.** The band renders text that
 *      already opens with the demonstration seed's marker, verbatim, and shows a NAMED
 *      ABSENCE when no payload on the screen carries one. It never composes the marker,
 *      and — proven by mutation — never keeps showing one when the payload stops carrying
 *      it. R5, `db/seeds/demo/demo_world.sql` §preamble.
 *   2. **Every number in the band is the database's.** The open-obligation count is read
 *      off `permit.counters.open_blocking`; change the payload and the sentence changes
 *      with it. A band that carried its own number would keep printing the old one.
 *   3. **PLAIN hides none of the seven.** The refusal bar, the SQLSTATE, the constraint
 *      name, the provenance chips, the STAGED badge, the verbatim message and the marker
 *      are outside every `<details>` in PLAIN, asserted structurally rather than by
 *      reading prose. R6.
 *   4. **The glossary is keyed by WORDS, never by codes.** An entry keyed by `23514` or
 *      by a constraint name would be the console explaining a refusal in its own words,
 *      which is precisely what the refusal bar exists to prevent. R8 / D18.
 *   5. **The headline screen self-addresses.** With no `?permit=` and no subject index,
 *      the permit a `gate-run` payload named is enough to open the screen — and an
 *      address a reader typed still wins over it.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { DetailModeContext } from '../../../src/app/detail-mode';
import { resolveRequest, type ResourceRequest } from '../../../src/data/resources';
import type { Exchange, MainlineTransport } from '../../../src/data/transport';
import {
  GLOSSED_TERMS,
  PRODUCT_WORDS,
  forbiddenWordsIn,
  glossFor,
  sqlstateGloss,
} from '../../../src/design/glossary';
import { MAX_SENTENCES } from '../../../src/design/primitives';
import {
  SUBJECT_ORIGIN_SENTENCE,
  publishGateRunSubject,
  resetGateRunSubject,
} from '../../../src/features/gate/addressing';
import { DemoDriver } from '../../../src/features/gate/DemoDriver';
import { GateSurfaceRoot } from '../../../src/features/gate/GateSurfaceRoot';
import {
  plainGateBand,
  REASON_SET_TITLE,
  WELD_TITLE,
  type PlainBandInput,
} from '../../../src/features/gate/model';
import { GateTransportContext } from '../../../src/features/gate/transport-context';
import type { BlockingCheck, Permit } from '../../../src/data/types.generated';
import { bundleFiles, bundleTransport, permitId, sourcePayload } from './_support';

// ── The fixture, read rather than retyped ──────────────────────────────────

const files = bundleFiles();
const subject = permitId();

/**
 * How long a wait on a bundle-backed read is given.
 *
 * The staged transport hashes every file in the fixture with WebCrypto before it serves
 * anything — that is the verifier gate working, not overhead to be optimised away — and
 * on a loaded machine it exceeds testing-library's 1000 ms default. Raising the WAIT is
 * not weakening an assertion: every expectation below is unchanged, and a read that never
 * lands still fails, one second later.
 */
const WAIT = 5000;

function fixturePermit(): Permit {
  return sourcePayload<{ data: Permit }>('permit.json').data;
}

function fixtureChecks(): readonly BlockingCheck[] {
  return sourcePayload<{ data: { checks: readonly BlockingCheck[] } }>('blocking-checks.json').data
    .checks;
}

function bandInput(over: Partial<PlainBandInput> = {}): PlainBandInput {
  return {
    permitId: subject,
    permit: fixturePermit(),
    checks: fixtureChecks(),
    ancestry: null,
    ...over,
  };
}

beforeEach(() => {
  resetGateRunSubject();
  window.location.hash = '';
});

afterEach(() => {
  resetGateRunSubject();
  window.location.hash = '';
});

// ── 1. The band is three sentences, and every one points at a field ────────

describe('the plain-language band', () => {
  it('never exceeds the three sentences R6 allows', () => {
    expect(plainGateBand(bandInput()).sentences.length).toBeLessThanOrEqual(
      MAX_SENTENCES,
    );
    expect(plainGateBand(bandInput({ permit: null })).sentences.length).toBeLessThanOrEqual(
      MAX_SENTENCES,
    );
  });

  it('reads the open-obligation count off the payload, not out of this console', () => {
    const permit = fixturePermit();
    const moved: Permit = {
      ...permit,
      counters: { ...permit.counters, open_blocking: permit.counters.open_blocking + 41 },
    };

    const band = plainGateBand(bandInput({ permit: moved }));
    const sentence = band.sentences.join(' ');

    expect(sentence).toContain(String(moved.counters.open_blocking));
    expect(band.basis).toContain('permit.counters.open_blocking');
  });

  it('shows no count at all — not a zero — when the permit read has not landed', () => {
    const band = plainGateBand(bandInput({ permit: null, checks: null }));
    const sentence = band.sentences.join(' ');

    expect(sentence).toContain('has not landed');
    expect(sentence).toContain('rather than a zero');
    // The subject line falls back to the identifier, which is a thing somebody named,
    // rather than to a description the console made up.
    expect(sentence).toContain(subject);
  });

  it('names the members it was built from, so the prose can be checked against them', () => {
    expect(plainGateBand(bandInput()).basis.length).toBeGreaterThanOrEqual(3);
  });
});

// ── 1b. The SYNTHETIC marker is the seed's, or it is absent ────────────────

describe('the SYNTHETIC marker', () => {
  it('is the payload’s own text, verbatim, when a payload carries one', () => {
    const checks = fixtureChecks().map((check, index) =>
      index === 0
        ? {
            ...check,
            precursor: {
              ...(check.precursor ?? {
                event_id: check.check_id,
                kind: 'incident' as const,
                occurred_at: check.materialised_at,
                severity_gate: check.severity,
                severity_basis: 'human_rated' as const,
              }),
              title: 'SYNTHETIC — a marker planted by this test and not by any console file',
            },
          }
        : check,
    );

    const band = plainGateBand(bandInput({ checks }));
    expect(band.marker).toBe(
      'SYNTHETIC — a marker planted by this test and not by any console file',
    );
    expect(band.markerField).toBe('blocking_checks.checks[0].precursor.title');
  });

  it('is NULL, and named as absent, when nothing on the screen declares one', () => {
    const checks = fixtureChecks().map((check) =>
      check.precursor === null || check.precursor === undefined
        ? check
        : { ...check, precursor: { ...check.precursor, title: 'no marker on this one' } },
    );

    const band = plainGateBand(bandInput({ checks, ancestry: null }));
    expect(band.marker).toBeNull();
    expect(band.markerField).toBeNull();
  });

  it('renders the absence as a statement rather than going quiet', async () => {
    // The staged `blk-07` bundle is a HAND-AUTHORED capture, not the demonstration seed,
    // and none of its free text opens with the seed's marker. So the honest rendering
    // against this fixture is the NAMED ABSENCE — and the expectation is computed from
    // the fixture rather than written down, so a fixture that gains a marker flips this
    // test rather than leaving it asserting yesterday's bytes.
    const expected = plainGateBand(bandInput()).marker;
    window.location.hash = `#/gate?permit=${subject}`;
    render(
      <GateTransportContext.Provider value={bundleTransport(files)}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );

    const marker = await screen.findByTestId('synthetic-marker', undefined, { timeout: WAIT });
    expect(marker.dataset.synthetic).toBe(expected === null ? 'undeclared' : 'declared');
    if (expected === null) {
      expect(screen.getByTestId('synthetic-marker-absent').textContent).toContain(
        'will not assert either way',
      );
      expect(screen.queryByTestId('synthetic-marker-quote')).toBeNull();
    } else {
      expect(screen.getByTestId('synthetic-marker-quote').textContent).toBe(expected);
    }
  });
});

// ── 2. The glossary explains WORDS, never codes ────────────────────────────

describe('the vocabulary this screen glosses', () => {
  it('is keyed by words and never by a constraint name', () => {
    // A gloss keyed by a constraint name would be the console explaining THIS refusal in
    // its own words. The SQLSTATE table is a different thing and is allowed: it says what
    // a five-character CODE names, it is closed, and `sqlstateGloss` answers null rather
    // than inventing a sentence for a code nobody modelled.
    for (const word of [...PRODUCT_WORDS, ...GLOSSED_TERMS]) {
      expect(word.key).not.toMatch(/_when_issued$/);
      expect(word.key).not.toMatch(/^mainline\./);
      expect(word.key).not.toMatch(/^[0-9A-Z]{5}$/);
    }
  });

  it('carries every term this screen names, so no gloss falls back to a blank', () => {
    const keys = new Set([...PRODUCT_WORDS, ...GLOSSED_TERMS].map((word) => word.key));
    for (const term of [
      'permit',
      'obligation',
      'refusal',
      'synthetic',
      'projection',
      'constraint',
      'gate-epoch',
      'minimal-unsatisfiable-subset',
      'nearest-admissible-alternative',
      'staged',
    ]) {
      expect(keys, `the gate glosses "${term}"`).toContain(term);
    }
  });

  it('uses none of the forbidden words in the sentences this screen composes', () => {
    for (const sentence of plainGateBand(bandInput()).sentences) {
      expect(forbiddenWordsIn(sentence), sentence).toEqual([]);
    }
    for (const sentence of plainGateBand(bandInput({ permit: null })).sentences) {
      expect(forbiddenWordsIn(sentence), sentence).toEqual([]);
    }
    for (const sentence of Object.values(SUBJECT_ORIGIN_SENTENCE)) {
      expect(forbiddenWordsIn(sentence), sentence).toEqual([]);
    }
  });

  it('uses none of them in the use-case walkthrough either, as rendered', async () => {
    // Read off the RENDER rather than off a constant: the walkthrough is deliberately not
    // exported (`react-refresh/only-export-components` is a real rule about a real
    // hazard), and what a judge reads is the page.
    render(
      <GateTransportContext.Provider value={runOnlyTransport()}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    const walkthrough = await screen.findByTestId('demo-walkthrough');
    expect(forbiddenWordsIn(walkthrough.textContent ?? '')).toEqual([]);

    // And it is the walkthrough R9 asks for: what is attempted, why the middle beat is
    // the product, why the fourth matters, and that nothing is kept.
    for (const step of ['attempt', 'tamper', 'admit', 'nothing-kept']) {
      expect(walkthrough.querySelector(`[data-step="${step}"]`), step).not.toBeNull();
    }
    expect(walkthrough.textContent).toContain('re-derives the count from the rows');
    expect(walkthrough.textContent).toContain('always refuses is broken, not safe');
  });
});

// ── 3. Reading mode, in the address and nowhere else ───────────────────────

describe('PLAIN and FULL DETAIL', () => {
  it('folds the exact CHECK expression away in PLAIN and opens it in FULL DETAIL', async () => {
    // The MODE is the shell's — `?detail=full`, parsed once and published through
    // `DetailModeContext` (R6, `src/app/detail-mode.ts`). This surface threads it
    // nowhere, so the test drives the context the shell would provide rather than a prop
    // the screen does not have.
    window.location.hash = `#/gate?permit=${subject}`;
    const { unmount } = render(
      <GateTransportContext.Provider value={bundleTransport(files)}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );

    await waitFor(
      () => {
        expect(screen.getByTestId('weld')).toBeInTheDocument();
      },
      { timeout: WAIT },
    );
    const plain = screen.getByTestId('weld-predicate-gate_closed_when_issued');
    expect(plain).toBeInstanceOf(HTMLDetailsElement);
    expect((plain as HTMLDetailsElement).open).toBe(false);
    // Closed, not gone: the predicate is still in the page, still printable, still
    // findable by the browser's own text search.
    expect(plain.textContent).toContain('open_blocking');
    unmount();

    window.location.hash = `#/gate?permit=${subject}&detail=full`;
    render(
      <DetailModeContext value="full">
        <GateTransportContext.Provider value={bundleTransport(files)}>
          <GateSurfaceRoot />
        </GateTransportContext.Provider>
      </DetailModeContext>,
    );
    await waitFor(
      () => {
        expect(screen.getByTestId('weld')).toBeInTheDocument();
      },
      { timeout: WAIT },
    );
    const full = screen.getByTestId('weld-predicate-gate_closed_when_issued');
    expect((full as HTMLDetailsElement).open).toBe(true);
  });

  it('hides none of the seven things R6 forbids PLAIN to hide', async () => {
    window.location.hash = `#/gate?permit=${subject}`;
    render(
      <GateTransportContext.Provider value={bundleTransport(files)}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );

    const button = await screen.findByTestId('attempt-merge', undefined, { timeout: WAIT });
    await waitFor(
      () => {
        expect(button).toBeEnabled();
      },
      { timeout: WAIT },
    );
    await userEvent.click(button);
    await screen.findByTestId('refusal-constraint', undefined, { timeout: WAIT });

    // Structural, not textual: NONE of these may sit inside a collapsed disclosure.
    for (const testId of [
      'refusal-bar',
      'refusal-constraint',
      'refusal-sqlstate',
      'refusal-message',
      'synthetic-marker',
      'counter-open_blocking',
    ]) {
      const node = screen.getByTestId(testId);
      expect(node.closest('details'), `${testId} is inside a disclosure in PLAIN`).toBeNull();
    }
  });
});

// ── 4. The R7 renames actually reach the screen ────────────────────────────

describe('the headings R7 ruled on', () => {
  it('renders the plain heading and keeps “the weld” as its subtitle', async () => {
    window.location.hash = `#/gate?permit=${subject}`;
    render(
      <GateTransportContext.Provider value={bundleTransport(files)}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );

    const weld = await screen.findByTestId('weld', undefined, { timeout: WAIT });
    expect(weld.getAttribute('aria-label')).toBe(WELD_TITLE);
    expect(screen.getByTestId('weld-subtitle').textContent).toContain('the weld');
    expect(screen.getByTestId('reason-set-absent').textContent).toContain(REASON_SET_TITLE);
  });

  it('labels the merge control in words AND keeps the exact method and path', async () => {
    window.location.hash = `#/gate?permit=${subject}`;
    render(
      <GateTransportContext.Provider value={bundleTransport(files)}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );

    const button = await screen.findByTestId('attempt-merge', undefined, { timeout: WAIT });
    expect(button.textContent).toContain('merge this permit');
    expect(button.textContent).toContain(`POST /v1/permits/${subject}/merge`);
  });

  it('puts a gloss BESIDE the SQLSTATE and the constraint name, never inside them', async () => {
    window.location.hash = `#/gate?permit=${subject}`;
    render(
      <GateTransportContext.Provider value={bundleTransport(files)}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );

    const button = await screen.findByTestId('attempt-merge', undefined, { timeout: WAIT });
    await waitFor(
      () => {
        expect(button).toBeEnabled();
      },
      { timeout: WAIT },
    );
    await userEvent.click(button);

    const code = await screen.findByTestId('refusal-sqlstate', undefined, { timeout: WAIT });
    const sqlstate = screen.getByTestId('refusal-bar').dataset.sqlstate ?? '';
    expect(sqlstate).not.toBe('');

    // The gloss is keyed by the CODE THE BUNDLE CARRIES, and it resolved — a missing
    // entry would mark itself and render the value alone rather than a blank definition.
    const pair = screen.getByTestId('gloss-sqlstate');
    expect(pair.dataset.glossSqlstate).toBe(sqlstate);
    expect(pair.dataset.glossMissing).toBeUndefined();

    // BESIDE, never INSIDE (R8): the element carrying the verbatim five characters
    // carries none of the console's sentence, and the sentence is in its own element.
    const sentence = sqlstateGloss(sqlstate);
    expect(sentence, `the closed table glosses ${sqlstate}`).not.toBeNull();
    expect(code.textContent).toContain(sqlstate);
    expect(code.textContent).not.toContain(sentence);
    expect(pair.textContent).toContain(sentence);

    const constraintPair = screen.getByTestId('gloss-constraint');
    expect(constraintPair.dataset.glossTerm).toBe('constraint');
    expect(screen.getByTestId('refusal-constraint').textContent).not.toContain(
      glossFor('constraint'),
    );
  });
});

// ── 5. Self-addressing, with no subject index and no deploy ────────────────

/** A gate-run payload with a subject that is the FIXTURE's permit, not a literal. */
function gateRun(): Record<string, unknown> {
  const fingerprint = {
    row_counts: { 'mainline.permit': 1 },
    subject_row_counts: { 'mainline.disposition': 0 },
    permit_row: {
      state: 'dispositioned',
      head_seq: 2,
      gate_epoch: 1,
      open_blocking: 1,
      unmet_floor_count: 0,
      countersigned_count: 0,
      merged_commit: null,
    },
  };
  return {
    schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
    run_id: 'run-under-test',
    generated_at: '2026-08-15T00:00:00Z',
    outcome: 'completed',
    verdict: 'PROVEN',
    failures: [],
    persisted: false,
    elapsed_ms: 1,
    transaction: {
      isolation: 'SERIALIZABLE',
      disposition: 'rolled_back',
      opened_logical_timestamp: '1786000000000000000.0000000000',
      closed_logical_timestamp: '1786000000000000000.0000000000',
      single_transaction: true,
      savepoints: [],
      retry_sqlstate: null,
      canonicalisation: 'trappoint-canon/1.0',
    },
    subject: {
      subject_kind: 'permit',
      subject_id: subject,
      external_ref: 'from-the-payload',
      state: 'dispositioned',
      head_seq: 2,
      gate_epoch: 1,
      open_blocking: 1,
      open_blocking_derived: 1,
      blocking_check_id: 'a-check-the-payload-named',
      exposure_receipt_id: null,
      site_code: 'a-site-the-payload-named',
    },
    beats: [
      {
        ordinal: 1,
        name: 'read',
        label: 'read the subject',
        expected: { outcome: 'read' },
        outcome: 'read',
        sqlstate: '00000',
        constraint: null,
        constraint_source: null,
        message: null,
        matched_expectation: true,
        elapsed_ms: 1,
        statement: 'SELECT 1',
        observed: {},
        note: null,
        refusal: { mus: [{ clause_id: 'a-clause-the-payload-named' }] },
      },
    ],
    persistence_check: {
      before: fingerprint,
      after: fingerprint,
      identical: true,
      self_persisted: false,
      self_evidence: {
        minted_disposition_id: null,
        minted_disposition_rows_after_rollback: 0,
        subject_row_counts_before: fingerprint.subject_row_counts,
        subject_row_counts_after: fingerprint.subject_row_counts,
        permit_row_identical: true,
      },
      concurrent_writes: null,
      tables: ['mainline.permit'],
      note: 'nothing was kept',
    },
  };
}

/** A transport that answers the gate-run key and refuses everything else, by name. */
function runOnlyTransport(): MainlineTransport {
  return {
    describe: () => ({
      mode: 'live',
      source: 'https://demo.example.test/api',
      bundleDigestPrefix: null,
      staged: false,
      stagedNote: null,
    }),
    exchange: <T,>(request: ResourceRequest): Promise<Exchange<T>> => {
      const resolved = resolveRequest(request);
      const payload = gateRun();
      return Promise.resolve({
        request: resolved,
        envelope: {
          envelope_version: 1,
          resource: request.resource,
          schema_id: 'https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json',
          staged: false,
          provenance: [],
          data: payload,
        },
        data: payload as unknown as T,
        httpStatus: 200,
        clockSkewMs: null,
        mode: 'live',
      });
    },
  };
}

describe('the headline screen addresses itself from a run’s own payload', () => {
  it('opens on the permit a gate-run answered with, when nothing else named one', async () => {
    // No `?permit=` in the address, and the bundle transport carries no
    // `GET /v1/demo/subjects` frame — which is the LIVE deployment's state today, measured
    // 2026-08-15: that read answers 404 while gate-run answers 200.
    window.location.hash = '#/gate';

    const { unmount } = render(
      <GateTransportContext.Provider value={runOnlyTransport()}>
        <DemoDriver />
      </GateTransportContext.Provider>,
    );
    await userEvent.click(await screen.findByTestId('demo-control-all'));
    await screen.findByTestId('gate-run-report');
    unmount();

    render(
      <GateTransportContext.Provider value={bundleTransport(files)}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );

    const origin = await screen.findByTestId('subject-origin', undefined, { timeout: WAIT });
    expect(origin.dataset.origin).toBe('demo-run');
    expect(origin.textContent).toContain('did not choose this permit');
    expect(await screen.findByTestId('gate-surface', undefined, { timeout: WAIT })).toBeInTheDocument();
  });

  it('lets an address a reader typed win over the subject a run named', async () => {
    publishGateRunSubject({
      permitId: 'a-permit-the-run-named',
      blockingCheckId: null,
      clauseId: null,
      externalRef: null,
      runId: 'run-under-test',
    });
    window.location.hash = `#/gate?permit=${subject}`;

    render(
      <GateTransportContext.Provider value={bundleTransport(files)}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );

    const origin = await screen.findByTestId('subject-origin', undefined, { timeout: WAIT });
    expect(origin.dataset.origin).toBe('address');
    await waitFor(
      () => {
        expect(screen.getByTestId('permit-state')).toBeInTheDocument();
      },
      { timeout: WAIT },
    );
  });
});

// ── 6. With nothing at all, a panel a reader can act on ────────────────────

describe('the no-subject panel', () => {
  it('offers a form rather than an instruction, and keeps the kernel’s own words', async () => {
    window.location.hash = '#/gate';
    render(
      <GateTransportContext.Provider value={bundleTransport(files)}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );

    const panel = await screen.findByTestId('gate-no-subject', undefined, { timeout: WAIT });
    // The plain band says what the screen is for, in the reader's words…
    const band = within(panel).getByTestId('plain-band-no-subject');
    expect(band.textContent).toContain('written authorisation for one specific piece of work');
    // …the form is the way out of the dead end…
    expect(within(panel).getByTestId('gate-address-form')).toBeInTheDocument();
    // …and the exact sentence the console has always said is still on the page.
    expect(panel.textContent).toContain('does not choose one for you');
  });

  it('navigates to the permit a reader pastes, and reads nothing on the way', async () => {
    window.location.hash = '#/gate';
    render(
      <GateTransportContext.Provider value={bundleTransport(files)}>
        <GateSurfaceRoot />
      </GateTransportContext.Provider>,
    );

    const form = await screen.findByTestId('gate-address-form', undefined, { timeout: WAIT });
    await userEvent.type(within(form).getByLabelText('Permit identifier'), subject);
    await userEvent.click(within(form).getByRole('button', { name: 'Show this permit' }));

    await waitFor(() => {
      expect(window.location.hash).toContain(`permit=${subject}`);
    });
  });
});
