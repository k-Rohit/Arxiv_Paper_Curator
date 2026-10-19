"""Retriever metrics: did hybrid search bring back the right chunks?"""

from deepeval.metrics import ContextualPrecisionMetric, ContextualRecallMetric, ContextualRelevancyMetric


def retriever_metrics(model: str = "gpt-4.1-mini", threshold: float = 0.65) -> list:
    return [
        ContextualRecallMetric(threshold=threshold, model=model, include_reason=True),
        ContextualPrecisionMetric(threshold=threshold, model=model, include_reason=True),
        ContextualRelevancyMetric(threshold=threshold, model=model, include_reason=True),
    ]
