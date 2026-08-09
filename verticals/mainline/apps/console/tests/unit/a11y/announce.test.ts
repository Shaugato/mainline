// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The announcer, and the one rule in it that is not ergonomics.
 *
 * `announceVerbatim()` refuses a string it would have to alter. The test that matters is
 * the third one: a constraint name with a trailing space is REFUSED rather than trimmed,
 * because trimming here would make speech output and the mono face disagree about what
 * the database emitted — a paraphrase performed by the accessibility layer, which is the
 * one place nobody would look for it (D18).
 */

import { afterEach, describe, expect, it } from 'vitest';

import { createAnnouncer, verbatimRefusal } from '../../../src/a11y/announce';
import { audit } from '../../../src/a11y/audit';

afterEach(() => {
  createAnnouncer(document).destroy();
});

describe('the regions', () => {
  it('creates one polite and one assertive region, both real text', () => {
    const announcer = createAnnouncer(document);
    announcer.announce('Six checks are open.');
    announcer.announce('Merge refused.', 'assertive');

    const polite = document.getElementById('mainline-live-polite');
    const assertive = document.getElementById('mainline-live-assertive');
    expect(polite?.getAttribute('role')).toBe('status');
    expect(polite?.getAttribute('aria-live')).toBe('polite');
    expect(assertive?.getAttribute('role')).toBe('alert');
    expect(assertive?.getAttribute('aria-live')).toBe('assertive');
    // aria-atomic, or a screen reader may announce only the diff — and for a constraint
    // name sharing a prefix with the previous one, the diff is a fragment nobody can act on.
    expect(assertive?.getAttribute('aria-atomic')).toBe('true');
    expect(announcer.read('polite')).toBe('Six checks are open.');
    expect(announcer.read('assertive')).toBe('Merge refused.');
  });

  it('is idempotent — two alert regions would announce every refusal twice', () => {
    const first = createAnnouncer(document);
    first.announce('a', 'assertive');
    first.announce('a', 'polite');
    const second = createAnnouncer(document);
    second.announce('b', 'assertive');
    second.announce('b', 'polite');
    expect(document.querySelectorAll('[role="alert"]')).toHaveLength(1);
    expect(document.querySelectorAll('[role="status"]')).toHaveLength(1);
    expect(second.read('assertive')).toBe('b');
  });

  it('creates a region only when something is said in it', () => {
    // A region nobody uses is a node in every screenshot and every accessibility tree for
    // no reason. They are created on first use, not on construction.
    createAnnouncer(document);
    expect(document.querySelectorAll('[role="alert"]')).toHaveLength(0);
    expect(document.querySelectorAll('[role="status"]')).toHaveLength(0);
  });

  it('hides the regions without removing them from the accessibility tree', () => {
    const announcer = createAnnouncer(document);
    announcer.announce('x');
    const style = document.getElementById('mainline-live-polite')?.getAttribute('style') ?? '';
    // display:none and visibility:hidden both REMOVE the text — the classic way an
    // announcer ships announcing nothing.
    expect(style).not.toContain('display:none');
    expect(style).not.toContain('visibility:hidden');
    expect(style).toContain('clip-path');
  });

  it('re-announces an identical message, because a refusal repeated must be heard twice', () => {
    const announcer = createAnnouncer(document);
    announcer.announce('Merge refused.', 'assertive');
    announcer.announce('Merge refused.', 'assertive');
    expect(announcer.read('assertive')).toBe('Merge refused.');
  });

  it('leaves no blocking accessibility finding of its own', () => {
    createAnnouncer(document).announce('x');
    const report = audit(document.body);
    expect(report.blocking).toEqual([]);
  });
});

describe('announceVerbatim', () => {
  it('announces the exact string, assertively by default', () => {
    const announcer = createAnnouncer(document);
    announcer.announceVerbatim('gate_closed_when_issued');
    expect(announcer.read('assertive')).toBe('gate_closed_when_issued');
  });

  it('refuses the empty string', () => {
    expect(verbatimRefusal('')).not.toBeNull();
    expect(() => {
      createAnnouncer(document).announceVerbatim('');
    }).toThrow(/empty string/);
  });

  it('REFUSES rather than trims a value with surrounding whitespace', () => {
    expect(() => {
      createAnnouncer(document).announceVerbatim(' 23514 ');
    }).toThrow(/whitespace/);
  });

  it('refuses a multi-line value, because a live region flattens newlines', () => {
    expect(() => {
      createAnnouncer(document).announceVerbatim('line one\nline two');
    }).toThrow(/multi-line/);
  });

  it('permits ordinary prose through announce(), which is allowed to compose', () => {
    // The split IS the design: one function may compose, the other may not.
    const announcer = createAnnouncer(document);
    announcer.announce('  Merge refused by constraint:  ');
    expect(announcer.read('polite')).toBe('  Merge refused by constraint:  ');
  });
});
