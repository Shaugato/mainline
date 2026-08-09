<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# Hostile Path-B responses

`hostile_responses.json` is the adversarial corpus for `mainline-delta-oracle`:
one Anthropic-native response body per thing a **compromised** Path B would put
on the wire, as distinct from the eleven *recordings* one directory up under
`cassettes/`, which are the behaviours a **working** Path B exhibits.

Three properties of this file are load-bearing:

* **It is not a cassette store and is never replayed as one.** The bodies carry
  no key, no `prefix_digest` and no `recorded_at`, and they are served by a
  scripted transport rather than by `CassetteTransport`. A hostile body that
  lived in the cassette directory would be indistinguishable from a recording,
  which is the exact confusion the `provenance` field exists to prevent.
* **`"provenance": "synthetic-adversarial"`.** Nothing here has been near
  Bedrock, and nothing here is a claim about how any model behaves. These are
  the inputs the code must survive, not observations of a model producing them.
* **The expectations are in the file, not in the test.** Each case declares
  `expect_abstained`, `expect_label` and `expect_code`, so widening the corpus is
  a data edit and weakening an expectation is a visible diff rather than a
  loosened assertion buried in a parametrisation.

The clause pair is fixed (`clause_a`, `clause_b`): B lengthens the gas-test
interval from 30 minutes to 120 while softening nothing else, so every case is a
real weakening that an attacker would like reported as anything but.

Consumed by `tests/unit/domain/oracle_adversary/test_transport_hostility.py`.
