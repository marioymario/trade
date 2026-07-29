from __future__ import annotations

import json

from files.research.scorer_search_config import contract_as_dict


def main() -> None:
    contract = contract_as_dict()

    print()
    print("=== SCORER SEARCH CONTRACT ===")
    print(
        json.dumps(
            contract,
            indent=2,
            sort_keys=True,
        )
    )
    print("================================")
    print()


if __name__ == "__main__":
    main()
