from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service import RecommendationMetricService


def main() -> None:
    RecommendationMetricService().refresh_all()
    print("Recommendation metrics refreshed")


if __name__ == "__main__":
    main()
