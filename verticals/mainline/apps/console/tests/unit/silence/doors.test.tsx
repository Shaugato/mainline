// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * ONE CLICK OUT OF A NAMED ABSENCE — and never a link to a subject nobody named.
 *
 * `SilenceSurfaceRoot` renders ONE permit and refuses to choose one. That rule is not under
 * test here and is not being relaxed: what is under test is the dead end underneath it. A
 * judge who arrives at `#/silence` with nothing addressed was told, accurately, that an
 * explicit identifier would work — and then had to produce a UUID from somewhere.
 *
 * `SubjectDoors` turns whatever the kernel's own subject index DID name into addressed
 * links. The two claims that matter are opposite in sign and both are asserted below:
 *
 *   • a slot the index filled becomes an `<a href>` carrying that identifier, so nobody
 *     types one; and
 *   • a slot the index left null, an index that did not resolve, and an index that named
 *     nothing at all produce NO link — not a dead one, not a placeholder, and not a guess.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { DemoSubjects, SubjectIndex } from '../../../src/data/demo-subjects';
import { SubjectDoors } from '../../../src/features/silence/SubjectDoors';

const SITE = 'f81d4fae-7dec-11d0-a765-00a0c91e6bf6';
const CLAUSE = '6ba7b810-9dad-11d1-80b4-00c04fd430c8';
const COMMIT = '9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39';
const LESSON = '6ba7b811-9dad-11d1-80b4-00c04fd430c8';

function subjects(over: Partial<DemoSubjects>): DemoSubjects {
  return {
    permitId: null,
    crId: null,
    checkId: null,
    receiptId: null,
    clauseUuid: null,
    commitId: null,
    runId: null,
    lessonId: null,
    siteCode: null,
    siteId: null,
    absent: [],
    ...over,
  };
}

function resolved(over: Partial<DemoSubjects>): SubjectIndex {
  return { status: 'resolved', subjects: subjects(over) };
}

describe('the doors out of a silence screen with no permit', () => {
  it('links every subject the kernel named, carrying the identifier it named', () => {
    render(
      <SubjectDoors
        index={resolved({ siteCode: SITE, clauseUuid: CLAUSE, commitId: COMMIT, lessonId: LESSON })}
      />,
    );

    const doors = screen.getByTestId('silence-subject-doors');
    const hrefs = [...doors.querySelectorAll('a')].map((anchor) => anchor.getAttribute('href'));

    expect(hrefs).toContain(`#/custody?site=${SITE}`);
    expect(hrefs).toContain(`#/propagation?lesson=${LESSON}`);
    expect(hrefs).toContain(`#/diff?clause=${CLAUSE}&commit=${COMMIT}`);
  });

  it('shows the identifier beside the link, so a reader can see what they are opening', () => {
    render(<SubjectDoors index={resolved({ lessonId: LESSON })} />);
    expect(screen.getByTestId('silence-subject-doors')).toHaveTextContent(`lesson=${LESSON}`);
  });

  it('carries the STAGED label into the propagation door, rather than dropping it at the link', () => {
    render(<SubjectDoors index={resolved({ lessonId: LESSON })} />);
    const door = screen.getByTestId('silence-subject-doors').querySelector('[data-door="propagation"]');
    expect(door?.textContent ?? '').toContain('STAGED');
  });

  it('offers NO door for a slot the index left null', () => {
    render(<SubjectDoors index={resolved({ lessonId: LESSON })} />);
    const doors = screen.getByTestId('silence-subject-doors');

    expect(doors.querySelector('[data-door="propagation"]')).not.toBeNull();
    expect(doors.querySelector('[data-door="custody"]')).toBeNull();
    expect(doors.querySelector('[data-door="diff"]')).toBeNull();
    // The permit is the subject THIS screen needs, and no door here can ever supply one.
    expect(doors.querySelector('[data-door="gate"]')).toBeNull();
  });

  it('offers no half-addressed diff door when the index named a clause and no commit', () => {
    render(<SubjectDoors index={resolved({ clauseUuid: CLAUSE, siteCode: SITE })} />);
    const doors = screen.getByTestId('silence-subject-doors');

    expect(doors.querySelector('[data-door="diff"]')).toBeNull();
    expect(doors.querySelector('[data-door="custody"]')).not.toBeNull();
  });

  it('renders nothing when the index did not resolve', () => {
    for (const index of [
      { status: 'no_source' } as const,
      { status: 'resolving' } as const,
      { status: 'unavailable', failure: 'status', detail: 'HTTP 404' } as const,
    ]) {
      const { container, unmount } = render(<SubjectDoors index={index} />);
      expect(container).toBeEmptyDOMElement();
      unmount();
    }
  });

  it('renders nothing when the index resolved and named nothing', () => {
    const { container } = render(<SubjectDoors index={resolved({})} />);
    expect(container).toBeEmptyDOMElement();
  });
});
