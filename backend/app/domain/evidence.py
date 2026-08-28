"""The evidence ladder: what a number is, and what it is allowed to claim.

Pivot's organising constraint is that analytical authority is never created by
presentation. A figure on a screen has to be able to say where it came from, and the
three answers are not interchangeable:

    OBSERVED   a quantity a provider reported. Nobody in this repository computed it.
               `PTS`, `MIN`, a roster row, a salary in a contract year.

    DERIVED    an arithmetic transform of observed quantities, with no basketball
               judgement in it beyond the choice of formula. A per-100 rate, a
               percentile against a stated population, a weighted z-score index.
               Reproducible by anyone holding the same rows.

    INFERRED   a basketball *attribute* asserted from derived quantities — a claim about
               a player or a roster that goes beyond restating the arithmetic. "This
               player protects the rim." "This roster cannot create shots." An inference
               can be wrong in a way a derivation cannot.

The distinction is not decoration. R4-2 withdrew a shipped point-of-attack composite
because it was an INFERENCE that its own pre-registered check refuted, while the DERIVED
steals rate underneath it was never in question. Keeping the two apart is what made the
withdrawal possible without deleting the data.

Nothing here computes anything. This module gives the rest of the system a vocabulary for
saying which rung a number sits on, and a `Measurement` envelope that carries the rung
along with the value so a consumer cannot render one without the other.

`Measurement` is deliberately **not** a replacement for `None`. The repository's existing
discipline — a missing input is `None`, never a default (see `analytics.fit`,
`analytics.components`, `cba.context.overall_status`) — is unchanged and load-bearing.
`Measurement.unavailable()` exists for the case where a consumer needs the *reason*
alongside the absence, which is what the four-state CBA standard already does for rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Generic, TypeVar


class Evidence(StrEnum):
    """Which rung of the ladder a quantity sits on."""

    OBSERVED = "observed"
    DERIVED = "derived"
    INFERRED = "inferred"

    @property
    def label(self) -> str:
        return {
            Evidence.OBSERVED: "Observed",
            Evidence.DERIVED: "Derived",
            Evidence.INFERRED: "Inferred",
        }[self]

    @property
    def definition(self) -> str:
        return {
            Evidence.OBSERVED: (
                "Reported by a data provider. Not computed here."
            ),
            Evidence.DERIVED: (
                "An arithmetic transform of observed quantities, reproducible from the "
                "same rows by the documented formula."
            ),
            Evidence.INFERRED: (
                "A basketball attribute asserted from derived quantities. Goes beyond "
                "restating the arithmetic, and can be wrong in a way a derivation cannot."
            ),
        }[self]


class Confidence(StrEnum):
    """How much weight a claim can bear.

    Ordered, and deliberately coarse: this repository has no calibrated probability for
    "is this archetype label right", so a five-point scale would be false precision about
    false precision. `VALIDATED` is reserved for quantities with a *falsifiable check that
    is run by a command* — the comparable, acquisition and adversarial batteries — not for
    quantities that merely have a test.
    """

    VALIDATED = "validated"
    MEASURED = "measured"
    HEURISTIC = "heuristic"
    UNAVAILABLE = "unavailable"

    @property
    def label(self) -> str:
        return {
            Confidence.VALIDATED: "Validated",
            Confidence.MEASURED: "Measured",
            Confidence.HEURISTIC: "Heuristic",
            Confidence.UNAVAILABLE: "Unavailable",
        }[self]

    @property
    def definition(self) -> str:
        return {
            Confidence.VALIDATED: (
                "Checked against a stated threshold by a command that exits non-zero when "
                "it fails."
            ),
            Confidence.MEASURED: (
                "Computed from real data by a documented method, with no validation "
                "target available to check it against."
            ),
            Confidence.HEURISTIC: (
                "A transparent rule chosen by construct rather than fitted. Defensible, "
                "not validated — treat as a starting point for judgement."
            ),
            Confidence.UNAVAILABLE: "Not established. No value is offered.",
        }[self]


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Measurement(Generic[T]):
    """A value that carries its own provenance, or an explicit absence with a reason.

    Construct through `observed` / `derived` / `inferred` / `unavailable` rather than
    directly, so every instance states its rung.
    """

    value: T | None
    evidence: Evidence | None
    confidence: Confidence
    #: How the number was produced, in one line, in the language a GM would read.
    method: str = ""
    #: Where the inputs came from — a provider name, a table, a fitted model version.
    source: str = ""
    #: What this number cannot support. Rendered wherever the number is.
    limitations: tuple[str, ...] = field(default_factory=tuple)
    #: Why there is no value. Non-empty exactly when `available` is False.
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.value is not None

    @classmethod
    def observed(
        cls, value: T, *, source: str, method: str = "", limitations: tuple[str, ...] = ()
    ) -> Measurement[T]:
        return cls(
            value=value,
            evidence=Evidence.OBSERVED,
            confidence=Confidence.MEASURED,
            method=method or "Reported by the provider as-is.",
            source=source,
            limitations=limitations,
        )

    @classmethod
    def derived(
        cls,
        value: T,
        *,
        method: str,
        source: str,
        confidence: Confidence = Confidence.MEASURED,
        limitations: tuple[str, ...] = (),
    ) -> Measurement[T]:
        return cls(
            value=value,
            evidence=Evidence.DERIVED,
            confidence=confidence,
            method=method,
            source=source,
            limitations=limitations,
        )

    @classmethod
    def inferred(
        cls,
        value: T,
        *,
        method: str,
        source: str,
        confidence: Confidence = Confidence.HEURISTIC,
        limitations: tuple[str, ...] = (),
    ) -> Measurement[T]:
        return cls(
            value=value,
            evidence=Evidence.INFERRED,
            confidence=confidence,
            method=method,
            source=source,
            limitations=limitations,
        )

    @classmethod
    def unavailable(cls, reason: str) -> Measurement[T]:
        """No value, and the reason is the payload.

        The reason is required. An unavailable measurement whose reason is empty is the
        thing this class exists to prevent: a gap the UI has to invent copy for.
        """
        if not reason:
            raise ValueError("an unavailable measurement must state why")
        return cls(
            value=None,
            evidence=None,
            confidence=Confidence.UNAVAILABLE,
            reason=reason,
        )

    def as_dict(self) -> dict[str, Any]:
        """Serialization shape shared by every Pivot intelligence endpoint.

        `value` and `reason` are mutually exclusive by construction, and both keys are
        always present, so a client never has to branch on key existence to find out
        whether it has a number.
        """
        return {
            "value": self.value,
            "available": self.available,
            "evidence": self.evidence.value if self.evidence else None,
            "confidence": self.confidence.value,
            "method": self.method,
            "source": self.source,
            "limitations": list(self.limitations),
            "reason": self.reason,
        }


__all__ = ["Confidence", "Evidence", "Measurement"]
