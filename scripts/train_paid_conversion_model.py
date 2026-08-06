from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service import PaidConversionModelService


def main() -> None:
    result = PaidConversionModelService().train_and_predict_all()
    print(
        f"trained={result.trained_count} candidates={result.candidate_count} "
        f"conversion_mae={result.model_mae:.4f}"
    )


if __name__ == "__main__":
    main()
