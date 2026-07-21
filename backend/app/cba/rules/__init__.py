"""Trade rule registry. Each rule is a small, independently unit-tested class."""

from ..context import TradeRule
from .picks import StepienRule
from .restrictions import NoTradeClauseRule, RecentlySignedRule, TwoWayExclusionRule
from .roster import RosterSizeRule
from .salary import (
    MinimumTeamSalaryRule,
    SalaryDataAvailabilityRule,
    SalaryMatchingRule,
    SecondApronAggregationRule,
)


def all_rules() -> list[TradeRule]:
    return [
        SalaryDataAvailabilityRule(),
        SalaryMatchingRule(),
        SecondApronAggregationRule(),
        MinimumTeamSalaryRule(),
        RosterSizeRule(),
        RecentlySignedRule(),
        NoTradeClauseRule(),
        TwoWayExclusionRule(),
        StepienRule(),
    ]
