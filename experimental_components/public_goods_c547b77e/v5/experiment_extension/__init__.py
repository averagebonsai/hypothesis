"""Saved-balance public-goods experiment extension.

Custom components: a contribution payload, the withdrawal-schedule mechanism,
closed-form reference utilities, and the preview/final notebook generators.
"""

from experiment_extension.mechanism import PublicGoodsMechanism, PublicGoodsParameters
from experiment_extension.references import (
    full_reinvestment_trajectory,
    marginal_private_return,
    zero_contribution_trajectory,
)
from experiment_extension.report import preview, report
from experiment_extension.schemas import ContributionPayload

__all__ = [
    "ContributionPayload",
    "PublicGoodsMechanism",
    "PublicGoodsParameters",
    "full_reinvestment_trajectory",
    "marginal_private_return",
    "preview",
    "report",
    "zero_contribution_trajectory",
]
