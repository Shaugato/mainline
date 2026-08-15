// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ON-RAMP, HELD TO THE RULING THAT PUT IT THERE.
 *
 * `docs/leads/two-audience-ux-plan.md` R6 makes two promises about this screen, and both
 * fail silently if nobody asserts them.
 *
 *   1. **COLLAPSED IS NOT REMOVED.** `src/a11y/contract.ts` promises a reader can "read
 *      every declared file with its expected digest and its recomputed digest, as
 *      selectable text". A worker who shortens the screen by rendering the inventory
 *      conditionally breaks that promise and leaves a page that looks identical on arrival.
 *      So every assertion here reaches INSIDE a shut `<details>` and demands the bytes.
 *   2. **SOME THINGS MAY NEVER COLLAPSE.** The seal, the findings, the coverage arithmetic,
 *      the "what a clean audit does not establish" section, and the not-established
 *      sentence. Tidying any one of those behind a click would turn this screen from an
 *      audit into a summary of an audit, which is the failure mode it exists to refuse.
 *
 * A third property, and the one the founder actually asked for: a lay reader must be told
 * which of the several possible nothings they are looking at. `unlisted === null` renders
 * as **not established**, and the sentence beside it must say, in ordinary words, that this
 * is not the same as "none".
 */

import { render, screen, waitFor } from '@testing-library/react';
import { type ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { HonestyProvider } from '../../../src/app/HonestyProvider';
import { contractRegistry } from '../../../src/data/contracts';
import { EvidenceScreen } from '../../../src/features/evidence/EvidenceScreen';
import { resolveDigestOracle, type DigestOracle } from '../../../src/features/evidence/digest';

import { bundleFiles, ListableMemorySource, OpaqueMemorySource } from './_fixture';

const ORACLE: DigestOracle = (() => {
  const resolved = resolveDigestOracle();
  if (!resolved.ok) throw new Error(`no digest oracle in this test environment: ${resolved.reason}`);
  return resolved.oracle;
})();

const CLOCK = (): string => '2026-08-15T00:00:00.000Z';

function view(source: OpaqueMemorySource | ListableMemorySource): ReactNode {
  return (
    <HonestyProvider>
      <EvidenceScreen
        source={source}
        oracle={ORACLE}
        registry={contractRegistry()}
        clock={CLOCK}
        params={new URLSearchParams()}
        env={{}}
        transport="unknown"
      />
    </HonestyProvider>
  );
}

/** The nearest enclosing `<details>`, or null when the node is in the open flow. */
function enclosingDetails(node: Element): HTMLDetailsElement | null {
  return node.closest('details');
}

async function settled(): Promise<void> {
  await waitFor(() => {
    expect(screen.getByTestId('evidence-coverage')).toBeTruthy();
  });
}

describe('the screen opens in plain language', () => {
  it('says what a bundle is before it says what SHA-256 it got', async () => {
    render(view(new OpaqueMemorySource('test:fixtures/bundles/blk-07', bundleFiles())));
    const band = screen.getByTestId('evidence-plain-band');
    expect(band.textContent ?? '').toContain('a capture of a past session');
    expect(enclosingDetails(band)).toBeNull();

    // The precise standfirst is UNTOUCHED and still on the screen. The on-ramp is a band
    // above it, never a replacement for it (R6).
    expect(screen.getByTestId('evidence-screen').textContent ?? '').toContain(
      'recomputed each one’s SHA-256',
    );
    await settled();
  });

  it('claims no signature, because this screen checks none', () => {
    render(view(new OpaqueMemorySource('test:fixtures/bundles/blk-07', bundleFiles())));
    const band = (screen.getByTestId('evidence-plain-band').textContent ?? '').toLowerCase();
    // `.env.demo` ships an empty VITE_MAINLINE_LOG_VKEY and no signature is verified here.
    // A plain sentence is not a place to acquire a claim the machinery does not make.
    for (const word of ['signed', 'signature', 'tamper-proof', 'guaranteed']) {
      expect(band.includes(word), `the plain band claims "${word}"`).toBe(false);
    }
  });
});

describe('collapsed is not removed', () => {
  it('keeps every declared and recomputed digest in the DOM while the inventory is shut', async () => {
    render(view(new OpaqueMemorySource('test:fixtures/bundles/blk-07', bundleFiles())));
    await settled();

    const disclosure: HTMLDetailsElement = screen.getByTestId('evidence-inventory-disclosure');
    expect(disclosure.open, 'the inventory starts open, so nothing was collapsed').toBe(false);

    const inventory = screen.getByTestId('evidence-inventory');
    expect(enclosingDetails(inventory)).toBe(disclosure);
    expect(inventory.querySelectorAll('tbody tr').length).toBeGreaterThan(3);
    expect(inventory.textContent ?? '').toContain('manifest.json');

    // The manifest's own digest is one click away and still complete: 64 hex characters,
    // not a prefix. A collapsed exhibit that truncated would be a removed exhibit.
    const digest = screen.getByTestId('evidence-manifest-digest');
    expect(/[0-9a-f]{64}/.test(digest.textContent ?? '')).toBe(true);
    expect(enclosingDetails(digest)).not.toBeNull();
  });

  it('gives every disclosure a summary that names what is behind it', async () => {
    const { container } = render(
      view(new OpaqueMemorySource('test:fixtures/bundles/blk-07', bundleFiles())),
    );
    await settled();
    const summaries = [...container.querySelectorAll('summary')];
    expect(summaries.length).toBeGreaterThanOrEqual(2);
    for (const summary of summaries) {
      const label = (summary.textContent ?? '').trim();
      expect(label.length, 'an unlabelled disclosure').toBeGreaterThan(12);
      expect(/^(details|more|show more|advanced)$/i.test(label), `bare label "${label}"`).toBe(
        false,
      );
    }
  });
});

describe('what may never be collapsed', () => {
  it('leaves the seal, the coverage arithmetic and the limits in the open flow', async () => {
    render(view(new OpaqueMemorySource('test:fixtures/bundles/blk-07', bundleFiles())));
    await settled();

    expect(enclosingDetails(screen.getByTestId('evidence-seal')), 'the seal is behind a click')
      .toBeNull();
    expect(enclosingDetails(screen.getByTestId('evidence-coverage'))).toBeNull();
    expect(enclosingDetails(screen.getByTestId('evidence-conservation'))).toBeNull();
    expect(enclosingDetails(screen.getByTestId('evidence-transport-note'))).toBeNull();
    expect(screen.getByTestId('evidence-screen').textContent ?? '').toContain(
      'What a clean audit does not establish',
    );
  });
});

describe('which nothing this is', () => {
  it('tells a lay reader that “not established” is not “none”', async () => {
    render(view(new OpaqueMemorySource('test:fixtures/bundles/blk-07', bundleFiles())));
    await settled();

    // A static host answers for a file you name and will not list its directory, so the
    // no-smuggled-file claim cannot be made at all.
    expect(screen.getByTestId('evidence-unlisted').textContent ?? '').toContain('not established');

    const note = screen.getByTestId('evidence-not-established-note');
    expect(enclosingDetails(note), 'the distinction is behind a click').toBeNull();
    const text = note.textContent ?? '';
    expect(text).toContain('the check ran and came back empty');
    expect(text).toContain('nobody looked');
  });

  it('says “none” only when the source really did enumerate itself', async () => {
    render(view(new ListableMemorySource('test:fixtures/bundles/blk-07', bundleFiles())));
    await settled();

    const unlisted = screen.getByTestId('evidence-unlisted').textContent ?? '';
    expect(unlisted).toContain('none.');
    expect(unlisted).not.toContain('not established');
    // The explanation stays on screen either way: a reader who arrives at the reassuring
    // branch must still be able to read what the other branch would have meant.
    expect(screen.getByTestId('evidence-not-established-note')).toBeTruthy();
  });
});
