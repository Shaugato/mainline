// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE THREE CONTROLS.
 *
 * `docs/leads/ui.md` §1.2.2: *further back*, *further forward*, and a stop. There is no
 * fourth control here and `RAILS_CONTROLS` is the list this component maps over, so a
 * fourth cannot be added to the UI without being added to the state machine that
 * `rails.test.ts` asserts has exactly three.
 *
 * They are real `<button>`s with `aria-pressed`, operable by keyboard, in the console's
 * own focus treatment. The MEMORY register is optional, but "optional" means a reader
 * may skip it — not that a reader who arrives with a keyboard is stuck.
 */

import { type JSX } from 'react';

import { RAILS_CONTROLS, type RailsControl } from './rails';
import styles from './walk.module.css';

const CONTROL_LABEL: Record<RailsControl, string> = {
  back: 'Further back',
  forward: 'Further forward',
  stop: 'Stop',
};

const CONTROL_HINT: Record<RailsControl, string> = {
  back: 'Walk deeper into the past along the time axis.',
  forward: 'Walk toward the present along the time axis.',
  stop: 'Hold position.',
};

export interface WalkControlsProps {
  readonly control: RailsControl;
  readonly onControl: (control: RailsControl) => void;
  /** `false` when the ancestry spans a single instant and there is nowhere to walk. */
  readonly enabled: boolean;
}

export function WalkControls({ control, onControl, enabled }: WalkControlsProps): JSX.Element {
  return (
    <div className={styles.controls} role="group" aria-label="Ancestry walk — camera">
      {RAILS_CONTROLS.map((candidate) => (
        <button
          key={candidate}
          type="button"
          className={styles.control}
          data-walk-control={candidate}
          aria-pressed={control === candidate}
          title={CONTROL_HINT[candidate]}
          disabled={!enabled}
          onClick={() => {
            onControl(candidate);
          }}
        >
          {CONTROL_LABEL[candidate]}
        </button>
      ))}
    </div>
  );
}
