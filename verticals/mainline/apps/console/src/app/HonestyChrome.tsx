// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The honesty chrome (D16) — a permanent, non-dismissible strip.
 *
 * There is no close button, no collapse affordance and no `aria-hidden` path. Every
 * surface in this console renders beneath it, and ui.md §7 makes that structural: there
 * is no screen reachable without it. It is also the first five seconds of the demo
 * video, which is the reason it is at the top rather than in a footer.
 *
 * Each cell renders one fact plus a PROVENANCE marker saying how the console came to
 * believe it (D5): `db:column`, `db:constraint`, `recomputed`, `staged`, or `unset`.
 * A cell nobody filled reads "unknown / unset". That is the honest rendering of an
 * empty slot and it is deliberately the ugliest state on the screen.
 */

import { type ReactNode } from 'react';

import { CAPABILITY } from './capability';
import { useHonesty, type SealState, type TransportMode } from './honesty';
import styles from './chrome.module.css';

type Provenance = 'db:column' | 'db:constraint' | 'recomputed' | 'staged' | 'build' | 'unset';

function Cell({
  label,
  value,
  provenance,
  title,
  tone,
}: {
  readonly label: string;
  readonly value: string;
  readonly provenance: Provenance;
  readonly title?: string;
  readonly tone?: 'neutral' | 'warn' | 'refuse' | 'ok';
}): ReactNode {
  return (
    <div
      className={styles.cell}
      data-tone={tone ?? 'neutral'}
      data-provenance={provenance}
      {...(title === undefined ? {} : { title })}
    >
      <span className={styles.label}>{label}</span>
      <span className={styles.value} data-testid={`chrome-${label.replace(/\s+/g, '-')}`}>
        {value}
      </span>
      <span className={styles.provenance} aria-label={`provenance: ${provenance}`}>
        {provenance}
      </span>
    </div>
  );
}

function transportLabel(mode: TransportMode): { value: string; tone: 'neutral' | 'warn' } {
  if (mode === 'live') return { value: 'LIVE', tone: 'neutral' };
  if (mode === 'replay') return { value: 'REPLAY', tone: 'warn' };
  return { value: 'UNKNOWN', tone: 'warn' };
}

function sealLabel(seal: SealState): {
  value: string;
  tone: 'neutral' | 'warn' | 'refuse' | 'ok';
} {
  switch (seal) {
    case 'verified':
      return { value: 'VERIFIED IN THIS BROWSER', tone: 'ok' };
    case 'failed':
      return { value: 'VERIFICATION FAILED', tone: 'refuse' };
    case 'verifying':
      return { value: 'verifying…', tone: 'neutral' };
    case 'unverified':
    default:
      // Not "pending", not "—". Nothing has been checked, and the reader is told that
      // in the same words they would use to complain about it.
      return { value: 'NOT VERIFIED', tone: 'warn' };
  }
}

function skewLabel(ms: number | null): string {
  if (ms === null) return 'unknown';
  const sign = ms >= 0 ? '+' : '−';
  return `${sign}${Math.abs(ms)} ms`;
}

export function HonestyChrome(): ReactNode {
  const honesty = useHonesty();
  const transport = transportLabel(honesty.transport);
  const seal = sealLabel(honesty.seal);

  return (
    <aside className={styles.chrome} aria-label="Honesty chrome" data-testid="honesty-chrome">
      <div className={styles.row}>
        <Cell
          label="transport"
          value={transport.value}
          tone={transport.tone}
          provenance={honesty.transport === 'unknown' ? 'unset' : 'staged'}
          title={
            honesty.transport === 'replay'
              ? 'These bytes came from a signed EvidenceBundle captured from a real run, and were verified before being rendered.'
              : honesty.transport === 'live'
                ? 'These bytes came from a live kernel over the wire.'
                : 'No transport has declared itself. Nothing on screen has a stated origin.'
          }
        />
        <Cell
          label="bundle"
          value={honesty.bundleDigestPrefix ?? 'unknown'}
          provenance={honesty.bundleDigestPrefix === null ? 'unset' : 'recomputed'}
          title="First 12 hex characters of the SHA-256 over the bundle manifest, recomputed in this browser."
        />
        <Cell
          label="seal"
          value={seal.value}
          tone={seal.tone}
          provenance={honesty.seal === 'unverified' ? 'unset' : 'recomputed'}
          {...(honesty.sealDetail === null ? {} : { title: honesty.sealDetail })}
        />
        <Cell
          label="corpus root"
          value={honesty.corpusRoot ?? 'unknown'}
          provenance={honesty.corpusRoot === null ? 'unset' : 'db:column'}
          title="The commit the displayed blame closure was computed against."
        />
        <Cell
          label="clock skew"
          value={skewLabel(honesty.clockSkewMs)}
          provenance={honesty.clockSkewMs === null ? 'unset' : 'recomputed'}
          title="Server instant minus this browser's instant. A screenshot's timestamp means nothing without it."
        />
        <Cell
          label="signature path"
          value={honesty.signaturePath}
          tone={honesty.signaturePath === 'unknown' ? 'warn' : 'neutral'}
          provenance={honesty.signaturePath === 'unknown' ? 'unset' : 'build'}
          title="Compiled at build time from the GT-15 attestation. WebAuthn is not assumed; if no attestation existed, this says so."
        />
        <Cell
          label="render"
          value={CAPABILITY.renderMode === '3d' ? 'walk (3D)' : 'ribbon (2D)'}
          provenance="build"
          title={CAPABILITY.reasons.join(' ')}
        />
        <Cell label="build" value={honesty.buildId} provenance="build" />
      </div>
      {honesty.sealDetail !== null && (
        <p className={styles.detail} data-testid="honesty-seal-detail">
          {honesty.sealDetail}
        </p>
      )}
    </aside>
  );
}
