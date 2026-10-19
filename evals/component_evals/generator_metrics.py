"""Generator metrics: is the LLM's answer grounded in the chunks and on-topic?"""

from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric


def generator_metrics(model: str = "gpt-4.1-mini", threshold: float = 0.65) -> list:
    return [
        FaithfulnessMetric(threshold=threshold, model=model, include_reason=True),
        AnswerRelevancyMetric(threshold=threshold, model=model, include_reason=True),
    ]
