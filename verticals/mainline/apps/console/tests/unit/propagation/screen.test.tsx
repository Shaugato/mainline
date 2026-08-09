// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The fleet surface, end to end through the real replay transport.
 *
 * Every expected string is read out of the fixture bundle at run time, and the last block
 * re-seals a MUTATED bundle and requires the screen to follow it. A console that hardcoded
 * a site code and a test that hardcoded the one it expected would both pass a naive suite
 * and neither would assert anything.
 *
 * The claim this file exists to defend is the product claim on this surface: **a
 * declination is rendered with equal prominence to an adoption**. It is asserted three
 * ways, because one way is a rendering detail and three ways is a property:
 *
 *   1. both rows carry `data-prominence="equal"`;
 *   2. both rows carry the SAME `class` attribute — there is no muted variant to apply;
 *   3. the declined row renders MORE, not less: its kind, the constraint that makes the
 *      kind falsifiable, and the predicate that constraint requires.
 *
 * The browser spec adds the fourth way — computed font size, weight and opacity — because
 * a later stylesheet edit could break the claim without touching a component.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { type ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { HonestyProvider } from '../../../src/app/HonestyProvider';
import { PropagationSurfaceRoot } from '../../../src/features/propagation/PropagationSurfaceRoot';
import { PropagationTransportContext } from '../../../src/features/propagation/transport-context';
import type { MainlineTransport } from '../../../src/data/transport';
import type { Propagation } from '../../../src/data/types.generated';

import {
  bundleFiles,
  bundleTransport,
  frameEnvelope,
  lessonId,
  mutateFrame,
  propagationFramePath,
  sourcePropagation,
} from './_fixture';

const LESSON = lessonId();
const FRAME = propagationFramePath();
const PAYLOAD = sourcePropagation();

/** The two rows the equal-prominence claim is about, READ FROM THE FIXTURE. */
const ADOPTED: Propagation | undefined = PAYLOAD.data.propagations.find(
  (row) => row.state === 'adopted',
);
const DECLINED: Propagation | undefined = PAYLOAD.data.propagations.find(
  (row) => row.state === 'declined',
);

function mount(transport: MainlineTransport | null): ReactNode {
  window.location.hash = `#/propagation?lesson=${LESSON}`;
  return (
    <HonestyProvider>
      <PropagationTransportContext.Provider value={transport}>
        <PropagationSurfaceRoot />
      </PropagationTransportContext.Provider>
    </HonestyProvider>
  );
}

async function renderReady(files: ReadonlyMap<string, Uint8Array>): Promise<void> {
  render(mount(bundleTransport(files)));
  await waitFor(() => {
    expect(screen.getByTestId('site-list')).toBeInTheDocument();
  });
}

function rowFor(site: string): HTMLElement {
  const found = screen
    .getAllByTestId('site-row')
    .find((element) => element.getAttribute('data-site') === site);
  if (found === undefined) {
    throw new Error(
      `no site row for ${site}. Present: ${screen
        .getAllByTestId('site-row')
        .map((element) => element.getAttribute('data-site'))
        .join(', ')}`,
    );
  }
  return found;
}

describe('the fixture this suite reads is the one it thinks it reads', () => {
  it('has an adopted row and a declined row with a declination kind', () => {
    expect(ADOPTED).toBeDefined();
    expect(DECLINED).toBeDefined();
    expect(DECLINED?.declination_kind).toBeTruthy();
    expect(frameEnvelope(bundleFiles(), FRAME).data.lesson.lesson_id).toBe(LESSON);
  });
});

describe('no transport, no claim', () => {
  it('says NO SOURCE rather than painting an empty fleet', () => {
    render(mount(null));
    const panel = screen.getByTestId('propagation-no-source');
    expect(panel).toHaveTextContent('No transport was provided');
    expect(screen.queryByTestId('site-list')).toBeNull();
  });
});

describe('the fleet', () => {
  it('renders every site the payload carries', async () => {
    await renderReady(bundleFiles());
    expect(screen.getAllByTestId('site-row')).toHaveLength(PAYLOAD.data.propagations.length);
  });

  it('EQUAL PROMINENCE — the declined row is built exactly like the adopted one', async () => {
    await renderReady(bundleFiles());

    const adopted = rowFor(ADOPTED?.site_code ?? '');
    const declined = rowFor(DECLINED?.site_code ?? '');

    expect(adopted).toHaveAttribute('data-prominence', 'equal');
    expect(declined).toHaveAttribute('data-prominence', 'equal');

    // The same class attribute, character for character. There is no muted variant in the
    // stylesheet to apply, and this is the assertion that goes red if one is ever added.
    expect(declined.getAttribute('class')).toBe(adopted.getAttribute('class'));

    // Both rows carry the same blocks: the state, the clock, the appraisal, what the site
    // did. A declination that collapsed one of them would be a quieter row.
    for (const row of [adopted, declined]) {
      expect(row.querySelector('[data-testid="site-state"]')).not.toBeNull();
      expect(row.querySelector('[data-testid="site-due"]')).not.toBeNull();
      expect(row.querySelector('[data-testid="site-score"]')).not.toBeNull();
    }
  });

  it('the declined row carries its kind, its governing constraint and its predicate', async () => {
    await renderReady(bundleFiles());
    const declined = rowFor(DECLINED?.site_code ?? '');

    const declination = declined.querySelector('[data-testid="site-declination"]');
    expect(declination).not.toBeNull();
    expect(declination).toHaveAttribute('data-declination-kind', DECLINED?.declination_kind ?? '');
    expect(declined.querySelector('[data-testid="site-declination-kind"]')).toHaveTextContent(
      DECLINED?.declination_kind ?? '',
    );

    // `mechanism_absent` without a machine-checkable predicate is not a representable row —
    // so the predicate is on screen, verbatim, from the fixture.
    const predicate = DECLINED?.declination_predicate_id ?? null;
    if (predicate !== null) {
      expect(declined.querySelector('[data-testid="site-declination-predicate"]')).toHaveTextContent(
        predicate,
      );
    }
    expect(
      declined.querySelector('[data-testid="site-declination-constraint"]'),
    ).not.toBeNull();
  });

  it('renders the SLA clock as an instant plus its reference, never as a countdown', async () => {
    await renderReady(bundleFiles());
    const declined = rowFor(DECLINED?.site_code ?? '');
    const due = declined.querySelector('[data-testid="site-due"]');
    expect(due).toHaveTextContent(DECLINED?.due_by ?? '');
    // The reference instant is on screen beside the interval: an SLA measured against an
    // unnamed clock is a claim about somebody's laptop.
    expect(due).toHaveTextContent(PAYLOAD.observed_at ?? '');
  });

  it('renders the appraisal score beside the model version that produced it', async () => {
    await renderReady(bundleFiles());
    const adopted = rowFor(ADOPTED?.site_code ?? '');
    expect(adopted.querySelector('[data-testid="site-score"]')).toHaveTextContent(
      String(ADOPTED?.score ?? ''),
    );
    expect(adopted.querySelector('[data-testid="site-model-version"]')).toHaveTextContent(
      ADOPTED?.model_version ?? '',
    );
  });
});

describe('only_tightenings_travel is a stated law, not a filter', () => {
  it('renders the constraint name and both excluded control_delta values', async () => {
    await renderReady(bundleFiles());
    expect(screen.getByTestId('tightenings-constraint')).toHaveTextContent(
      'only_tightenings_travel',
    );

    const terms = screen.getByTestId('tightenings-terms');
    for (const admitted of ['introduce', 'strengthen', 'restate']) {
      expect(terms.querySelector(`[data-term="${admitted}"]`)).toHaveAttribute(
        'data-admitted',
        'true',
      );
    }
    for (const excluded of ['weaken', 'remove']) {
      expect(terms.querySelector(`[data-term="${excluded}"]`)).toHaveAttribute(
        'data-admitted',
        'false',
      );
    }
  });

  it('says nothing is being filtered — there is nothing to filter', async () => {
    await renderReady(bundleFiles());
    expect(screen.getByTestId('tightenings-law')).toHaveTextContent('not a representable row');
    // No control that offers to widen the set. A "show weakenings" toggle would advertise
    // a state the database cannot hold.
    expect(screen.queryByRole('checkbox')).toBeNull();
  });
});

describe('conflicts and resolution memory', () => {
  it('renders base, ours and theirs for every conflict', async () => {
    await renderReady(bundleFiles());
    const conflicts = screen.getAllByTestId('conflict');
    expect(conflicts).toHaveLength(PAYLOAD.data.conflicts.length);

    const first = PAYLOAD.data.conflicts[0];
    if (first !== undefined) {
      const rendered = conflicts.find(
        (element) => element.getAttribute('data-conflict') === first.conflict_id,
      );
      expect(rendered?.querySelector('[data-testid="conflict-base"]')).toHaveTextContent(
        first.base_digest,
      );
      expect(rendered?.querySelector('[data-testid="conflict-ours"]')).toHaveTextContent(
        first.ours_digest,
      );
      expect(rendered?.querySelector('[data-testid="conflict-theirs"]')).toHaveTextContent(
        first.theirs_digest,
      );
    }
  });

  it('ships no control that applies a recorded resolution', async () => {
    await renderReady(bundleFiles());
    // Auto-applying a safety-text resolution is the rubber-stamp accelerant this design
    // refuses to build, and the reliable way not to build it is to ship no button.
    expect(screen.queryAllByRole('button', { name: /apply|resolve|accept/i })).toEqual([]);
  });

  it('names the column it cannot show rather than implying a recall flag', async () => {
    await renderReady(bundleFiles());
    expect(screen.getByTestId('inheritance-limit')).toHaveTextContent('recalled_at');
    expect(screen.getByTestId('inheritance-limit')).toHaveTextContent('not carried');
  });
});

describe('nothing is hardcoded', () => {
  it('renders whatever declination kind the re-sealed bundle carries', async () => {
    const site = DECLINED?.site_code ?? '';
    const replacement = DECLINED?.declination_kind === 'waiver' ? 'mitigated' : 'waiver';

    const files = await mutateFrame(bundleFiles(), FRAME, (envelope) => {
      const data = envelope.data as { propagations: Record<string, unknown>[] };
      for (const row of data.propagations) {
        if (row.site_code !== site) continue;
        row.declination_kind = replacement;
        // `waiver_expires` requires an expiry, and the CONTRACT enforces it — a mutation
        // that broke the schema would be refused by the transport, which is the transport
        // working rather than a test being clever.
        row.declination_expires_at = '2026-12-31T00:00:00.000Z';
      }
    });

    await renderReady(files);
    const declined = rowFor(site);
    expect(declined.querySelector('[data-testid="site-declination"]')).toHaveAttribute(
      'data-declination-kind',
      replacement,
    );
    expect(declined.querySelector('[data-testid="site-declination-kind"]')).toHaveTextContent(
      replacement,
    );
  });

  it('renders whatever state the re-sealed bundle carries, with the same prominence', async () => {
    const site = ADOPTED?.site_code ?? '';
    const files = await mutateFrame(bundleFiles(), FRAME, (envelope) => {
      const data = envelope.data as { propagations: Record<string, unknown>[] };
      for (const row of data.propagations) {
        if (row.site_code !== site) continue;
        row.state = 'revoked';
        // `adopt_needs_commit` only binds the adopted state; a revoked row may carry none.
        row.adopted_commit = null;
      }
    });

    await renderReady(files);
    const changed = rowFor(site);
    expect(changed).toHaveAttribute('data-state', 'revoked');
    expect(changed).toHaveAttribute('data-prominence', 'equal');
    expect(changed.querySelector('[data-testid="site-state"]')).toHaveTextContent('revoked');
  });
});

describe('a tampered bundle shows no rows at all', () => {
  it('refuses to render when a frame’s bytes disagree with the manifest', async () => {
    const files = new Map(bundleFiles());
    const original = files.get(FRAME);
    expect(original).toBeDefined();
    // Rewritten WITHOUT re-sealing: the digest no longer matches the manifest.
    files.set(FRAME, new TextEncoder().encode(`${new TextDecoder().decode(original)} `));

    render(mount(bundleTransport(files)));
    await waitFor(() => {
      expect(screen.getByTestId('propagation-failed')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('site-list')).toBeNull();
  });
});
