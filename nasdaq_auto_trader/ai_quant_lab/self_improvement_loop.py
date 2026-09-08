"""Legacy imports for the research-only candidate evaluation API."""

from .candidate_evaluation import (
    CandidateEvaluationPipeline as SelfImprovementLoop,
    CandidateEvaluationResult as SelfImprovementResult,
)

__all__ = ["SelfImprovementLoop", "SelfImprovementResult"]
