// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The screen's honesty properties.
 *
 * Each assertion here is written so that the COMFORTABLE failure is red: a seal that
 * appears before any arithmetic, a caveat panel quietly deleted, a tampered bundle
 * rendered with an apologetic note instead of a refusal, a "not established" quietly
 * rounded down to "none".
 *
 * The screen is driven with an explicit source, oracle and clock, so nothing here
 * depends on the page's address, on the build environment, or on the wall clock.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { type ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { HonestyProvider } from '../../../src/app/HonestyProvider';
import { useHonesty } from '../../../src/app/honesty';
import type { BundleSource } from '../../../src/data/bundle';
import { contractRegistry } from '../../../src/data/contracts';
import { EvidenceScreen } from '../../../src/features/evidence/EvidenceScreen';
import { resolveDigestOracle, type DigestOracle } from '../../../src/features/evidence/digest';

import {
  FIXTURE_MANIFEST_SHA256,
  frameAddressOf,
  FIXTURE_PERMIT_ID,
  OpaqueMemorySource,
  bundleFiles,
  editManifest,
  flipDeclaredDigest,
} from './_fixture';

const ORACLE: DigestOracle = (() => {
  const resolved = resolveDigestOracle();
  if (!resolved.ok) throw new Error(`no digest oracle in this test environment: ${resolved.reason}`);
  return resolved.oracle;
})();

const CLOCK = (): string => '2026-08-04T00:00:00.000Z';
const PERMIT_FRAME = frameAddressOf(`GET /v1/permits/${FIXTURE_PERMIT_ID}`);

function mount(node: ReactNode): ReturnType<typeof render> {
  return render(<HonestyProvider>{node}</HonestyProvider>);
}

function intact(): BundleSource {
  return new OpaqueMemorySource('test:fixtures/bundles/blk-07', bundleFiles());
}

function view(source: BundleSource | null, oracle: DigestOracle | null = ORACLE): ReactNode {
  return (
    <EvidenceScreen
      source={source}
      oracle={oracle}
      registry={contractRegistry()}
      clock={CLOCK}
      params={new URLSearchParams()}
      env={{}}
    />
  );
}

describe('no bundle, no claim', () => {
  it('names which of the several possible nothings this is', () => {
    mount(view(null));
    const card = screen.getByTestId('evidence-no-bundle');
    expect(card).toHaveTextContent('VITE_MAINLINE_BUNDLE_URL');
    expect(card).toHaveTextContent('a fact about this deployment');
    expect(screen.queryByTestId('evidence-inventory')).toBeNull();
  });
});

describe('a bundle and no way to hash it', () => {
  it('renders UNVERIFIED with the reason — never verified, and never failed', () => {
    // An insecure origin has not accused the bundle of anything. Rendering `failed`
    // here would be the console blaming the evidence for its own deployment.
    mount(view(intact(), null));
    const card = screen.getByTestId('evidence-no-oracle');
    expect(card).toHaveTextContent('no digest oracle was supplied');
    const seal = screen.getByTestId('evidence-seal');
    expect(seal).toHaveAttribute('data-state', 'unverified');
    expect(screen.queryByTestId('evidence-inventory')).toBeNull();
  });
});

describe('the intact bundle', () => {
  it('seals only after the arithmetic, and names the arithmetic', async () => {
    mount(view(intact()));
    const seal = await screen.findByTestId('evidence-seal');
    expect(seal).toHaveAttribute('data-state', 'verified');
    expect(seal).toHaveTextContent('SHA-256 over the sealed bytes (WebCrypto SHA-256)');
    expect(seal).toHaveTextContent('2026-08-04T00:00:00.000Z');
  });

  it('puts the whole recomputed manifest digest in the DOM', async () => {
    mount(view(intact()));
    const digest = await screen.findByTestId('evidence-manifest-digest');
    // The full 64 characters, not a prefix: a digest a reader cannot copy is decoration.
    expect(digest).toHaveTextContent(FIXTURE_MANIFEST_SHA256);
  });

  it('shows the conservation equation, balanced', async () => {
    mount(view(intact()));
    const equation = await screen.findByTestId('evidence-conservation');
    expect(equation).toHaveAttribute('data-conserved', 'true');
    expect(equation).toHaveTextContent('21 declared = 21 matched + 0 disagreed');
  });

  it('renders one inventory row per listed file, each with its declared digest', async () => {
    mount(view(intact()));
    const table = await screen.findByTestId('evidence-inventory');
    expect(table.querySelectorAll('tbody tr')).toHaveLength(21);
    const row = screen.getByTestId(`evidence-row:${PERMIT_FRAME}`);
    expect(row).toHaveAttribute('data-state', 'match');
    expect(row).toHaveTextContent('936cc69879616fca61b16f08d1c2fe3e6fe6fe7819ccfbe8895b04c037d79047');
    // A frame says what it serves, and who owes the endpoint.
    expect(row).toHaveTextContent(`GET /v1/permits/${FIXTURE_PERMIT_ID}`);
    expect(row).toHaveTextContent('permit · owed by kernel');
  });

  it('says "not established" about unlisted files rather than "none"', async () => {
    mount(view(intact()));
    const note = await screen.findByTestId('evidence-unlisted');
    expect(note).toHaveTextContent('not established');
    expect(note).not.toHaveTextContent('none.');
  });

  it('carries the staged note verbatim, because a staged bundle must say so', async () => {
    mount(view(intact()));
    const badge = await screen.findByTestId('evidence-staged');
    expect(badge).toHaveTextContent('Hand-authored demonstration bundle');
    expect(badge).toHaveTextContent('no number on it may be quoted as a measurement');
  });

  it('names the declared resources this bundle never captured, and the unowned one', async () => {
    mount(view(intact()));
    const gaps = await screen.findByTestId('evidence-gaps');
    expect(gaps.querySelectorAll('li')).toHaveLength(2);
    expect(gaps.querySelector('[data-resource="change_request"]')).not.toBeNull();
    expect(gaps.querySelector('[data-resource="suspend_permit"]')).not.toBeNull();
  });

  it('reports no finding, in words, rather than by showing an empty list', async () => {
    mount(view(intact()));
    expect(await screen.findByTestId('evidence-findings-none')).toHaveTextContent('No finding.');
  });

  it('always renders what a clean audit does NOT establish', async () => {
    mount(view(intact()));
    const limits = await screen.findByTestId('evidence-limits');
    expect(limits.querySelectorAll('li').length).toBeGreaterThanOrEqual(4);
    expect(limits).toHaveTextContent('provenance, not truth');
    expect(limits).toHaveTextContent('NOT verified on this screen');
  });
});

describe('the tampered bundle', () => {
  it('fails the seal and renders the finding verbatim, check name and all', async () => {
    mount(view(new OpaqueMemorySource('test:tampered', flipDeclaredDigest(bundleFiles(), PERMIT_FRAME))));

    const seal = await screen.findByTestId('evidence-seal');
    expect(seal).toHaveAttribute('data-state', 'failed');

    const findings = screen.getByTestId('evidence-findings');
    const finding = findings.querySelector('[data-check="manifest-digest"]');
    expect(finding, 'the digest mismatch was not rendered as a finding').not.toBeNull();
    expect(finding).toHaveTextContent(PERMIT_FRAME);
    expect(finding).toHaveTextContent('manifest declares sha256');

    const row = screen.getByTestId(`evidence-row:${PERMIT_FRAME}`);
    expect(row).toHaveAttribute('data-state', 'mismatch');
    expect(row).toHaveTextContent('MISMATCH');
    // Every other row still reads `match`: the refusal is targeted, so a reader learns
    // WHICH file moved rather than only that something did.
    expect(screen.getByTestId('evidence-conservation')).toHaveTextContent('20 matched + 1 disagreed');
  });
});

describe('a manifest the console cannot read', () => {
  it('shows the contract failure verbatim and says the transport refuses it too', async () => {
    const files = editManifest(bundleFiles(), (manifest) => {
      delete manifest.bundle_id;
    });
    mount(view(new OpaqueMemorySource('test:malformed', files)));
    const card = await screen.findByTestId('evidence-unusable');
    expect(card).toHaveTextContent('bundle.schema.json');
    expect(card).toHaveTextContent('transport refuses such a bundle');
    expect(screen.queryByTestId('evidence-inventory')).toBeNull();
  });
});

describe('what reaches the honesty chrome (D16)', () => {
  function Probe(): ReactNode {
    const honesty = useHonesty();
    return (
      <p data-testid="probe">
        {honesty.seal}|{honesty.bundleDigestPrefix ?? 'null'}|{honesty.sealDetail ?? 'null'}
      </p>
    );
  }

  it('publishes the seal, the digest prefix, and a detail naming what was checked', async () => {
    mount(
      <>
        {view(intact())}
        <Probe />
      </>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('probe')).toHaveTextContent(
        `verified|${FIXTURE_MANIFEST_SHA256.slice(0, 12)}|`,
      );
    });
    const probe = screen.getByTestId('probe');
    expect(probe).toHaveTextContent('manifest integrity only');
    // The chrome must not be able to imply the ledger verified. A later, stronger seal
    // from the custody verifier will read as a visibly different sentence.
    expect(probe).toHaveTextContent('The carried ledger is NOT verified by this check.');
  });

  it('publishes `failed` for a tampered bundle', async () => {
    mount(
      <>
        {view(new OpaqueMemorySource('t', flipDeclaredDigest(bundleFiles(), PERMIT_FRAME)))}
        <Probe />
      </>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('probe')).toHaveTextContent('failed|');
    });
  });

  it('publishes `unverified` — never `failed` — when there is no oracle', () => {
    mount(
      <>
        {view(intact(), null)}
        <Probe />
      </>,
    );
    expect(screen.getByTestId('probe')).toHaveTextContent('unverified|null|');
  });
});
