from app.schemas.matching import (
    BlockingPolicyConfig,
    HybridWeights,
    ScoringConfig,
    SemanticScoringConfig,
)

DEFAULT_SCORING_CONFIG = ScoringConfig()
DETERMINISTIC_V11_CONFIG = ScoringConfig(
    version="deterministic-v1.1",
    blocking_policy=BlockingPolicyConfig(),
)
CANDIDATE_SCORING_CONFIG = DETERMINISTIC_V11_CONFIG
HYBRID_SCORING_CONFIG = ScoringConfig(
    version="hybrid-v1",
    base_rule_version="deterministic-v1.1",
    blocking_policy=BlockingPolicyConfig(),
    semantic=SemanticScoringConfig(),
    hybrid_weights=HybridWeights(),
)

SCORING_CONFIGS = {
    DEFAULT_SCORING_CONFIG.version: DEFAULT_SCORING_CONFIG,
    DETERMINISTIC_V11_CONFIG.version: DETERMINISTIC_V11_CONFIG,
    HYBRID_SCORING_CONFIG.version: HYBRID_SCORING_CONFIG,
}


def scoring_config_for(version: str) -> ScoringConfig:
    try:
        return SCORING_CONFIGS[version]
    except KeyError as exc:
        raise ValueError(f"unsupported scoring version: {version}") from exc
