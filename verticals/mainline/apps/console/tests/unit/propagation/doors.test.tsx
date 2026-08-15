// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * ONE CLICK OUT OF A NAMED ABSENCE — and never a link to a subject nobody named.
 *
 * `PropagationSurfaceRoot` renders ONE lesson and refuses to choose one. That rule is not
 * under test and is not being relaxed; the dead end underneath it is. When the kernel's
 * subject index named a permit, a site or a clause version, each becomes an addressed link
 * built out of that same answer — and when it named nothing, nothing is offered.
 *
 * The propagation payload itself is STAGED, and no door out of this screen presents it as
 * anything else: every destination below is a screen reading a payload of its own. The
 * reverse direction — the door INTO propagation, offered by the silence screen — carries the
 * STAGED label with it, and `tests/unit/silence/doors.test.tsx` asserts that.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { DemoSubjects, SubjectIndex } from '../../../src/data/demo-subjects';
import { SubjectDoors } from '../../../src/features/propagation/SubjectDoors';

const PERMIT = 'de305d54-75b4-431b-adb2-eb6b9e546014';
const SITE = 'f81d4fae-7dec-11d0-a765-00a0c91e6bf6';
const CLAUSE = '6ba7b810-9dad-11d1-80b4-00c04fd430c8';
const COMMIT = '9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39';

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

describe('the doors out of a propagation screen with no lesson', () => {
  it('links the permit the kernel named, at both screens that render one', () => {
    render(<SubjectDoors index={resolved({ permitId: PERMIT })} />);

    const doors = screen.getByTestId('propagation-subject-doors');
    const hrefs = [...doors.querySelectorAll('a')].map((anchor) => anchor.getAttribute('href'));

    expect(hrefs).toContain(`#/gate?permit=${PERMIT}`);
    expect(hrefs).toContain(`#/silence?permit=${PERMIT}`);
    expect(doors).toHaveTextContent(`permit=${PERMIT}`);
  });

  it('links the site and the clause version when the index named those too', () => {
    render(
      <SubjectDoors index={resolved({ siteCode: SITE, clauseUuid: CLAUSE, commitId: COMMIT })} />,
    );

    const hrefs = [...screen.getByTestId('propagation-subject-doors').querySelectorAll('a')].map(
      (anchor) => anchor.getAttribute('href'),
    );
    expect(hrefs).toContain(`#/custody?site=${SITE}`);
    expect(hrefs).toContain(`#/diff?clause=${CLAUSE}&commit=${COMMIT}`);
  });

  it('offers no door for a slot the index left null, and none for its own subject', () => {
    render(<SubjectDoors index={resolved({ permitId: PERMIT })} />);
    const doors = screen.getByTestId('propagation-subject-doors');

    expect(doors.querySelector('[data-door="custody"]')).toBeNull();
    expect(doors.querySelector('[data-door="diff"]')).toBeNull();
    // The lesson is the subject THIS screen needs; no door here can ever supply one.
    expect(doors.querySelector('[data-door="lesson"]')).toBeNull();
  });

  it('renders nothing when the index did not resolve or named nothing', () => {
    for (const index of [
      { status: 'no_source' } as const,
      { status: 'unavailable', failure: 'status', detail: 'HTTP 404' } as const,
      resolved({}),
    ]) {
      const { container, unmount } = render(<SubjectDoors index={index} />);
      expect(container).toBeEmptyDOMElement();
      unmount();
    }
  });
});
