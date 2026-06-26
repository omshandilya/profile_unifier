from typing import Dict, Any

class MetricsTracker:
    def __init__(self):
        self.metrics = {
            "resolve_requests": 0,
            "profile_lookups": 0,
            "errors": 0
        }

    def increment(self, metric_name: str):
        if metric_name in self.metrics:
            self.metrics[metric_name] += 1

    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics

metrics_tracker = MetricsTracker()
