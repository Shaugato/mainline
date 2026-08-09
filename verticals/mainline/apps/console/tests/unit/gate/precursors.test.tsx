// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PRECURSOR LIST.
 *
 * Three claims, and the second is the one with a body count behind it:
 *
 *   1. every projected field — severity, virulence, closure generation, origin — and the
 *      reranker's `evidence_summary` are rendered verbatim from the payload;
 *   2. a precursor whose event carries an Object-Lock key AND a digest is marked as a
 *      re-verifiable VERBATIM anchor; one that carries neither is marked GIST, because
 *      gist may accuse and only verbatim may acquit (M11);
 *   3. what wrote the clause comes from the ancestry payload or is reported absent. The
 *      read model has no commit-message column, so the panel renders the introducing
 *      commit and the blame edge's attribution — and when no ancestry arrived it says
 *      the origin is not carried rather than composing a sentence.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PrecursorList } from '../../../src/features/gate/PrecursorList';
import type { AncestryData, BlockingChecksData } from '../../../src/features/gate/model';
import { sourcePayload } from './_support';

interface Envelope<T> {
  readonly provenance: readonly { readonly pointer: string; readonly chip: string }[];
  readonly data: T;
}

const checksEnvelope = sourcePayload<Envelope<BlockingChecksData>>('blocking-checks.json');
const ancestry = sourcePayload<Envelope<AncestryData>>('ancestry.json').data;
const checks = checksEnvelope.data.checks;
const provenance = checksEnvelope.provenance as never;
const none: ReadonlySet<string> = new Set();

function renderList(options?: {
  readonly rows?: typeof checks | null;
  readonly ancestry?: AncestryData | null;
  readonly named?: ReadonlySet<string>;
}): void {
  render(
    <PrecursorList
      checks={options?.rows === undefined ? checks : options.rows}
      provenance={provenance}
      ancestry={options?.ancestry === undefined ? ancestry : options.ancestry}
      namedByReasonSet={options?.named ?? none}
    />,
  );
}

describe('the materialised obligations', () => {
  it('renders one entry per check, addressable by its id', () => {
    renderList();
    const items = screen.getAllByTestId('precursor');
    expect(items).toHaveLength(checks.length);
    items.forEach((node, index) => {
      expect(node.dataset.checkId).toBe(checks[index]?.check_id);
      // The weld diagram links here; the anchor has to exist for the link to land.
      expect(node.id).toBe(`gate-check-${checks[index]?.check_id ?? ''}`);
    });
  });

  it('renders the projected severity, virulence, closure generation and origin verbatim', () => {
    renderList();
    const items = screen.getAllByTestId('precursor');
    items.forEach((node, index) => {
      const check = checks[index];
      if (check === undefined) throw new Error('fixture drift');
      expect(node.textContent).toContain(check.origin);
      expect(node.textContent).toContain(check.virulence);
      expect(node.textContent).toContain(String(check.severity));
      expect(node.textContent).toContain(String(check.closure_gen));
    });
  });

  it('renders the reranker’s evidence summary verbatim and never abridges it', () => {
    renderList();
    const summaries = screen
      .getAllByTestId('precursor-evidence-summary')
      .map((node) => node.textContent);
    expect(summaries).toEqual(checks.map((check) => check.evidence_summary));
  });

  it('marks the checks the reason set names', () => {
    const first = checks[0];
    if (first === undefined) throw new Error('fixture has no checks');
    renderList({ named: new Set([first.check_id]) });
    const marked = screen.getAllByTestId('precursor-named');
    expect(marked).toHaveLength(1);
  });

  it('distinguishes an open obligation from a dispositioned one', () => {
    renderList();
    const states = screen.getAllByTestId('precursor-state').map((node) => node.textContent);
    expect(states).toEqual(checks.map((check) => (check.open ? 'open' : 'dispositioned')));
  });
});

describe('M11 — gist may accuse, only verbatim may acquit', () => {
  it('marks a precursor with a source key and a digest as a re-verifiable anchor', () => {
    renderList();
    const items = screen.getAllByTestId('precursor');
    items.forEach((node, index) => {
      const precursor = checks[index]?.precursor ?? null;
      const anchored =
        precursor !== null &&
        typeof precursor.source_object_key === 'string' &&
        typeof precursor.source_sha256 === 'string';
      expect(node.dataset.anchor).toBe(anchored ? 'verbatim' : 'gist');
    });
  });

  it('says explicitly what an unanchored precursor may not be used to do', () => {
    renderList();
    const note = screen.getAllByTestId('precursor-gist-note')[0];
    expect(note?.textContent).toContain('may not clear one');
  });

  it('shows the Object-Lock pointer and digest for an anchored precursor', () => {
    renderList();
    const anchored = checks.find(
      (check) =>
        typeof check.precursor?.source_object_key === 'string' &&
        typeof check.precursor.source_sha256 === 'string',
    );
    if (anchored === undefined) throw new Error('fixture carries no anchored precursor');
    const node = screen.getByText(anchored.precursor?.source_object_key ?? '');
    expect(node).not.toBeNull();
  });
});

describe('what wrote the clause', () => {
  it('renders the introducing commit and the blame attribution from the ancestry payload', () => {
    renderList();
    const introducing = ancestry.commit_chain.find((link) => link.control_delta === 'introduce');
    if (introducing === undefined) throw new Error('fixture chain has no introducing commit');

    const commit = screen.getAllByTestId('origin-commit')[0];
    expect(commit?.textContent).toContain(introducing.commit_id);
    expect(commit?.textContent).toContain(introducing.committed_at);

    const attribution = screen.getAllByTestId('origin-attribution')[0];
    const expected = ancestry.blame_edges.find(
      (edge) => edge.event_id === checks[0]?.precursor_event_id,
    )?.attribution;
    expect(attribution?.textContent).toBe(expected);
  });

  it('says the origin is not carried when no ancestry payload arrived', () => {
    renderList({ ancestry: null });
    const absent = screen.getAllByTestId('origin-absent');
    expect(absent).toHaveLength(checks.length);
    expect(absent[0]?.textContent).toContain('not carried');
  });

  it('refuses to attribute one clause’s ancestry to another clause’s check', () => {
    const otherClause: AncestryData = { ...ancestry, clause_uuid: 'not-this-clause' };
    renderList({ ancestry: otherClause });
    expect(screen.getAllByTestId('origin-absent')).toHaveLength(checks.length);
  });
});

describe('absences', () => {
  it('separates "the read has not landed" from "there are none"', () => {
    renderList({ rows: null });
    expect(screen.getByTestId('precursors-unavailable').textContent).toContain(
      'not a claim that there are none',
    );
  });

  it('reports an empty list as the emitter asserting there are none', () => {
    renderList({ rows: [] });
    expect(screen.getByTestId('precursors-empty').textContent).toContain('asserting there are none');
  });
});
