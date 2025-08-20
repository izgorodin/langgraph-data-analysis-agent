#!/usr/bin/env python3
"""
Simple hardcoded secret scanner to reduce false positives vs naive grep.
- Flags assignments of literal-looking secrets to sensitive keys
- Ignores environment variable reads and obviously masked values
- Scans only files under src/
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
    "credentials",
}


class SecretVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[tuple[str, int, str]] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        # Check targets for sensitive names
        for target in node.targets:
            name = None
            if isinstance(target, ast.Name):
                name = target.id
            elif isinstance(target, ast.Attribute):
                name = target.attr

            if name and name.lower() in SENSITIVE_KEYS:
                # Allow env-based assignment like os.getenv(...) or settings.*
                if isinstance(node.value, (ast.Call, ast.Attribute)):
                    self.generic_visit(node)
                    return
                # Literal string that looks like a secret
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    val = node.value.value
                    masked = {"***MASKED***", ""}
                    if val and val.strip() and val.strip() not in masked:
                        # Heuristic: long-ish strings without spaces
                        long_enough = len(val.strip()) >= 16
                        no_spaces = " " not in val.strip()
                        if long_enough and no_spaces:
                            sample = val[:6] + "…"
                            self.findings.append((name, node.lineno, sample))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Detect hardcoded secrets passed as args
        suspicious = {"configure", "Client", "OpenAI", "from_api_key"}
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id
        else:
            func_name = ""

        if func_name in suspicious:
            for kw in node.keywords or []:
                if kw.arg and kw.arg.lower() in SENSITIVE_KEYS:
                    if isinstance(kw.value, ast.Constant) and isinstance(
                        kw.value.value, str
                    ):
                        val = kw.value.value
                        if len(val) >= 16 and " " not in val:
                            sample = val[:6] + "…"
                            self.findings.append((kw.arg, node.lineno, sample))
        self.generic_visit(node)


def scan_file(path: Path) -> list[tuple[str, int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    v = SecretVisitor()
    v.visit(tree)
    return v.findings


def main() -> int:
    root = Path("src")
    if not root.exists():
        print("No src/ directory; skipping secret scan")
        return 0

    violations = []
    for p in root.rglob("*.py"):
        # Use POSIX-ish relative string to avoid Path.relative_to issues
        rel = str(p)
        for name, lineno, sample in scan_file(p):
            msg = (
                f"{rel}:{lineno}: Hardcoded secret-like value assigned to "
                f"'{name}' (sample: {sample})"
            )
            violations.append(msg)

    if violations:
        print("Potential hardcoded secrets found!\n")
        for v in violations:
            print(v)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
