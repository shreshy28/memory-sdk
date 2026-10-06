import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOTS = {
    "memory_domain": ROOT / "packages/domain/src/memory_domain",
    "memory_application": ROOT / "packages/application/src/memory_application",
    "memory_sdk": ROOT / "packages/sdk-python/src/memory_sdk",
}
FORBIDDEN = {
    "memory_domain": {
        "alembic",
        "asyncpg",
        "fastapi",
        "httpx",
        "memory_api",
        "memory_application",
        "memory_postgres",
        "memory_providers",
        "pydantic",
        "sqlalchemy",
    },
    "memory_application": {
        "alembic",
        "asyncpg",
        "fastapi",
        "memory_api",
        "memory_postgres",
        "memory_providers",
        "pydantic",
        "sqlalchemy",
    },
    "memory_sdk": {
        "memory_api",
        "memory_application",
        "memory_domain",
        "memory_postgres",
        "memory_providers",
        "sqlalchemy",
    },
}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.partition(".")[0])
    return roots


def main() -> None:
    violations: list[str] = []
    for package, root in PACKAGE_ROOTS.items():
        for path in root.rglob("*.py"):
            blocked = imported_roots(path) & FORBIDDEN[package]
            if blocked:
                violations.append(f"{path.relative_to(ROOT)} imports {', '.join(sorted(blocked))}")
    if violations:
        raise SystemExit("Architecture boundary violations:\n" + "\n".join(violations))
    print("Architecture dependency boundaries are valid.")


if __name__ == "__main__":
    main()
