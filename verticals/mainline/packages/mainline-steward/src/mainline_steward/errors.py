# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Every refusal this package can raise, as a typed class with a reason.

The Steward's whole output is a claim about what a review saw. A run that half-failed
and reported anyway would be worse than a run that did not happen, because the
attestation would carry the authority of a completed review over a partial reading. So
every failure here is a distinct class, is raised before an attestation is emitted, and
names the thing that was missing rather than the place the code gave up.

The one exception is :class:`ReadFailed`, which is *captured* rather than raised: a
single view that would not answer is recorded as an indeterminate finding and downgrades
the run outcome, because "one of the nine reads did not answer" is itself an ops fact a
reader needs. Everything else aborts.
"""

from __future__ import annotations


class StewardError(Exception):
    """Base class for every error this package raises."""


class ConfigurationRefused(StewardError):
    """A required piece of run configuration is absent, empty or self-contradictory.

    Raised at the top of a run, never half-way through. A Steward that discovers at
    emit time that it never knew its own cluster id has already done the reads under
    an identity it cannot name.
    """


class SkillPinRefused(StewardError):
    """A consumed skill is missing, or its bytes do not match the recorded digest.

    A floating skill reference is a floating claim: "the observability skill said X"
    means nothing if the skill can change under the sentence. The pin is the commit;
    the digest is the bytes; a mismatch in either is a refusal, never a warning.
    """


class ScheduleRefused(StewardError):
    """``schedules.yaml`` is absent, malformed, or names an occurrence that does not exist."""


class OccurrenceAlreadyAttested(StewardError):
    """This ``(schedule_id, occurrence_ts)`` has already produced an attestation.

    EventBridge Scheduler is at-least-once, so a second invocation of the same
    occurrence is expected rather than exceptional. It is an error class and not a
    silent return because the caller — the entrypoint — has to be able to exit 0 on it
    deliberately, and an exception that is caught by name is a decision a reader can see.
    """


class ReadFailed(StewardError):
    """One contracted read did not answer.

    Captured into an indeterminate finding rather than aborting the run. See the module
    docstring: which read failed is an ops fact, and losing it to an exception would
    make a partial reading indistinguishable from a clean one.
    """

    def __init__(self, view: str, detail: str) -> None:
        """Record the view that would not answer and what the surface said."""
        self.view = view
        self.detail = detail
        super().__init__(f"{view}: {detail}")


class CcloudUnavailable(StewardError):
    """No ``ccloud`` shim could be resolved, and no fixture directory was supplied.

    Never silently degraded. §9.3 is explicit that unattended ``ccloud`` auth is
    undocumented; the honest positions are "ran it and here is the parsed JSON" and
    "could not run it, and here is why" — not an empty finding that looks like a clean one.
    """


class CcloudFieldMissing(StewardError):
    """A ``ccloud -o json`` response is missing a field the caller named.

    §9.3: *parse the JSON — never screen-scrape — and treat a missing field as a hard
    failure, because a silently renamed field is how a provisioning agent lies.*
    """

    def __init__(self, command: str, field: str, present: tuple[str, ...]) -> None:
        """Record the command, the absent field, and what the response did carry."""
        self.command = command
        self.field = field
        self.present = present
        super().__init__(
            f"{command}: response has no field {field!r}; it carried {list(present)}. "
            "A missing field is a hard failure — a silently renamed field is how a "
            "provisioning agent lies."
        )


class AttestationRefused(StewardError):
    """The attestation could not be built or could not be written.

    Covers a payload that will not canonicalise (a float reached an evidentiary
    payload — CU-5), a finding with no statement, and a write the surface rejected.
    """
