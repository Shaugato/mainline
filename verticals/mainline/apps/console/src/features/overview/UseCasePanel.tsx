// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * ONE WORKED CASE, ending in a door.
 *
 * The founder's second request: *"the demo is all about showing what we are doing… we need
 * to present a couple of exceptional use cases that we are solving with this platform and
 * show those examples."* A case that ends in prose is a claim. A case that ends in a link
 * into the screen that shows it, addressed to a subject THIS deployment seeded, is an
 * invitation to check.
 *
 * Three parts, in this order and no other: the situation, what a reader will SEE when they
 * click, and why that is worth anything. The middle part is the load-bearing one — it is
 * written as a prediction about a screen, so a reader who clicks and sees something else
 * has caught this panel, which is exactly the property a demo should have.
 *
 * ── THE DOOR IS DISABLED HONESTLY, OR IT IS NOT THERE AT ALL ─────────────────────
 *
 * A destination whose subject the kernel did not name renders as a NAMED ABSENCE: no
 * `href`, no `<a>`, and the reason the resolver gave, in words, where the link would have
 * been. It is never quietly dropped and it never points at a screen with no subject on it,
 * because "the link went somewhere and the somewhere was empty" is the exact experience
 * this wave exists to end (`docs/leads/screens-work-plan.md` §0).
 *
 * There is no identifier written down in this file or in any file beside it. The one
 * shortcut this panel is not allowed to take is a UUID typed into a constant: it works
 * until the day a deployment seeds a different history, and then it is `BLK-07` again with
 * a luckier value (§2.2).
 */

import { type ReactNode } from 'react';

import { Mono } from '../../design/primitives';

import styles from './overview.module.css';

/**
 * Where a case sends a reader.
 *
 * `href` and `absence` are exclusive: exactly one of them is non-null, and which one is a
 * fact about whether the kernel named the subject — never about how this panel feels about
 * the screen at the other end.
 */
export interface Destination {
  /** The words on the link. Names the screen and the subject it will be showing. */
  readonly label: string;
  /** Ready to click, or `null` when no subject was resolved. */
  readonly href: string | null;
  /** The identifier the link carries, for display beside it. `null` with `href`. */
  readonly subject: string | null;
  /** Why there is no link, in the resolver's terms. `null` exactly when `href` is not. */
  readonly absence: string | null;
  /** The transport's own report, verbatim, when it had one. Rendered in a `<pre>`. */
  readonly detail: string | null;
}

export interface UseCasePanelProps {
  /** `1`, `2`, `3` — the reading order, shown so a reader can hold their place. */
  readonly ordinal: number;
  readonly title: string;
  /** The situation, in plain language. One or two sentences. */
  readonly situation: readonly string[];
  /** What a reader will see on the linked screen. Each item is a prediction. */
  readonly whatYouWillSee: readonly string[];
  /** Why the above is worth anything. One or two sentences, no adjectives. */
  readonly whyItMatters: readonly string[];
  /** One or two doors. The first is the case's own screen. */
  readonly destinations: readonly Destination[];
  readonly testId: string;
}

function Door({ destination }: { readonly destination: Destination }): ReactNode {
  if (destination.href === null) {
    return (
      <div className={styles.doorAbsent} data-testid="usecase-door-absent">
        <span className={styles.doorAbsentLabel}>{destination.label} — no subject to address</span>
        <p className={styles.doorAbsentReason}>{destination.absence}</p>
        {destination.detail !== null && <pre className={styles.verbatim}>{destination.detail}</pre>}
      </div>
    );
  }

  return (
    <a className={styles.door} href={destination.href} data-testid="usecase-door">
      <span className={styles.doorLabel}>{destination.label}</span>
      {destination.subject !== null && (
        <span className={styles.doorSubject}>
          <Mono>{destination.subject}</Mono>
        </span>
      )}
    </a>
  );
}

export function UseCasePanel({
  ordinal,
  title,
  situation,
  whatYouWillSee,
  whyItMatters,
  destinations,
  testId,
}: UseCasePanelProps): ReactNode {
  const headingId = `usecase-${ordinal}-title`;
  return (
    <section className={styles.useCase} aria-labelledby={headingId} data-testid={testId}>
      <p className={styles.useCaseKicker}>case {ordinal}</p>
      <h2 className={styles.useCaseTitle} id={headingId}>
        {title}
      </h2>

      {situation.map((sentence) => (
        <p className={styles.prose} key={sentence}>
          {sentence}
        </p>
      ))}

      <p className={styles.subhead}>What you will see when you click</p>
      <ul className={styles.list}>
        {whatYouWillSee.map((line) => (
          <li className={styles.listItem} key={line}>
            {line}
          </li>
        ))}
      </ul>

      <p className={styles.subhead}>Why that is worth anything</p>
      {whyItMatters.map((sentence) => (
        <p className={styles.prose} key={sentence}>
          {sentence}
        </p>
      ))}

      <div className={styles.doors}>
        {destinations.map((destination) => (
          <Door destination={destination} key={destination.label} />
        ))}
      </div>
    </section>
  );
}
