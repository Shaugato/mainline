// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE VOCABULARY IS CLOSED, AND CLOSED IS THE POINT.
 *
 * `/memory.html` renders envelope payloads verbatim, so it speaks the envelope's five
 * chips — `db:column`, `db:constraint`, `recomputed`, `staged`, `derived` — and not the
 * console's four. That discrepancy is REAL and it is RECORDED, not a bug to be tidied:
 *
 *   `src/design/provenance.ts`  four kinds; its docstring says there is no `derived`
 *   the read API's envelope     five chips; `derived` means "computed by this read API
 *                               from columns it names in statement_refs"
 *
 * The page uses the API's five because it renders what the API shipped and the API is the
 * authority on what it shipped. Both files stay exactly as they are, and the tests below
 * assert the relationship between them rather than papering over it: the four shared kinds
 * must be spoken with byte-identical wording, and the one extra must be exactly `derived`.
 *
 * Two prohibitions carry the weight here, and each has a test:
 *
 *   NO SIXTH CHIP.        `renderChip` throws on anything outside the five. A page that
 *                         invented a chip would be asserting a meaning no emitter claimed.
 *   NO SUBSTITUTE.        A value whose pointer carries no chip renders with NO chip and
 *                         nothing in its place — not a dash, not a grey box, not the word
 *                         "unknown". An unclaimed provenance is better than a comfortable
 *                         default, and an empty slot is how the absence gets NOTICED.
 */

import { describe, expect, it } from 'vitest';

import {
  PROVENANCE_KINDS as CONSOLE_KINDS,
  PROVENANCE_SPOKEN as CONSOLE_SPOKEN,
} from '../../../src/design/provenance';

// @ts-expect-error -- `public/` is served verbatim and is deliberately outside the
// TypeScript project; the module's shape is re-declared below. See verify.test.ts.
import * as memoryVerifyUntyped from '../../../public/memory-verify.js';

interface ProvenanceEntry {
  readonly chip: string;
  readonly pointer: string;
}

interface MemoryVerifyModule {
  readonly PROVENANCE_CHIPS: readonly string[];
  readonly PROVENANCE_SPOKEN: Readonly<Record<string, string>>;
  readonly CLASS_NAMES: { readonly chip: string; readonly chipDetail: string };
  renderChip(kind: unknown, pointer?: unknown): Element | null;
  lookupChip(provenance: unknown, pointer: unknown): string | null;
}

const mv = memoryVerifyUntyped as MemoryVerifyModule;

/**
 * The `provenance` array of `GET /v1/ledger` against the deployed Function URL, read at
 * `observed_at 2026-08-15T11:52:32.039704Z` — all eighteen entries, transcribed verbatim.
 * It is here so that the chip vocabulary is tested against chips a server actually claimed,
 * at pointers it actually claimed them for, rather than against invented pairs.
 */
const CAPTURED_LEDGER_PROVENANCE: readonly ProvenanceEntry[] = [
  { chip: 'db:column', pointer: '/site_code' },
  { chip: 'db:column', pointer: '/checkpoints/0' },
  { chip: 'derived', pointer: '/checkpoints/0/log_key' },
  { chip: 'db:column', pointer: '/checkpoints/1' },
  { chip: 'derived', pointer: '/checkpoints/1/log_key' },
  { chip: 'db:column', pointer: '/leaves/0' },
  { chip: 'db:column', pointer: '/leaves/1' },
  { chip: 'db:column', pointer: '/leaves/2' },
  { chip: 'db:column', pointer: '/leaves/3' },
  { chip: 'db:column', pointer: '/nodes/0' },
  { chip: 'db:column', pointer: '/nodes/1' },
  { chip: 'db:column', pointer: '/nodes/2' },
  { chip: 'derived', pointer: '/cosignatures/0/witness_key' },
  { chip: 'db:column', pointer: '/cosignatures/0' },
  { chip: 'derived', pointer: '/cosignatures/1/witness_key' },
  { chip: 'db:column', pointer: '/cosignatures/1' },
  { chip: 'derived', pointer: '/inclusion_proofs' },
  { chip: 'derived', pointer: '/consistency_proofs' },
];

describe('the vocabulary is the envelope’s five, and it is closed', () => {
  it('is exactly those five, in that order', () => {
    expect(mv.PROVENANCE_CHIPS).toStrictEqual([
      'db:column',
      'db:constraint',
      'recomputed',
      'staged',
      'derived',
    ]);
  });

  it('cannot be extended at run time', () => {
    expect(Object.isFrozen(mv.PROVENANCE_CHIPS)).toBe(true);
    expect(() => {
      (mv.PROVENANCE_CHIPS as string[]).push('estimated');
    }).toThrow(TypeError);
    expect(mv.PROVENANCE_CHIPS).toHaveLength(5);
    expect(Object.isFrozen(mv.PROVENANCE_SPOKEN)).toBe(true);
  });

  it('speaks every one of its own kinds', () => {
    for (const chip of mv.PROVENANCE_CHIPS) {
      expect(mv.PROVENANCE_SPOKEN[chip], `no spoken text for ${chip}`).toBeTruthy();
    }
    expect(Object.keys(mv.PROVENANCE_SPOKEN).sort()).toStrictEqual([...mv.PROVENANCE_CHIPS].sort());
  });
});

describe('the recorded discrepancy with the console’s four kinds', () => {
  it('is exactly one extra chip, and it is `derived`', () => {
    const extra = mv.PROVENANCE_CHIPS.filter(
      (chip) => !(CONSOLE_KINDS as readonly string[]).includes(chip),
    );
    expect(extra).toStrictEqual(['derived']);
    expect([...CONSOLE_KINDS].every((kind) => mv.PROVENANCE_CHIPS.includes(kind))).toBe(true);
  });

  it('speaks the four shared kinds with the console’s wording, word for word', () => {
    for (const kind of CONSOLE_KINDS) {
      expect(mv.PROVENANCE_SPOKEN[kind], `wording drifted for ${kind}`).toBe(CONSOLE_SPOKEN[kind]);
    }
  });

  it('speaks `derived` as what the read API says it is', () => {
    expect(mv.PROVENANCE_SPOKEN.derived ?? '').toContain('statement_refs');
  });
});

describe('renderChip', () => {
  it('renders each kind with its pointer, its spoken sentence and its bare label', () => {
    for (const kind of mv.PROVENANCE_CHIPS) {
      const chip = mv.renderChip(kind, '/data/checks/0/severity');
      expect(chip).not.toBeNull();
      expect(chip?.className).toBe(mv.CLASS_NAMES.chip);
      expect(chip?.getAttribute('data-kind')).toBe(kind);
      expect(chip?.textContent).toContain(`provenance: ${mv.PROVENANCE_SPOKEN[kind] ?? ''}.`);
      expect(chip?.textContent).toContain('/data/checks/0/severity');

      // The bare kind is shown, and hidden from the screen reader that just heard the
      // sentence — otherwise `db:column` is spoken twice, once as jargon.
      const visible = chip?.querySelector('[aria-hidden="true"]');
      expect(visible?.textContent).toBe(kind);
    }
  });

  it('THROWS on a sixth chip rather than inventing one', () => {
    for (const invented of [
      'computed',
      'estimated',
      'derived ',
      'DB:COLUMN',
      'db:columns',
      '',
      'recomputed?',
    ]) {
      expect(() => mv.renderChip(invented, '/x'), `${JSON.stringify(invented)} was accepted`).toThrow(
        RangeError,
      );
    }
  });

  it('THROWS on a chip that is not even a string', () => {
    for (const invented of [0, 1, true, false, {}, ['db:column'], Symbol.iterator]) {
      expect(() => mv.renderChip(invented, '/x')).toThrow(RangeError);
    }
  });

  it('names the closed vocabulary in the refusal, so the fix is obvious', () => {
    expect(() => mv.renderChip('computed', '/x')).toThrow(/db:column/);
    expect(() => mv.renderChip('computed', '/x')).toThrow(/closed/);
  });
});

describe('the no-chip path renders NOTHING, not a placeholder', () => {
  it.each([
    ['null', null],
    ['undefined', undefined],
  ])('returns null for %s, and appending it adds no node', (_label, kind) => {
    expect(mv.renderChip(kind, '/data/closure/max_severity')).toBeNull();

    const container = document.createElement('div');
    const chip = mv.renderChip(kind, '/data/closure/max_severity');
    if (chip !== null) {
      container.appendChild(chip);
    }
    expect(container.childNodes).toHaveLength(0);
    expect(container.innerHTML).toBe('');
    expect(container.textContent).toBe('');
  });

  it('is reached by a pointer the response did not claim a chip for', () => {
    expect(mv.lookupChip(CAPTURED_LEDGER_PROVENANCE, '/leaves/0/payload')).toBeNull();
    expect(mv.renderChip(mv.lookupChip(CAPTURED_LEDGER_PROVENANCE, '/leaves/0/payload'))).toBeNull();
  });

  it('shows `unspecified` when a claimed chip arrives with no pointer — a different bug', () => {
    const chip = mv.renderChip('db:column');
    expect(chip?.textContent).toContain('unspecified');

    // `staged` is the one kind whose whole content is that there is no source yet.
    const staged = mv.renderChip('staged');
    expect(staged?.textContent).not.toContain('unspecified');
    expect(staged?.querySelector(`.${mv.CLASS_NAMES.chipDetail}`)).toBeNull();
  });
});

describe('lookupChip — the page never assigns a chip the response did not claim', () => {
  it('returns the chip the captured response claimed at that pointer', () => {
    expect(mv.lookupChip(CAPTURED_LEDGER_PROVENANCE, '/leaves/2')).toBe('db:column');
    expect(mv.lookupChip(CAPTURED_LEDGER_PROVENANCE, '/leaves/3')).toBe('db:column');
    expect(mv.lookupChip(CAPTURED_LEDGER_PROVENANCE, '/inclusion_proofs')).toBe('derived');
  });

  it('finds every captured chip inside the closed vocabulary', () => {
    for (const entry of CAPTURED_LEDGER_PROVENANCE) {
      expect(mv.PROVENANCE_CHIPS, `the server claimed ${entry.chip}`).toContain(entry.chip);
      expect(mv.lookupChip(CAPTURED_LEDGER_PROVENANCE, entry.pointer)).toBe(entry.chip);
    }
  });

  it('confirms the read API never claims `recomputed` — that chip can only be earned here', () => {
    expect(CAPTURED_LEDGER_PROVENANCE.map((entry) => entry.chip)).not.toContain('recomputed');
    expect([...new Set(CAPTURED_LEDGER_PROVENANCE.map((entry) => entry.chip))].sort()).toStrictEqual(
      ['db:column', 'derived'],
    );
  });

  it('REFUSES a chip outside the vocabulary rather than dropping it quietly', () => {
    expect(() => mv.lookupChip([{ chip: 'computed', pointer: '/x' }], '/x')).toThrow(RangeError);
    expect(() => mv.lookupChip([{ chip: null, pointer: '/x' }], '/x')).toThrow(RangeError);
  });

  it('returns null, never throws, for a pointer that is simply absent', () => {
    expect(mv.lookupChip([], '/anything')).toBeNull();
    expect(mv.lookupChip(undefined, '/anything')).toBeNull();
  });

  it('refuses a pointer that is not a pointer', () => {
    expect(() => mv.lookupChip(CAPTURED_LEDGER_PROVENANCE, '')).toThrow(TypeError);
    expect(() => mv.lookupChip(CAPTURED_LEDGER_PROVENANCE, undefined)).toThrow(TypeError);
  });
});
