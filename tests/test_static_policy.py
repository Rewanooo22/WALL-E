"""Static policy checks (spec INV-05, P1-NG-08; ADR-001 §4.8): Phase 1 source code
contains no network, subprocess-shell, or LLM SDK imports. A runtime socket block
is added with the extraction workers (M3)."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "wall_e"
FORBIDDEN_MODULES = {
    "socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx", "aiohttp", "ftplib",
    "smtplib", "telnetlib", "xmlrpc", "websocket", "websockets", "grpc",
    "anthropic", "openai", "langchain", "litellm",
}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "__import__":
            roots.add("<dynamic __import__>")
    return roots


def test_source_tree_exists():
    assert list(SRC.rglob("*.py")), "no source files found; check would be vacuous"


def test_no_network_or_llm_imports():
    violations = {
        str(p.relative_to(SRC)): sorted(imported_roots(p) & (FORBIDDEN_MODULES | {"<dynamic __import__>"}))
        for p in SRC.rglob("*.py")
    }
    assert {k: v for k, v in violations.items() if v} == {}
