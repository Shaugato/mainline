// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * W7 — THE ACCESSIBILITY FLOOR OF THE OPERATOR SURFACE.
 *
 * ── WHAT THIS AUDITS, AND WHY IT IS THE CAPTURE AND NOT A FIXTURE ────────────────────
 *
 * It audits the DOM the real screens actually produced, taken out of
 * `evidence/demo/operator-capture.json` — the file `scripts/operator-capture.mjs` writes
 * after driving a real Chromium against `scripts/deploy/local_furl.py` over the local
 * CockroachDB node. Five stages: the permit before the press, the 23514 refusal, the P0001
 * refusal after the counter was forged, the admission, and the gated change request.
 *
 * The alternative was to build the screens here out of hand-written payloads. That would
 * have been an audit of a fixture. Half of what an accessibility floor is about on THIS
 * product is what happens when the database says something unexpected — a `parsed`
 * constraint source, a `not_computable` alternative, an absent field — and a fixture is
 * exactly where those never happen. So the bytes are real, and the audit is of what a judge
 * and a screen-reader user will actually meet.
 *
 * A capture that is missing makes this file FAIL, never skip. "Nothing to check" is not the
 * same as "clean" — `scripts/check-a11y.ts` says so in its own header and exits 2 rather
 * than 0 when it cannot measure.
 *
 * ── IT REUSES `src/a11y`, AND DOES NOT TOUCH IT ──────────────────────────────────────
 *
 * `audit()`, `accessibleName()`, `visibleTextContent()`, `isTabbable()`, `LIVE_REGION_ROLES`
 * and `runSourceChecks()` all come from `src/a11y`, which belongs to another domain and is
 * read-only here. Re-implementing an accessible-name algorithm in a test directory is how a
 * repository ends up with two of them that disagree.
 *
 * ── WHAT IT CANNOT SEE, SAID OUT LOUD ────────────────────────────────────────────────
 *
 * jsdom has no cascade and no layout, so colour contrast, focus-ring visibility, reflow and
 * target size are invisible here. `src/a11y/audit.ts` `NOT_CHECKED_HERE` enumerates that and
 * the enumeration is printed on every failure. Those claims are measured in the BROWSER
 * tier instead — `tests/browser/operator-permit.spec.ts` and `operator-change.spec.ts` run
 * axe-core against the live page — and the two tiers are complementary, not redundant.
 *
 * The same is true of live focus: `document.activeElement` in a parsed snapshot is `<body>`
 * for every snapshot, so a focus assertion here would pass or fail for a reason that has
 * nothing to do with the product. What this tier CAN assert is the structural precondition —
 * that a revealed beat is somewhere focus can be sent — and it does. The behavioural claim
 * is asserted for real in the browser tier.
 */

import { readFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { audit, formatReport } from '../../../../src/a11y/audit';
import { accessibleName, visibleTextContent, isAriaHidden } from '../../../../src/a11y/accname';
import { isTabbable, tabOrder } from '../../../../src/a11y/focus';
import { LIVE_REGION_ROLES } from '../../../../src/a11y/roles';
import { classify, runSourceChecks } from '../../../../src/a11y/source-checks';

// ───────────────────────────────────────────────────────────────────────────────────────
// The capture, read off disk
// ───────────────────────────────────────────────────────────────────────────────────────

const HERE = dirname(fileURLToPath(import.meta.url));
/** `console/tests/unit/operator/a11y` → repository root. */
const REPO_ROOT = resolve(HERE, '../../../../../../../..');
const CAPTURE = resolve(REPO_ROOT, 'evidence/demo/operator-capture.json');

const HOW_TO_REGENERATE =
  'Regenerate it:\n' +
  '  1. .venv/Scripts/python.exe scripts/deploy/local_furl.py --port 8741 \\\n' +
  '       --web-root verticals/mainline/apps/console/dist --require-web-root \\\n' +
  '       --dsn "postgresql://root@localhost:26257/defaultdb?sslmode=disable" \\\n' +
  '       --database mainline_demo --permit-id dec0de00-0006-4000-8000-000000000001\n' +
  '  2. cd verticals/mainline/apps/console && node scripts/operator-capture.mjs';

interface Stage {
  readonly id: string;
  readonly note: string;
  readonly html: string;
}

interface Capture {
  readonly target: { readonly emulator_header: string | null };
  readonly stages: readonly Stage[];
}

function loadCapture(): Capture {
  if (!existsSync(CAPTURE)) {
    throw new Error(
      `${CAPTURE} does not exist, so this audit has not run — it has failed to measure, ` +
        `which is not the same as passing.\n${HOW_TO_REGENERATE}`,
    );
  }
  const capture = JSON.parse(readFileSync(CAPTURE, 'utf8')) as Capture;
  if (capture.stages.length === 0) {
    throw new Error(`${CAPTURE} carries no stages.\n${HOW_TO_REGENERATE}`);
  }
  return capture;
}

const CAPTURED = loadCapture();

/** Parses one captured stage into a document this environment can audit. */
function documentOf(stage: Stage): Document {
  const parsed = new DOMParser().parseFromString(stage.html, 'text/html');
  if (parsed.body.childElementCount === 0) {
    throw new Error(`stage ${stage.id} parsed to an empty body; the capture is not usable.`);
  }
  return parsed;
}

const STAGES: readonly { stage: Stage; doc: Document }[] = CAPTURED.stages.map((stage) => ({
  stage,
  doc: documentOf(stage),
}));

/**
 * One captured stage, by id, or a failure that names the missing stage.
 *
 * A non-null assertion here would turn "the capture is incomplete" into an unexplained
 * TypeError three frames from the cause; `pnpm run lint` forbids the assertion for exactly
 * that reason and the named throw is the better artefact anyway.
 */
function stageDoc(id: string): Document {
  const found = STAGES.find((entry) => entry.stage.id === id);
  if (found === undefined) {
    throw new Error(`the capture carries no stage "${id}".\n${HOW_TO_REGENERATE}`);
  }
  return found.doc;
}

/** The element, or a failure that says what was looked for and did not exist. */
function must<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`${what} is not in the captured DOM, so nothing here was asserted.`);
  }
  return value;
}

/** The stages that carry the permit screen, i.e. everything before the change request. */
const PERMIT_STAGES = STAGES.filter(({ stage }) => stage.id.includes('permit') || stage.id.includes('refused') || stage.id.includes('forged') || stage.id.includes('admitted'));

// ───────────────────────────────────────────────────────────────────────────────────────
// The capture is the thing it says it is
// ───────────────────────────────────────────────────────────────────────────────────────

describe('the capture this audit reads', () => {
  it('came off the local emulator and carries every stage the film needs', () => {
    expect(CAPTURED.target.emulator_header).toBe('local_furl');
    const ids = CAPTURED.stages.map((stage) => stage.id);
    expect(ids).toContain('01-permit-before-press');
    expect(ids).toContain('02-refused-23514');
    expect(ids).toContain('03-forged-counter-refused-anyway');
    expect(ids).toContain('04-admitted-and-proven');
    expect(ids).toContain('05-change-request-gated');
  });

  it('carries real rendered screens, not empty shells', () => {
    for (const { stage, doc } of STAGES) {
      // A guard, not a formality: an audit of an empty tree reports zero findings and looks
      // exactly like a clean one.
      expect(doc.querySelectorAll('*').length, `${stage.id} is nearly empty`).toBeGreaterThan(200);
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────────────────
// The repo's own auditor, over the real DOM
// ───────────────────────────────────────────────────────────────────────────────────────

describe('src/a11y/audit over every captured stage', () => {
  /**
   * The findings this audit currently reports, each with its owner and its one-line fix.
   *
   * This is a RATCHET, not an amnesty: the assertion below is that the set of rule ids
   * reported is a SUBSET of this one. A new rule firing fails the test, and every entry here
   * is a named, owned, open defect rather than a silence.
   *
   * `src/a11y/audit.ts` refuses a `skip` with no reason for the same purpose.
   */
  const KNOWN: Readonly<Record<string, string>> = {
    // OWNER W3 (src/operator/permit/signatures.ts). The block sets role="table" on the
    // wrapper and role="row" on each row, but .cow-sig-h and .cow-sig-cell carry no role, so
    // the grid exposes no cells and a screen reader reads it as empty. Two attributes fix it.
    'aria-required-children': 'W3 · signatures.ts · role="columnheader" / role="cell"',
    // OWNER W1 (src/operator/permit/screen.ts). The permit screen's headings start at h2.
    // The change screen already has an h1; the permit screen needs the same.
    'heading-order': 'W1 · the permit screen has no h1 and jumps h2 → h4',
  };

  for (const { stage, doc } of STAGES) {
    it(`reports no rule outside the recorded set — ${stage.id}`, () => {
      const report = audit(doc, { expectMain: true });
      const unexpected = [...new Set(report.findings.map((finding) => finding.ruleId))].filter(
        (ruleId) => !Object.prototype.hasOwnProperty.call(KNOWN, ruleId),
      );
      expect(
        unexpected,
        `new accessibility rule(s) firing on ${stage.id}: ${unexpected.join(', ')}\n\n` +
          formatReport(report, stage.id),
      ).toEqual([]);
    });
  }

  it('the recorded set is not empty for a vacuous reason', () => {
    // If `audit()` ever stopped running its rules, every assertion above would pass. This
    // one fails instead.
    const report = audit(stageDoc('01-permit-before-press'), { expectMain: true });
    expect(report.rulesRun.length).toBeGreaterThan(15);
    expect(report.elementsChecked).toBeGreaterThan(200);
    expect(report.notChecked.length).toBeGreaterThan(0);
  });
});

// ───────────────────────────────────────────────────────────────────────────────────────
// Every interactive control has an accessible name
// ───────────────────────────────────────────────────────────────────────────────────────

describe('every interactive control has an accessible name', () => {
  const INTERACTIVE = 'button, a[href], input, select, textarea, [role="button"], [role="link"]';

  for (const { stage, doc } of STAGES) {
    it(`names every control on ${stage.id}`, () => {
      const controls = [...doc.querySelectorAll(INTERACTIVE)].filter(
        (element) => !isAriaHidden(element),
      );
      expect(controls.length, `${stage.id} has no interactive control at all`).toBeGreaterThan(0);

      const unnamed = controls
        .filter((element) => accessibleName(element).trim() === '')
        .map((element) => `<${element.tagName.toLowerCase()} class="${element.className}">`);
      expect(
        unnamed,
        `controls with no accessible name on ${stage.id}. A control a screen reader announces ` +
          'as "button" is a control nobody can use:\n  ' + unnamed.join('\n  '),
      ).toEqual([]);
    });
  }

  it('the ISSUE control says what it is, and the locked one says why', () => {
    const refused = stageDoc('02-refused-23514');
    const issue = must(refused.querySelector('[data-action="issue"]'), 'the ISSUE control');
    expect(accessibleName(issue)).toContain('ISSUE');
    expect(issue.hasAttribute('disabled')).toBe(true);
    // A disabled control with no stated reason is a dead end. R15's lock line is that reason
    // and it names the thing that refused the write.
    const lock = refused.querySelector('.cow-actionbar__lock');
    expect(lock).not.toBeNull();
    expect(visibleTextContent(must(lock, 'the lock line'))).toMatch(/refused this write/);
  });

  it('the disabled approve control on the change screen is described, not merely dead', () => {
    const change = stageDoc('05-change-request-gated');
    const approve = must(change.querySelector('button.moc-approve'), 'the approve control');
    expect(approve.getAttribute('aria-disabled')).toBe('true');
    const describedBy = approve.getAttribute('aria-describedby');
    expect(describedBy).not.toBeNull();
    const reason = change.getElementById(must(describedBy, 'aria-describedby on approve'));
    expect(reason, 'aria-describedby points at nothing').not.toBeNull();
    expect(visibleTextContent(must(reason, 'the described reason'))).toMatch(/blocking obligation/);
  });
});

// ───────────────────────────────────────────────────────────────────────────────────────
// The refusal is ANNOUNCED, not swapped in silently
// ───────────────────────────────────────────────────────────────────────────────────────

describe('the refusal banner is announced', () => {
  function inLiveRegion(element: Element): boolean {
    let current: Element | null = element;
    while (current !== null) {
      if (current.hasAttribute('aria-live')) return true;
      const role = current.getAttribute('role');
      if (role?.split(/\s+/).some((token) => LIVE_REGION_ROLES.has(token)) === true) return true;
      current = current.parentElement;
    }
    return false;
  }

  for (const id of ['02-refused-23514', '03-forged-counter-refused-anyway']) {
    it(`announces the refusal on ${id}`, () => {
      const doc = stageDoc(id);
      const banners = [...doc.querySelectorAll('.cow-refusal')];
      expect(banners.length, `${id} renders no refusal banner`).toBeGreaterThan(0);
      for (const banner of banners) {
        expect(
          inLiveRegion(banner),
          'a refusal appeared in the DOM with no live region around it. A refusal an operator ' +
            'cannot hear is a refusal that did not happen for that operator, and this product ' +
            'IS a refusal.',
        ).toBe(true);
      }
    });
  }

  it('does not announce the whole result region assertively', () => {
    const doc = stageDoc('04-admitted-and-proven');
    const result = must(doc.querySelector('[data-result="true"]'), 'the result region');
    // `role="alert"` on the container would re-announce every beat, every fact and every
    // statement each time one more is revealed. The alert is scoped to the banner.
    expect(result.getAttribute('role')).not.toBe('alert');
    expect(result.getAttribute('aria-live')).toBeNull();
  });

  it('the admission is reachable too — it is not announced but it is in the document', () => {
    const doc = stageDoc('04-admitted-and-proven');
    // R16: the film does not end on a refusal. An admission that only existed as a colour
    // change would be invisible to a screen reader; it is a section with a headline.
    const admit = must(doc.querySelector('[data-beat="admit"]'), 'the admission beat');
    expect(visibleTextContent(admit)).toContain('ISSUE ADMITTED');
  });
});

// ───────────────────────────────────────────────────────────────────────────────────────
// Focus, at the level a parsed snapshot can honestly assert
// ───────────────────────────────────────────────────────────────────────────────────────

describe('a revealed beat is somewhere focus can be sent', () => {
  /**
   * The behavioural claim — that focus MOVES when a beat is revealed — is asserted in the
   * browser tier, where `document.activeElement` means something. What this tier asserts is
   * the precondition: there has to be somewhere to send it. A section with no tabbable
   * content and no `tabindex="-1"` cannot receive programmatic focus at all, so no amount of
   * later work in `ActionBar.ts` could manage focus onto it.
   */
  it('every revealed beat can receive programmatic focus', () => {
    const doc = stageDoc('04-admitted-and-proven');
    const beats = [...doc.querySelectorAll('[data-beat]')];
    expect(beats.length).toBe(4);

    const unreachable = beats
      .filter((beat) => {
        if (beat.hasAttribute('tabindex')) return false;
        return tabOrder(beat).length === 0;
      })
      .map((beat) => `beat ${beat.getAttribute('data-ordinal')} (${beat.getAttribute('data-beat')})`);

    expect(
      unreachable,
      'these beats have no focus target: no tabbable content and no tabindex="-1", so focus ' +
        'cannot be moved onto them when they are revealed. Measured 2026-08-15: nothing in ' +
        'src/operator/** calls .focus() at all, so pressing ISSUE and every reveal after it ' +
        'drops focus to <body>. WCAG 2.4.3.\n' +
        'OWNER: W5 (src/operator/issue/ActionBar.ts). The shell already provides the pattern — ' +
        'boot.ts gives #cw-module tabIndex = -1 as "a programmatic focus target for the skip ' +
        'that the module screens own". Give each beat section tabIndex = -1 and focus the ' +
        'newly revealed one.\n  ' + unreachable.join('\n  '),
    ).toEqual([]);
  });

  it('the tab order never runs backwards through a positive tabindex', () => {
    for (const { stage, doc } of STAGES) {
      const positive = [...doc.querySelectorAll('[tabindex]')].filter(
        (element) => Number(element.getAttribute('tabindex')) > 0,
      );
      expect(positive.map((element) => element.outerHTML.slice(0, 80)), stage.id).toEqual([]);
    }
  });

  it('nothing focusable is hidden from assistive technology', () => {
    for (const { stage, doc } of STAGES) {
      const trapped = [...doc.querySelectorAll('[aria-hidden="true"] *')]
        .filter((element) => isTabbable(element))
        .map((element) => `${element.tagName.toLowerCase()}.${element.className}`);
      expect(trapped, `${stage.id} hides a tabbable element from assistive tech`).toEqual([]);
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────────────────
// Nothing load-bearing is carried by colour alone
// ───────────────────────────────────────────────────────────────────────────────────────

describe('status and severity are never colour alone', () => {
  /**
   * `src/a11y/audit.ts` has a `severity-not-colour-alone` rule keyed on `data-severity`. The
   * operator surface uses no such attribute, so that rule is VACUOUS here — it would pass on
   * a screen that carried severity in a red dot and nothing else. So the substantive claim is
   * asserted directly, over the elements that actually carry a state or a severity.
   */
  const STATEFUL: readonly string[] = [
    '.cow-state-chip', // the permit's state
    '.hz-state', // whether the obligation has been answered
    '.hz-sev', // the precursor's severity
    '.cow-sig-cell', // signed / unsigned
    '.cow-refusal__chip', // reported vs parsed
    '.moc-statechip', // the change request's state
    '[data-beat]', // refused vs admitted
  ];

  for (const { stage, doc } of STAGES) {
    it(`every state indicator exposes text on ${stage.id}`, () => {
      const mute: string[] = [];
      for (const selector of STATEFUL) {
        for (const element of doc.querySelectorAll(selector)) {
          if (isAriaHidden(element)) continue;
          const text = `${visibleTextContent(element)} ${accessibleName(element)}`;
          if (!/[a-z0-9]/i.test(text)) {
            mute.push(`${selector} → <${element.tagName.toLowerCase()} class="${element.className}">`);
          }
        }
      }
      expect(
        mute,
        'these carry a state or a severity with no text at all, so they mean nothing to a ' +
          'screen reader, to a monochrome print, or to a court exhibit photocopied twice:\n  ' +
          mute.join('\n  '),
      ).toEqual([]);
    });
  }

  it('the refused and admitted beats say so in words, not only in colour', () => {
    const doc = stageDoc('04-admitted-and-proven');
    const words = [...doc.querySelectorAll('[data-beat]')].map((beat) =>
      visibleTextContent(beat).toUpperCase(),
    );
    expect(words.filter((text) => text.includes('NOT ISSUED')).length).toBe(2);
    expect(words.filter((text) => text.includes('ISSUE ADMITTED')).length).toBe(1);
  });

  it('the blue cold-work edge is decoration and carries no meaning', () => {
    for (const { stage, doc } of PERMIT_STAGES) {
      const edges = [...doc.querySelectorAll('.cow-edge')];
      expect(edges.length, `${stage.id} has no permit-type edge`).toBeGreaterThan(0);
      for (const edge of edges) {
        // R9 / §7: no column carries a permit type. The edge is a colour and colour alone,
        // which is fine EXACTLY BECAUSE the type is also a labelled control beside it. If the
        // edge ever gained text or a label it would become a second, unsourced claim.
        expect(edge.getAttribute('aria-hidden'), stage.id).toBe('true');
        expect(visibleTextContent(edge).trim()).toBe('');
        expect(edge.getAttribute('aria-label')).toBeNull();
        expect(edge.getAttribute('title')).toBeNull();
      }
      // And the thing the edge is about IS available as text.
      const select = doc.querySelector('#cow-permit-type');
      expect(select, `${stage.id} has no permit-type control`).not.toBeNull();
      expect(accessibleName(must(select, 'the permit-type control')).trim()).not.toBe('');
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────────────────
// The shipped CSS, through the repo's own source checks
// ───────────────────────────────────────────────────────────────────────────────────────

/**
 * `scripts/check-a11y.ts` runs these over all of `src/**` as a CI gate. Running them again
 * scoped to `src/operator/**` is not redundant: it makes the operator surface's own failure
 * message name the operator surface, and it keeps the claim asserted in a test the fleet
 * runs rather than only in a script somebody has to remember to invoke.
 */
const RAW_SOURCES: Record<string, unknown> = import.meta.glob('/src/operator/**/*.{ts,css}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const OPERATOR_SOURCES: readonly { path: string; text: string }[] = Object.entries(RAW_SOURCES).map(
  ([path, value]) => {
    if (typeof value !== 'string') {
      throw new Error(`${path} did not load as text; the raw glob is missing import: 'default'.`);
    }
    return { path: path.replace(/^\//, ''), text: value };
  },
);

describe('the shipped operator source, through src/a11y/source-checks', () => {
  it('loaded enough files to mean something', () => {
    // The same guard `scripts/check-a11y.ts` applies: a scan that matched nothing reports
    // clean forever.
    expect(OPERATOR_SOURCES.length).toBeGreaterThan(20);
    expect(OPERATOR_SOURCES.filter((file) => file.path.endsWith('.css')).length).toBeGreaterThan(4);
  });

  it('has no violation — including no :focus-visible rule that removes an outline', () => {
    const result = runSourceChecks(
      OPERATOR_SOURCES.map((file) => classify(file.path, file.text)),
    );
    const violations = result.violations.filter((violation) => violation.severity === 'violation');
    expect(
      violations.map(
        (violation) =>
          `${violation.file}:${violation.line} [${violation.checkId}] ${violation.message}`,
      ),
      'a focus ring the browser draws is the only thing a keyboard user has. Removing it — ' +
        'even inside :focus-visible, even "temporarily" — makes the surface unusable without ' +
        'a mouse.',
    ).toEqual([]);
  });

  it('every operator stylesheet that styles :focus-visible restores an outline', () => {
    // The source check above is a text scan for removal. This is the positive claim: the
    // operator CSS does declare focus rings, so a stylesheet that simply never mentioned
    // focus (and inherited nothing) could not pass by silence.
    const css = OPERATOR_SOURCES.filter((file) => file.path.endsWith('.css'));
    const withFocus = css.filter((file) => file.text.includes(':focus-visible'));
    expect(withFocus.length, 'no operator stylesheet declares a focus ring at all').toBeGreaterThan(
      0,
    );
    for (const file of withFocus) {
      expect(file.text, `${file.path} styles :focus-visible without an outline`).toMatch(
        /outline:\s*(?!none|0)/,
      );
    }
  });
});
