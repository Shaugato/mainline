// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The silence surface, end to end through the real replay transport.
 *
 * Every expected number is read out of the fixture bundle at run time; the last blocks
 * re-seal MUTATED bundles and require the screen to follow. The three claims defended here
 * are the three the brief names:
 *
 *   1. the conservation identity renders AND balances, with its constraint name;
 *   2. the PER honest-limit sentence appears, together with the receipt's own verbatim
 *      bounding statement; and
 *   3. no score is displayed without its threshold and its policy version — asserted by
 *      stripping the threshold from a re-sealed bundle and requiring the NUMBER to leave
 *      the DOM, not merely to lose a caption.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { HonestyProvider } from '../../../src/app/HonestyProvider';
import { PER_LIMIT_SENTENCE } from '../../../src/features/silence/model';
import { SilenceSurfaceRoot } from '../../../src/features/silence/SilenceSurfaceRoot';
import { SilenceTransportContext } from '../../../src/features/silence/transport-context';
import type { MainlineTransport } from '../../../src/data/transport';

import {
  bundleFiles,
  bundleTransport,
  mutateFrame,
  permitId,
  recallRunFramePath,
  silenceFramePath,
  sourceRecallRun,
  sourceSilence,
} from './_fixture';

const PERMIT = permitId();
const SILENCE_FRAME = silenceFramePath();
const RUN_FRAME = recallRunFramePath();
const SILENCE = sourceSilence().data;
const RUN = sourceRecallRun().data;

function mount(transport: MainlineTransport | null): ReactNode {
  window.location.hash = `#/silence?permit=${PERMIT}`;
  return (
    <HonestyProvider>
      <SilenceTransportContext.Provider value={transport}>
        <SilenceSurfaceRoot />
      </SilenceTransportContext.Provider>
    </HonestyProvider>
  );
}

/*
 * THE WAITS ARE EXPLICIT, AND THAT IS A HARNESS FACT RATHER THAN A SOFTENED ASSERTION.
 *
 * This surface performs TWO chained exchanges through the real replay transport — the
 * silence ledger, then the recall run the receipt names — and the second cannot start until
 * the first has landed, by design (`useSilenceData` says why: a conservation identity
 * belonging to a different retrieval than the rows under it would be the most convincing
 * wrong screen this console could paint). Both go through bundle verification. At Testing
 * Library's default one second these helpers failed intermittently under the fully parallel
 * tier while passing every time in isolation, which is a statement about a shared machine
 * and not about the screen. Every expectation below is unchanged; only the patience is.
 */
const SETTLE = { timeout: 10_000 } as const;

// The per-case ceiling has to clear the wait above, or the case dies at five seconds while
// the arithmetic it is waiting for is still running and the report reads as a screen defect.
vi.setConfig({ testTimeout: 20_000 });

async function renderReady(files: ReadonlyMap<string, Uint8Array>): Promise<void> {
  render(mount(bundleTransport(files)));
  await waitFor(() => {
    expect(screen.getByTestId('entry-list')).toBeInTheDocument();
  }, SETTLE);
}

async function renderWithRun(files: ReadonlyMap<string, Uint8Array>): Promise<void> {
  render(mount(bundleTransport(files)));
  await waitFor(() => {
    expect(screen.getByTestId('conservation-panel')).toBeInTheDocument();
  }, SETTLE);
}

describe('no transport, no claim', () => {
  it('says NO SOURCE rather than painting an empty ledger', () => {
    render(mount(null));
    expect(screen.getByTestId('silence-no-source')).toHaveTextContent('No transport was provided');
    expect(screen.queryByTestId('entry-list')).toBeNull();
  });
});

describe('the conservation identity', () => {
  it('renders every term and the sum this browser computed', async () => {
    await renderWithRun(bundleFiles());

    expect(screen.getByTestId('conservation-total')).toHaveTextContent(
      String(RUN.counts.n_candidates),
    );
    expect(screen.getByTestId('conservation-n_blocking')).toHaveTextContent(
      String(RUN.counts.n_blocking),
    );
    expect(screen.getByTestId('conservation-n_advisory')).toHaveTextContent(
      String(RUN.counts.n_advisory),
    );
    expect(screen.getByTestId('conservation-n_silenced')).toHaveTextContent(
      String(RUN.counts.n_silenced),
    );
    expect(screen.getByTestId('conservation-n_deduped')).toHaveTextContent(
      String(RUN.counts.n_deduped),
    );
  });

  it('VISIBLY BALANCES — the rendered sum equals the rendered total', async () => {
    await renderWithRun(bundleFiles());

    const total = Number(screen.getByTestId('conservation-total').textContent);
    const sum = Number(screen.getByTestId('conservation-sum').textContent);
    expect(Number.isFinite(total)).toBe(true);
    expect(sum).toBe(total);

    expect(screen.getByTestId('conservation-equation')).toHaveAttribute('data-balances', 'true');
    expect(screen.getByTestId('conservation-constraint')).toHaveTextContent('candidates_conserved');
    expect(screen.queryByTestId('conservation-imbalance')).toBeNull();
  });

  it('renders the bonded invariant as a satisfied constraint, by name', async () => {
    await renderWithRun(bundleFiles());
    expect(screen.getByTestId('bonded-equation')).toHaveAttribute('data-holds', 'true');
    expect(screen.getByTestId('bonded-constraint')).toHaveTextContent(
      'bonded_fatalities_all_blocking',
    );
    expect(screen.getByTestId('bonded-total')).toHaveTextContent(String(RUN.counts.n_bonded_sev5));
    expect(screen.getByTestId('bonded-blocking')).toHaveTextContent(
      String(RUN.counts.n_bonded_sev5_blocking),
    );
  });

  it('says so loudly when a re-sealed bundle breaks the identity', async () => {
    // A payload violating a CHECK the database enforces did not come from that database.
    // That is a far more interesting finding than a rounding error, and it must not be
    // absorbed silently.
    const files = await mutateFrame(bundleFiles(), RUN_FRAME, (envelope) => {
      const data = envelope.data as { counts: Record<string, number> };
      data.counts.n_silenced = (data.counts.n_silenced ?? 0) + 1;
    });

    await renderWithRun(files);
    expect(screen.getByTestId('conservation-equation')).toHaveAttribute('data-balances', 'false');
    expect(screen.getByTestId('conservation-imbalance')).toHaveTextContent(
      'THIS IDENTITY DOES NOT BALANCE',
    );
  });
});

describe('arms', () => {
  it('states the degraded flag in both directions, taking it from the bundle', async () => {
    await renderWithRun(bundleFiles());
    expect(screen.getByTestId('arms-degraded')).toHaveAttribute(
      'data-degraded',
      String(RUN.arms_degraded),
    );
  });

  it('becomes prominent when a re-sealed bundle degrades an arm', async () => {
    const files = await mutateFrame(bundleFiles(), RUN_FRAME, (envelope) => {
      const data = envelope.data as Record<string, unknown>;
      data.arms_degraded = true;
      const arms = data.arms as Record<string, unknown>[] | undefined;
      if (arms?.[0] !== undefined) arms[0].degraded = true;
    });

    await renderWithRun(files);
    const panel = screen.getByTestId('arms-degraded');
    expect(panel).toHaveAttribute('data-degraded', 'true');
    expect(panel).toHaveTextContent('arms_degraded = true');
  });
});

describe('the PER commitment', () => {
  it('renders theta, s, n and both boundary leaves from the bundle', async () => {
    await renderReady(bundleFiles());
    const receipt = SILENCE.receipt;
    if (receipt === null) throw new Error('no receipt in the fixture');

    expect(screen.getByTestId('per-theta')).toHaveTextContent(String(receipt.theta));
    expect(screen.getByTestId('per-s')).toHaveTextContent(String(receipt.s));
    expect(screen.getByTestId('per-n')).toHaveTextContent(String(receipt.n));
    expect(screen.getByTestId('per-leaf-s-score')).toHaveTextContent(
      String(receipt.boundary_proof.leaf_s.score),
    );
    expect(screen.getByTestId('per-bracket')).toHaveAttribute('data-brackets', 'true');
  });

  it('carries the honest-limit sentence VERBATIM', async () => {
    await renderReady(bundleFiles());
    expect(screen.getByTestId('per-limit-sentence')).toHaveTextContent(PER_LIMIT_SENTENCE);
  });

  it('also carries the emitter’s own bounding statement, verbatim from the payload', async () => {
    await renderReady(bundleFiles());
    const receipt = SILENCE.receipt;
    if (receipt === null) throw new Error('no receipt in the fixture');
    expect(screen.getByTestId('per-bound-statement')).toHaveTextContent(receipt.bound.statement);
  });

  it('shows NO seal — the inclusion paths are displayed, not verified', async () => {
    await renderReady(bundleFiles());
    expect(screen.getByTestId('per-not-recomputed')).toHaveTextContent('DISPLAYED, not verified');
    // The console's only green belongs to the VerificationSeal. Nothing on this surface has
    // been cryptographically verified, so no seal may appear here.
    expect(screen.queryByTestId('verification-seal')).toBeNull();
  });
});

describe('the ledger', () => {
  it('renders every row in full rather than a count', async () => {
    await renderReady(bundleFiles());
    expect(screen.getAllByTestId('entry')).toHaveLength(SILENCE.entries.length);
  });

  it('renders the vocabularies exactly as the CHECK constraints spell them', async () => {
    await renderReady(bundleFiles());
    const sources = screen.getAllByTestId('entry-source').map((node) => node.textContent);
    for (const entry of SILENCE.entries) {
      expect(sources.some((text) => text?.includes(entry.source))).toBe(true);
    }
  });

  it('shows a score only beside its threshold and its policy version', async () => {
    await renderReady(bundleFiles());
    const scored = SILENCE.entries.find((entry) => (entry.score ?? null) !== null);
    if (scored === undefined) throw new Error('the fixture has no scored entry');

    const shown = screen
      .getAllByTestId('entry-score')
      .filter((node) => node.getAttribute('data-score-state') === 'shown');
    expect(shown.length).toBeGreaterThan(0);
    for (const node of shown) {
      expect(node.querySelector('[data-testid="entry-threshold-value"]')).not.toBeNull();
      expect(node.querySelector('[data-testid="entry-policy-version"]')).not.toBeNull();
    }
    expect(screen.getAllByTestId('entry-score-value')[0]).toHaveTextContent(String(scored.score));
  });

  it('WITHHOLDS the number when a re-sealed bundle removes the threshold', async () => {
    const scored = SILENCE.entries.find((entry) => (entry.score ?? null) !== null);
    if (scored === undefined) throw new Error('the fixture has no scored entry');

    const files = await mutateFrame(bundleFiles(), SILENCE_FRAME, (envelope) => {
      const data = envelope.data as { entries: Record<string, unknown>[] };
      for (const row of data.entries) {
        if (row.silence_id === scored.silence_id) row.threshold = null;
      }
    });

    await renderReady(files);
    const withheld = screen
      .getAllByTestId('entry-score')
      .filter((node) => node.getAttribute('data-score-state') === 'withheld');
    expect(withheld.length).toBeGreaterThan(0);
    expect(withheld[0]).toHaveTextContent('threshold');

    // The NUMBER must be gone, not merely uncaptioned. This is the assertion that would
    // stay green against a component that rendered the score and hid the label.
    const entryNode = withheld[0]?.closest('[data-testid="entry"]');
    expect(entryNode?.querySelector('[data-testid="entry-score-value"]')).toBeNull();
  });

  it('expands the arithmetic with its policy version and its calibration commit', async () => {
    await renderReady(bundleFiles());
    const scored = SILENCE.entries.find((entry) => (entry.score ?? null) !== null);
    if (scored === undefined) throw new Error('the fixture has no scored entry');

    const table = screen.getByTestId(`entry-arithmetic-${scored.silence_id}`);
    expect(table).toHaveAttribute('data-raw-admissible', 'true');
    expect(table.querySelector('[data-testid="arithmetic-policy-version"]')).toHaveTextContent(
      scored.policy_version ?? '',
    );
    expect(table.querySelector('[data-testid="arithmetic-calibrator"]')).not.toBeNull();
    expect(table.querySelectorAll('[data-testid="arithmetic-row"]').length).toBeGreaterThan(3);
  });

  it('WITHHOLDS raw similarities when a re-sealed bundle strips the calibration', async () => {
    const scored = SILENCE.entries.find((entry) =>
      JSON.stringify(entry.arithmetic).includes('cosine'),
    );
    if (scored === undefined) throw new Error('the fixture has no entry with a cosine');

    const files = await mutateFrame(bundleFiles(), SILENCE_FRAME, (envelope) => {
      const data = envelope.data as { entries: Record<string, unknown>[] };
      for (const row of data.entries) {
        if (row.silence_id !== scored.silence_id) continue;
        row.score = null;
        row.threshold = null;
        const arithmetic = row.arithmetic as Record<string, unknown>;
        delete arithmetic.p_relevant;
      }
    });

    await renderReady(files);
    const table = screen.getByTestId(`entry-arithmetic-${scored.silence_id}`);
    expect(table).toHaveAttribute('data-raw-admissible', 'false');
    expect(table.querySelector('[data-testid="arithmetic-raw-refused"]')).not.toBeNull();

    // The cosine's VALUE must be absent from the raw rows; the row, path and kind stay.
    const rawRows = [...table.querySelectorAll('[data-kind="raw_similarity"]')];
    expect(rawRows.length).toBeGreaterThan(0);
    for (const row of rawRows) {
      expect(row.querySelector('[data-testid="arithmetic-withheld"]')).not.toBeNull();
    }
  });
});

describe('a tampered bundle shows no arithmetic at all', () => {
  it('refuses to render when a frame’s bytes disagree with the manifest', async () => {
    const files = new Map(bundleFiles());
    const original = files.get(SILENCE_FRAME);
    expect(original).toBeDefined();
    files.set(SILENCE_FRAME, new TextEncoder().encode(`${new TextDecoder().decode(original)} `));

    render(mount(bundleTransport(files)));
    await waitFor(() => {
      expect(screen.getByTestId('silence-failed')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('entry-list')).toBeNull();
    expect(screen.queryByTestId('conservation-panel')).toBeNull();
  });
});
