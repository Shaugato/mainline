// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PERMIT-TO-WORK SCREEN — the software a site supervisor actually works in.
 *
 * MAINLINE is not branded here and must not be. You see MAINLINE by seeing what it stops.
 *
 * ─── R4, WRITTEN INTO THE SOURCE BECAUSE THE PLAN SAYS TO ───────────────────────────────
 *
 *   THE ISSUE BUTTON CALLS `POST /v1/demo/gate-run`. IT NEVER CALLS
 *   `POST /v1/permits/{id}/merge`.
 *
 * `docs/deploy/gate-run-contract.md` §7: a mutating transition aimed at the seeded demo
 * subject answers **423 Locked** and names `/v1/demo/gate-run` instead. A 423 is the demo
 * protecting itself, not a gate refusal — rendering one in a refusal banner would put a
 * fabricated exhibit in front of a judge. r3-operator §5.5 calls this *"the single most
 * likely wrong turn available to a builder"*. The action bar is W5's (`src/operator/issue/`)
 * and this file does not implement it; the rule is repeated here because this is the file a
 * builder opens first when they go looking for the ISSUE button.
 *
 * ─── WHAT THIS FILE IS ──────────────────────────────────────────────────────────────────
 *
 * A composition root and nothing else. It resolves addressing, performs three reads through
 * the kernel, binds each part's chip lookup to the envelope that part's data came from, and
 * lays the parts out in HSG250 Figure 1 order. It renders no value of its own.
 *
 *   1  Permit title                    typed on camera            typed-fields (R9)
 *   2  Permit reference number         GET /v1/permits/{id}       header
 *   3  Job location                    site + typed on camera     typed-fields (R9)
 *   4  Plant identification            boundary_certificate       plant
 *   5  Description of work             typed on camera            typed-fields (R9)
 *   6  Hazard identification           SLOT — W4, mountHazardCard()
 *   7  Precautions necessary           GET /v1/clauses/…          precautions
 *   8  Protective equipment            no column                  typed-fields (R9, option B)
 *   9–13  Signature block              permit + GET /v1/receipts  signatures
 *   —  Action bar                      SLOT — W5, mountActionBar()
 *
 * ─── IT NEVER CALLS `fetch` ─────────────────────────────────────────────────────────────
 *
 * Every request goes through W2's kernel — `resolveAddressing()` for WHICH subject and
 * `readPermit` / `readClauseVersion` / `readReceipt` for the payloads. No path is assembled
 * here, no identifier is written here, and `src/operator/kernel/client.ts` records every
 * exchange in the request log on its own, so this screen does not log them a second time.
 *
 * ─── WHICH SUBJECT: NEVER A LITERAL ─────────────────────────────────────────────────────
 *
 * Plan §6 lists "a UUID literal in source" among the things that would make this work
 * worthless. There is not one in this subtree, and there is nowhere in it that one could be
 * used: every identifier arrives from `GET /v1/demo/subjects` (M9). When addressing resolves
 * no permit, the screen says so and renders the kernel's own `absent[]` reasons verbatim.
 *
 * ─── WHAT IS TYPED, AND WHAT IS NEVER TYPED ────────────────────────────────────────────
 *
 * R9 is structural here: `typed-fields.ts` is the only module that can put a value on this
 * screen, `typedField()` accepts no value and no pointer, and `readField()` accepts no value
 * without a pointer. Nothing in this subtree can prefill a supervisor's field from a
 * response, and nothing can render a server value without naming where it came from.
 */

import type { ClauseResponse, ExposureReceipt, Permit } from '../../data/types.generated';
import { mountHazardCard } from '../hazard/HazardCard';
import { mountActionBar } from '../issue/ActionBar';
import { type Addressing, resolveAddressing } from '../kernel/addressing';
import type { Exchange } from '../kernel/client';
import { chipFor } from '../kernel/envelope';
import { readClauseVersion, readPermit, readReceipt } from '../kernel/reads';
import './permit.css';
import { renderDisplayCopy } from './display-copy';
import { renderPermitHeader } from './header';
import { renderPlantIdentification } from './plant';
import { renderPrecautions } from './precautions';
import { renderSignatureBlock } from './signatures';
import {
  type ChipLookup,
  absenceBlock,
  el,
  formSection,
  notCarriedField,
  readField,
  typedField,
} from './typed-fields';

/** What the screen ended up with. Returned so W7's capture can assert against it. */
export interface PermitScreenResult {
  readonly root: HTMLElement;
  readonly addressing: Addressing;
  readonly permit: Permit | null;
  /** Every exchange this screen performed, in order. The client also logs them itself. */
  readonly exchanges: readonly Exchange<unknown>[];
}

/** A lookup that claims nothing, for a read that returned no envelope. */
const NO_CHIPS: ChipLookup = () => null;

/**
 * Mount the permit-to-work screen into `host`.
 *
 * Resolves in whatever state the kernel put the screen in — including a screen showing only
 * absence, if the reads did not resolve. It does not throw on a refused or failed read: an
 * absence rendered verbatim is the correct output, and an exception here would be this
 * screen deciding that a truthful failure is not worth showing.
 */
export async function mountPermitScreen(host: HTMLElement): Promise<PermitScreenResult> {
  const exchanges: Exchange<unknown>[] = [];

  const root = el('article', 'cow-permit');
  root.setAttribute('data-screen', 'permit');
  host.replaceChildren(root);

  const addressing = await resolveAddressing();

  if (addressing.permitId === null) {
    root.appendChild(
      absenceBlock(
        'no permit subject to address',
        addressing.failure === null
          ? 'GET /v1/demo/subjects resolved no permit_id for this deployment'
          : `${addressing.failure.kind} — ${addressing.failure.detail}`,
      ),
    );
    root.appendChild(renderAbsentList(addressing));
    return { root, addressing, permit: null, exchanges };
  }

  const permitExchange = await readPermit(addressing.permitId);
  exchanges.push(permitExchange);
  const permit = permitExchange.data;
  if (permit === null) {
    root.appendChild(
      absenceBlock(
        'the permit did not read',
        `${permitExchange.method} ${permitExchange.path} → ${permitExchange.status}` +
          (permitExchange.problem === null ? '' : ` · ${permitExchange.problem.detail}`),
      ),
    );
    return { root, addressing, permit: null, exchanges };
  }
  const permitChips: ChipLookup = (pointer) => chipFor(permitExchange.envelope, pointer);

  // ── 2 · header ─────────────────────────────────────────────────────────────────
  const header = renderPermitHeader({ permit, lookup: permitChips });
  header.actions.appendChild(renderDisplayCopy().root);
  root.appendChild(header.root);

  const body = el('div', 'cow-permit-body');
  root.appendChild(body);

  // ── 1 · permit title — typed on camera (R9) ────────────────────────────────────
  const titleSection = formSection({ element: 1, heading: 'Permit title' });
  titleSection.body.appendChild(
    typedField({
      element: 1,
      id: 'cow-permit-title',
      label: 'Title',
      placeholder: 'Title of the work this permit authorises',
    }),
  );
  body.appendChild(titleSection.root);

  // ── 3 · job location — the real site, plus a typed location (R9, plan §6.3) ────
  const locationSection = formSection({ element: 3, heading: 'Job location' });
  locationSection.body.appendChild(
    readField({
      label: 'Site of record',
      value: permit.site_code ?? null,
      pointer: '/site_code',
      lookup: permitChips,
      kind: 'mono',
    }),
  );
  locationSection.body.appendChild(
    typedField({
      element: 3,
      id: 'cow-job-location',
      label: 'Location on site',
      placeholder: 'Where on the site the work will be done',
    }),
  );
  body.appendChild(locationSection.root);

  // ── 4 · plant identification ───────────────────────────────────────────────────
  body.appendChild(renderPlantIdentification({ permit, lookup: permitChips }));

  // ── 5 · description of work — typed on camera (R9) ─────────────────────────────
  const workSection = formSection({
    element: 5,
    heading: 'Description of work to be done and its limitations',
  });
  workSection.body.appendChild(
    typedField({
      element: 5,
      id: 'cow-work-description',
      label: 'Work and its limitations',
      placeholder: 'What is to be done, and what this permit does not authorise',
      rows: 4,
    }),
  );
  body.appendChild(workSection.root);

  // ── 6 · hazard identification — W4's card, mounted, not reimplemented ──────────
  const hazardSection = formSection({
    element: 6,
    heading: 'Hazard identification',
    note: 'Including residual hazards and hazards associated with the work.',
  });
  hazardSection.root.classList.add('cow-slot-hazard');
  body.appendChild(hazardSection.root);

  // ── 7 · precautions necessary ──────────────────────────────────────────────────
  body.appendChild(await renderPrecautionsSection(addressing, exchanges));

  // ── 8 · protective equipment — no column (R9, honest option B) ─────────────────
  const ppeSection = formSection({ element: 8, heading: 'Protective equipment (including PPE)' });
  ppeSection.body.appendChild(
    notCarriedField({ element: 8, label: 'Protective equipment required' }),
  );
  body.appendChild(ppeSection.root);

  // ── 9–13 · signature block ─────────────────────────────────────────────────────
  body.appendChild(await renderSignatures(addressing, permit, permitChips, exchanges));

  // ── the action bar — W5's, mounted, not reimplemented ──────────────────────────
  // `outstanding` is the PROJECTED counter the gate reads, passed through untouched. The
  // bar renders it; this screen does not compose a sentence about it.
  const actionSlot = el('div', 'cow-slot cow-slot-action-bar');
  root.appendChild(actionSlot);
  actionSlot.appendChild(
    mountActionBar({
      outstanding: permit.counters.open_blocking,
      onExchange: (exchange) => {
        exchanges.push(exchange as Exchange<unknown>);
      },
    }).element,
  );

  // Awaited last: the card opens four reads of its own, and the rest of the form should be
  // on screen while they are in flight rather than behind them.
  await mountHazardCard(hazardSection.body, addressing);

  return { root, addressing, permit, exchanges };
}

/**
 * Element 7. Reads the clause version the addressing named, and renders absence — with the
 * exchange's own status line — when it does not resolve.
 */
async function renderPrecautionsSection(
  addressing: Addressing,
  exchanges: Exchange<unknown>[],
): Promise<HTMLElement> {
  const heading = 'Precautions necessary and actions in the event of an emergency';

  if (addressing.clauseUuid === null || addressing.commitId === null) {
    const section = formSection({ element: 7, heading });
    section.body.appendChild(
      absenceBlock(
        'no clause version to quote',
        'GET /v1/demo/subjects resolved no clause_uuid or commit_id',
      ),
    );
    return section.root;
  }

  const exchange: Exchange<ClauseResponse['data']> = await readClauseVersion(
    addressing.clauseUuid,
    addressing.commitId,
  );
  exchanges.push(exchange);
  const payload = exchange.data;
  if (payload === null) {
    const section = formSection({ element: 7, heading });
    section.body.appendChild(
      absenceBlock(
        'the clause did not read',
        `${exchange.method} ${exchange.path} → ${exchange.status}` +
          (exchange.problem === null ? '' : ` · ${exchange.problem.detail}`),
      ),
    );
    return section.root;
  }

  return renderPrecautions({
    version: payload.version,
    lookup: (pointer) => chipFor(exchange.envelope, pointer),
  });
}

/** Elements 9–13. The receipt is the acceptance row's evidence; its absence is stated. */
async function renderSignatures(
  addressing: Addressing,
  permit: Permit,
  permitLookup: ChipLookup,
  exchanges: Exchange<unknown>[],
): Promise<HTMLElement> {
  if (addressing.receiptId === null) {
    return renderSignatureBlock({
      permit,
      permitLookup,
      receipt: null,
      receiptLookup: NO_CHIPS,
      receiptAbsence: 'GET /v1/demo/subjects resolved no receipt_id',
    });
  }

  const exchange: Exchange<ExposureReceipt> = await readReceipt(addressing.receiptId);
  exchanges.push(exchange);
  if (exchange.data === null) {
    return renderSignatureBlock({
      permit,
      permitLookup,
      receipt: null,
      receiptLookup: NO_CHIPS,
      receiptAbsence: `${exchange.method} ${exchange.path} → ${exchange.status}`,
    });
  }

  return renderSignatureBlock({
    permit,
    permitLookup,
    receipt: exchange.data,
    receiptLookup: (pointer) => chipFor(exchange.envelope, pointer),
  });
}

/** The kernel's own account of what it could not address, rendered verbatim (plan §4.2). */
function renderAbsentList(addressing: Addressing): HTMLElement {
  const list = el('ul', 'cow-absent-list');
  for (const entry of addressing.absent) {
    const item = el('li', 'cow-absent-item');
    item.appendChild(el('span', 'cow-mono', `${entry.subject} · ${entry.relation}`));
    item.appendChild(el('span', 'cow-absent-reason', entry.reason));
    list.appendChild(item);
  }
  return list;
}
