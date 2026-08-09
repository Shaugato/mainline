// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE AUDITOR, AGAINST PLANTED VIOLATIONS.
 *
 * PL-2 in a checker: every rule gets a fixture that MUST fail it and a fixture that must
 * NOT. The second half is the one people leave out, and leaving it out is how a rule that
 * returns a finding for every element it sees ships as a passing gate.
 *
 * The last block is the one that would catch a hollowed-out auditor: it asserts that the
 * clean panel produces zero findings AND that the rule list is non-empty AND that the
 * run actually visited every rule — a suite whose `audit()` silently returned an empty
 * report would satisfy every "expect no findings" assertion in this file.
 */

import { afterEach, describe, expect, it } from 'vitest';

import { audit, assertAccessible, formatReport, RULE_IDS, RULES } from '../../../src/a11y/audit';
import { CLEAN_PANEL, mount, unmountAll } from './_fixtures';

afterEach(unmountAll);

/** Every rule id a report fired, deduplicated. */
function firedRules(html: string): readonly string[] {
  const report = audit(mount(html));
  return [...new Set(report.findings.map((finding) => finding.ruleId))].sort();
}

function findingsFor(html: string, ruleId: string): readonly string[] {
  return audit(mount(html))
    .findings.filter((finding) => finding.ruleId === ruleId)
    .map((finding) => finding.message);
}

describe('the auditor sees the tree it thinks it sees', () => {
  it('runs every declared rule', () => {
    const report = audit(mount(CLEAN_PANEL));
    expect(report.rulesRun).toEqual([...RULE_IDS]);
    expect(RULES.length).toBeGreaterThan(15);
  });

  it('counts the elements it visited, so an empty run cannot look like a clean one', () => {
    const report = audit(mount(CLEAN_PANEL));
    expect(report.elementsChecked).toBeGreaterThan(10);
  });

  it('reports what it did NOT check, in every report', () => {
    const report = audit(mount('<p>nothing wrong here</p>'));
    expect(report.findings).toEqual([]);
    // A report that lists only what it found reads as a clearance. This one cannot.
    expect(report.notChecked.length).toBeGreaterThan(5);
    expect(report.notChecked.join(' ')).toContain('Colour contrast');
    expect(formatReport(report)).toContain('NOT CHECKED');
  });
});

describe('the clean control', () => {
  it('produces no finding at all', () => {
    const report = audit(mount(CLEAN_PANEL));
    expect(
      report.findings.map((finding) => `${finding.ruleId}: ${finding.message}`),
      'the auditor flagged structurally correct markup. A checker that flags everything is as ' +
        'useless as one that flags nothing, and every planted assertion below would still pass.',
    ).toEqual([]);
  });

  it('does not demand a main landmark of a fragment', () => {
    // A component audited in isolation can never satisfy "the document has one main".
    expect(firedRules(CLEAN_PANEL)).not.toContain('main-landmark');
  });
});

describe('generic rules — each planted, each caught', () => {
  it('img-alt: an image with no alt attribute', () => {
    expect(findingsFor('<img src="seal.png">', 'img-alt')).toHaveLength(1);
    // alt="" is a decision, not an omission, and must not be flagged.
    expect(findingsFor('<img src="seal.png" alt="">', 'img-alt')).toEqual([]);
  });

  it('control-name: a button with nothing in it', () => {
    expect(findingsFor('<button type="button"></button>', 'control-name')).toHaveLength(1);
    expect(findingsFor('<button type="button">Sign</button>', 'control-name')).toEqual([]);
    expect(findingsFor('<button type="button" aria-label="Sign"></button>', 'control-name')).toEqual([]);
  });

  it('control-name: a decorative glyph inside the button is not a name', () => {
    // The classic false pass: aria-hidden text still counts as content for a naive
    // textContent check, so the button reports as named "×".
    expect(
      findingsFor('<button type="button"><span aria-hidden="true">×</span></button>', 'control-name'),
    ).toHaveLength(1);
  });

  it('control-name: an input labelled by a dangling for= is unnamed', () => {
    expect(findingsFor('<label for="nope">Threshold</label><input id="yes">', 'control-name')).toHaveLength(1);
  });

  it('heading-empty and heading-order', () => {
    expect(findingsFor('<h2></h2>', 'heading-empty')).toHaveLength(1);
    expect(findingsFor('<h2>Two</h2><h4>Four</h4>', 'heading-order')).toHaveLength(1);
    expect(findingsFor('<h2>Two</h2><h3>Three</h3>', 'heading-order')).toEqual([]);
  });

  it('duplicate-id', () => {
    expect(findingsFor('<p id="x">a</p><p id="x">b</p>', 'duplicate-id')).toHaveLength(1);
    expect(findingsFor('<p id="x">a</p><p id="y">b</p>', 'duplicate-id')).toEqual([]);
  });

  it('aria-attr-known: the misspelling no browser reports', () => {
    // `aria-lable` is silently ignored by every browser. The control ships nameless and
    // every screenshot looks correct.
    const messages = findingsFor('<button aria-lable="Close"></button>', 'aria-attr-known');
    expect(messages).toHaveLength(1);
    expect(messages[0]).toContain('aria-lable');
    expect(findingsFor('<button aria-label="Close"></button>', 'aria-attr-known')).toEqual([]);
  });

  it('aria-attr-value: a boolean that is not one', () => {
    expect(findingsFor('<div aria-busy="yes">x</div>', 'aria-attr-value')).toHaveLength(1);
    expect(findingsFor('<div aria-live="loud">x</div>', 'aria-attr-value')).toHaveLength(1);
    expect(findingsFor('<div aria-live="polite">x</div>', 'aria-attr-value')).toEqual([]);
  });

  it('aria-ref-resolves: a label that reviews as present and announces as absent', () => {
    expect(findingsFor('<div aria-labelledby="ghost">x</div>', 'aria-ref-resolves')).toHaveLength(1);
    expect(
      findingsFor('<span id="real">Name</span><div aria-labelledby="real">x</div>', 'aria-ref-resolves'),
    ).toEqual([]);
  });

  it('role-known', () => {
    expect(findingsFor('<div role="widget">x</div>', 'role-known')).toHaveLength(1);
    expect(findingsFor('<div role="status">x</div>', 'role-known')).toEqual([]);
  });

  it('tabindex-positive', () => {
    expect(findingsFor('<button tabindex="3">Sign</button>', 'tabindex-positive')).toHaveLength(1);
    expect(findingsFor('<button tabindex="0">Sign</button>', 'tabindex-positive')).toEqual([]);
    // tabindex="-1" is the programmatic focus target the shell's <main> depends on.
    expect(findingsFor('<main tabindex="-1">x</main>', 'tabindex-positive')).toEqual([]);
  });

  it('focusable-inside-aria-hidden', () => {
    expect(
      findingsFor('<div aria-hidden="true"><button>Sign</button></div>', 'focusable-inside-aria-hidden'),
    ).toHaveLength(1);
    expect(
      findingsFor(
        '<div aria-hidden="true"><button tabindex="-1">Sign</button></div>',
        'focusable-inside-aria-hidden',
      ),
    ).toEqual([]);
  });

  it('list-structure', () => {
    expect(findingsFor('<ul><div>not an item</div></ul>', 'list-structure')).toHaveLength(1);
    expect(findingsFor('<ul><li>an item</li></ul>', 'list-structure')).toEqual([]);
  });

  it('label-for-resolves', () => {
    expect(findingsFor('<label for="ghost">Name</label>', 'label-for-resolves')).toHaveLength(1);
    expect(findingsFor('<label for="d">Name</label><div id="d"></div>', 'label-for-resolves')).toHaveLength(1);
    expect(findingsFor('<label for="i">Name</label><input id="i">', 'label-for-resolves')).toEqual([]);
  });

  it('landmark-unique-name: two navigations announced identically', () => {
    expect(findingsFor('<nav><a href="#a">a</a></nav><nav><a href="#b">b</a></nav>', 'landmark-unique-name')).toHaveLength(2);
    expect(
      findingsFor(
        '<nav aria-label="Surfaces"><a href="#a">a</a></nav><nav aria-label="Ancestry"><a href="#b">b</a></nav>',
        'landmark-unique-name',
      ),
    ).toEqual([]);
  });

  it('region-name', () => {
    expect(findingsFor('<div role="region">x</div>', 'region-name')).toHaveLength(1);
    expect(findingsFor('<div role="region" aria-label="Weld">x</div>', 'region-name')).toEqual([]);
  });

  it('main-landmark, only when a whole document is audited', () => {
    const report = audit(mount('<main>one</main><main>two</main>'), { expectMain: true });
    expect(report.findings.filter((finding) => finding.ruleId === 'main-landmark')).toHaveLength(1);
  });
});

describe('the five MAINLINE rules — the ones no generic checker has', () => {
  it('verbatim-is-text: a provenance-chipped claim rendered as a graphic', () => {
    const messages = findingsFor('<img data-provenance="db:constraint" alt="gate_closed_when_issued">', 'verbatim-is-text');
    expect(
      messages,
      'a verbatim value a reader cannot select is a verbatim value the medium paraphrased — it ' +
        'cannot be pasted into a bug report, a filing, or a grep of the schema.',
    ).toHaveLength(1);
    expect(findingsFor('<code data-provenance="db:constraint">gate_closed_when_issued</code>', 'verbatim-is-text')).toEqual([]);
  });

  it('severity-not-colour-alone: a band with no text', () => {
    expect(findingsFor('<span data-severity="blood_fatal"></span>', 'severity-not-colour-alone')).toHaveLength(1);
    expect(findingsFor('<span data-severity="blood_fatal">fatality</span>', 'severity-not-colour-alone')).toEqual([]);
    // A visually-hidden word is a legitimate answer: the layout may carry the colour and
    // the accessibility tree the word.
    expect(
      findingsFor(
        '<span data-severity="blood_fatal"><span class="visually-hidden">fatality</span></span>',
        'severity-not-colour-alone',
      ),
    ).toEqual([]);
  });

  it('refusal-in-live-region: a refusal nobody hears', () => {
    expect(findingsFor('<section data-failure="refusal">refused</section>', 'refusal-in-live-region')).toHaveLength(1);
    expect(
      findingsFor('<section role="alert" data-failure="refusal">refused</section>', 'refusal-in-live-region'),
    ).toEqual([]);
    expect(
      findingsFor('<div aria-live="assertive"><section data-failure="refusal">refused</section></div>', 'refusal-in-live-region'),
    ).toEqual([]);
  });

  it('refusal-in-live-region: a RECORDED SQLSTATE is not an announcement', () => {
    // A past refusal in an audit table, a custody row, an exposure receipt. Requiring a
    // live region around every one would announce every historical SQLSTATE on the screen
    // assertively — which is exactly how an operator learns to turn live regions off, and
    // then does not hear the one that mattered.
    expect(findingsFor('<td><code data-sqlstate="23514">23514</code></td>', 'refusal-in-live-region')).toEqual([]);
  });

  it('no-person-in-memory: D15 carried into pixels', () => {
    const messages = findingsFor(
      '<div data-register="memory"><span data-person="p-17">shift supervisor</span></div>',
      'no-person-in-memory',
    );
    expect(messages).toHaveLength(1);
    // The same markup outside the MEMORY register is not this rule's business — the
    // attribution rule is about the dimensional surface, and a rule that fired everywhere
    // would be turned off.
    expect(
      findingsFor('<div data-register="evidence"><span data-person="p-17">x</span></div>', 'no-person-in-memory'),
    ).toEqual([]);
  });

  it('signer-sub-is-not-a-dimension: never a colour, an axis, a facet or a sort key', () => {
    expect(findingsFor('<div data-colour-by="signer_sub">x</div>', 'signer-sub-is-not-a-dimension')).toHaveLength(1);
    expect(findingsFor('<table data-sort-key="signerSub"></table>', 'signer-sub-is-not-a-dimension')).toHaveLength(1);
    expect(findingsFor('<div data-colour-by="virulence_class">x</div>', 'signer-sub-is-not-a-dimension')).toEqual([]);
  });
});

describe('assertAccessible — D14’s gate', () => {
  it('throws on a blocking finding and prints the whole report', () => {
    const container = mount('<button aria-lable="Close"></button>');
    let message = '';
    try {
      assertAccessible(container, { label: 'planted' });
    } catch (error) {
      message = error instanceof Error ? error.message : String(error);
    }
    expect(message).toContain('blocking accessibility finding');
    expect(message).toContain('aria-attr-known');
    // The limits travel with the failure, because a person reading a failure is the
    // person most likely to conclude that a pass means "accessible".
    expect(message).toContain('NOT CHECKED');
  });

  it('does not throw on a moderate finding, and still reports it', () => {
    const container = mount('<h2>Two</h2><h4>Four</h4>');
    const report = assertAccessible(container);
    expect(report.blocking).toEqual([]);
    expect(report.counts.moderate).toBe(1);
  });

  it('returns the report on success, so a caller can assert what was checked', () => {
    const report = assertAccessible(mount(CLEAN_PANEL));
    expect(report.rulesRun.length).toBe(RULE_IDS.length);
  });
});
