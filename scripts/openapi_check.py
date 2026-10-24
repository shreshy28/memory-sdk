import json
from pathlib import Path

from memory_api import create_app


def main() -> None:
    source = json.loads(Path("packages/api-contract/openapi.yaml").read_text())
    runtime = create_app().openapi()
    if set(source["paths"]) != set(runtime["paths"]):
        missing = set(runtime["paths"]) - set(source["paths"])
        extra = set(source["paths"]) - set(runtime["paths"])
        raise SystemExit(f"OpenAPI paths differ; missing={sorted(missing)}, extra={sorted(extra)}")
    statuses = source["components"]["schemas"]["OperationStatus"]["enum"]
    if len(statuses) != 8:
        raise SystemExit("OperationStatus contract is incomplete")


if __name__ == "__main__":
    main()
