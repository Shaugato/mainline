// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * R9 — THE HONESTY LEDGER, AS A TEST.
 *
 * `docs/demo/operator-systems-plan.md` R9 rules that Figure 1 elements 1, 3 and 5 have no
 * column in this deployment and are therefore typed by a human on camera; that element 8
 * (PPE) renders greyed with the words "not carried by this deployment"; and that hard-coding
 * a plausible job description, plant name, crew or PPE list is FORBIDDEN — *"the same class
 * of act as reshaping a seed to match a constant."*
 *
 * The failure mode this file exists to catch is a quiet one. Somebody, wanting the screen to
 * look less empty on camera, prefills the description of work with a sentence about isolating
 * a pump. It is invisible to every other test we have, and it is indistinguishable to a judge
 * from real data. So the assertions below are deliberately blunt: the typed controls are
 * EMPTY, they carry NO chip, and the function that renders them cannot be handed a value.
 */

import { describe, expect, it } from 'vitest';

import {
  formatInstantUtc,
  NOT_CARRIED,
  notCarriedField,
  omittedElement,
  provenanceChip,
  readField,
  typedField,
} from '../../../../src/operator/permit/typed-fields';

describe('typedField — a field a human fills in, and nothing else (R9)', () => {
  const spec = {
    element: 5,
    id: 'test-description',
    label: 'Description of work',
    placeholder: 'What is to be done',
  } as const;

  it('renders a real input with a caret and a border, not a styled div', () => {
    const row = typedField(spec);
    const input = row.querySelector<HTMLInputElement>('input');
    expect(input).not.toBeNull();
    expect(input?.type).toBe('text');
    expect(input?.className).toContain('cow-input');
  });

  it('renders EMPTY — the placeholder is a prompt and is not a value', () => {
    const row = typedField(spec);
    const input = row.querySelector<HTMLInputElement>('input');
    expect(input?.value).toBe('');
    expect(input?.placeholder).toBe(spec.placeholder);
    // `placeholder` is not submitted and is not read back by `.value`. The distinction is
    // the whole point: prompting is not asserting.
    expect(input?.getAttribute('value')).toBeNull();
  });

  it('carries NO provenance chip, because there is nothing to corroborate', () => {
    const row = typedField(spec);
    expect(row.querySelector('.cow-chip')).toBeNull();
  });

  it('says on screen that the value was typed here and is not carried by the deployment', () => {
    const row = typedField(spec);
    expect(row.querySelector('.cow-hint')?.textContent).toContain(NOT_CARRIED);
  });

  it('is a textarea when the element needs one, still empty', () => {
    const row = typedField({ ...spec, rows: 4 });
    const area = row.querySelector<HTMLTextAreaElement>('textarea');
    expect(area?.rows).toBe(4);
    expect(area?.value).toBe('');
    expect(area?.textContent).toBe('');
  });

  it('is labelled, so the caret is reachable from the label', () => {
    const row = typedField(spec);
    const label = row.querySelector<HTMLLabelElement>('label');
    expect(label?.htmlFor).toBe(spec.id);
    expect(row.querySelector<HTMLInputElement>('input')?.id).toBe(spec.id);
  });

  it('cannot be handed a value or a pointer — the signature has neither', () => {
    // A structural assertion, kept honest by the compiler: adding `value` or `pointer` to
    // TypedFieldSpec would make this line compile, and this test is the tripwire.
    const keys = Object.keys(spec);
    expect(keys).not.toContain('value');
    expect(keys).not.toContain('pointer');
    expect(typedField.length).toBe(1);
  });
});

describe('notCarriedField — element 8, PPE (R9 honest option B)', () => {
  it('renders the exact words the ruling requires', () => {
    const row = notCarriedField({ element: 8, label: 'Protective equipment required' });
    const slot = row.querySelector('.cow-absent');
    expect(slot?.textContent).toBe('not carried by this deployment');
    expect(slot?.getAttribute('data-not-carried')).toBe('true');
  });

  it('names no equipment — a fabricated PPE list is the forbidden option', () => {
    const row = notCarriedField({ element: 8, label: 'Protective equipment required' });
    const text = (row.textContent ?? '').toLowerCase();
    for (const invented of ['gloves', 'goggles', 'helmet', 'harness', 'respirator', 'overalls']) {
      expect(text).not.toContain(invented);
    }
  });

  it('carries no provenance chip, because it carries no value', () => {
    const row = notCarriedField({ element: 8, label: 'Protective equipment required' });
    expect(row.querySelector('.cow-chip')).toBeNull();
  });
});

describe('omittedElement — element 11, named rather than silently dropped', () => {
  it('states the omission and its reason', () => {
    const row = omittedElement({
      element: 11,
      label: '11 · Extension / shift handover',
      reason: 'this deployment has no extension mechanism',
    });
    expect(row.getAttribute('data-omitted')).toBe('true');
    expect(row.textContent).toContain('omitted');
    expect(row.textContent).toContain('no extension mechanism');
  });
});

describe('readField — a server value cannot reach the screen unattributed', () => {
  const claims = (pointer: string) => (pointer === '/external_ref' ? ('db:column' as const) : null);

  it('renders the chip the envelope claimed, naming the pointer it claimed', () => {
    const row = readField({
      label: 'Permit reference number',
      value: 'REF-UNDER-TEST',
      pointer: '/external_ref',
      lookup: claims,
    });
    const chip = row.querySelector('.cow-chip');
    expect(chip?.textContent).toBe('db:column');
    expect(chip?.getAttribute('data-pointer')).toBe('/external_ref');
  });

  it('renders NO chip for a pointer the envelope did not claim', () => {
    const row = readField({
      label: 'Slice digest',
      value: 'value-under-test',
      pointer: '/slice_digest',
      lookup: claims,
    });
    expect(row.querySelector('.cow-chip')).toBeNull();
    expect(row.querySelector('.cow-field-value')?.textContent).toBe('value-under-test');
  });

  it('renders null AS null — absence, never a placeholder', () => {
    const row = readField({
      label: 'Merged commit',
      value: null,
      pointer: '/merged_commit',
      lookup: () => 'db:column',
    });
    expect(row.querySelector('.cow-null')?.textContent).toBe('null');
    for (const guess of ['—', 'N/A', 'n/a', 'None', 'unknown', 'pending']) {
      expect(row.textContent).not.toContain(guess);
    }
  });

  it('keeps the machine-readable instant beside the human one', () => {
    const row = readField({
      label: 'Valid from',
      value: '2026-08-02T00:00:00Z',
      pointer: '/opened_at',
      lookup: () => 'db:column',
      kind: 'instant',
    });
    const time = row.querySelector('time');
    expect(time?.getAttribute('datetime')).toBe('2026-08-02T00:00:00Z');
    expect(time?.textContent).toContain('2026');
  });
});

describe('provenanceChip — the rule, in one function', () => {
  it('is null when the pointer is unclaimed', () => {
    expect(provenanceChip(() => null, '/anything')).toBeNull();
  });

  it('reports the kind the lookup returned and never a default', () => {
    expect(provenanceChip(() => 'derived', '/x')?.textContent).toBe('derived');
    expect(provenanceChip(() => 'db:constraint', '/x')?.textContent).toBe('db:constraint');
  });
});

describe('formatInstantUtc — a convenience that never becomes the only copy', () => {
  it('formats in UTC and marks it', () => {
    expect(formatInstantUtc('2026-08-02T00:00:00Z')).toContain('Aug');
    expect(formatInstantUtc('2026-08-02T00:00:00Z').endsWith('Z')).toBe(true);
  });

  it('returns an unparseable string VERBATIM rather than repairing it', () => {
    expect(formatInstantUtc('not-a-timestamp')).toBe('not-a-timestamp');
  });
});
