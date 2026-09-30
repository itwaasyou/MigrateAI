"""Bounded, deterministic repository scanners. Uploaded code is never executed."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from .models import AnalysisResult, Dependency, Evidence, FileInventory, RiskFactor

IGNORED = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".next",
    "coverage",
    "__pycache__",
}
EXT_LANG = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".cs": "C#",
    ".kt": "Kotlin",
}
MANIFESTS = {
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "pom.xml",
    "go.mod",
    "*.csproj",
    "build.gradle",
    "build.gradle.kts",
}
MAX_FILES = 20000
MAX_FILE_BYTES = 1_000_000


def _safe_files(root: Path) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    warnings: list[str] = []
    for path in root.rglob("*"):
        if any(part in IGNORED for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                warnings.append(
                    f"Skipped oversized file: {path.relative_to(root).as_posix()}"
                )
                continue
        except OSError:
            continue
        files.append(path)
        if len(files) >= MAX_FILES:
            warnings.append(f"File scan capped at {MAX_FILES} files.")
            break
    return files, warnings


def analyze_repository(root: Path) -> AnalysisResult:
    files, warnings = _safe_files(root)
    languages: Counter[str] = Counter()
    technologies: set[str] = set()
    hints: set[str] = set()
    dependencies: list[Dependency] = []
    db_access: list[Evidence] = []
    routes: list[Evidence] = []
    parsed = 0
    unsupported = 0
    complexity: Counter[str] = Counter()
    incoming: Counter[str] = Counter()
    file_inventory: list[FileInventory] = []

    for path in files:
        rel = path.relative_to(root).as_posix()
        ext = path.suffix.lower()
        language = EXT_LANG.get(ext)
        recognized = (
            language is not None
            or path.name in MANIFESTS
            or path.name.endswith(".csproj")
        )
        try:
            content = path.read_bytes()
        except OSError:
            warnings.append(f"Could not read {rel}.")
            file_inventory.append(
                FileInventory(
                    path=rel,
                    language=language,
                    size_bytes=0,
                    status="read_error",
                )
            )
            continue
        if not recognized:
            unsupported += 1
            file_inventory.append(
                FileInventory(
                    path=rel,
                    size_bytes=len(content),
                    sha256=hashlib.sha256(content).hexdigest(),
                    status="unsupported",
                )
            )
            continue
        if ext in EXT_LANG:
            languages[EXT_LANG[ext]] += 1
        text = content.decode("utf-8", errors="replace")
        parsed += 1
        inventory_item = FileInventory(
            path=rel,
            language=language,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            line_count=len(text.splitlines()),
            status="parsed",
        )
        file_inventory.append(inventory_item)
        if path.name == "package.json":
            try:
                package = json.loads(text)
                technologies.update(package.get("dependencies", {}).keys())
                technologies.update(package.get("devDependencies", {}).keys())
            except (ValueError, AttributeError):
                warnings.append(f"Malformed dependency manifest: {rel}")
        elif path.name in {
            "requirements.txt",
            "pyproject.toml",
            "pom.xml",
            "go.mod",
        } or path.name.endswith(".csproj"):
            if path.name == "requirements.txt":
                technologies.update(
                    re.split(r"[<=>~!\[]", line.strip())[0]
                    for line in text.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                )
                technologies.discard("")
            elif path.name == "go.mod":
                technologies.update(re.findall(r"(?m)^\s*([\w./-]+)\s+v[\w.+-]+", text))
            elif path.name == "pom.xml":
                technologies.update(
                    re.findall(r"<artifactId>\s*([^<]+)\s*</artifactId>", text)
                )
            elif path.name.endswith(".csproj"):
                technologies.update(
                    re.findall(r"PackageReference\s+Include=[\"']([^\"']+)", text, re.I)
                )
            else:
                technologies.add(path.name)
        if path.name in {"manage.py", "app.py", "main.py"} and "FastAPI" in text:
            technologies.add("FastAPI")

        if ext == ".py":
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError:
                warnings.append(f"Python syntax could not be parsed: {rel}")
                inventory_item.status = "parse_error"
                parsed -= 1
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        [a.name for a in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                    for name in names:
                        target = name.split(".")[0]
                        dependencies.append(
                            Dependency(
                                source=rel,
                                target=target,
                                kind="import",
                                evidence=Evidence(
                                    file=rel,
                                    start_line=node.lineno,
                                    end_line=node.end_lineno or node.lineno,
                                    kind="import",
                                    detail=f"Imports {name}",
                                ),
                            )
                        )
                        incoming[target] += 1
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    complexity[rel] += sum(
                        isinstance(
                            n,
                            (
                                ast.If,
                                ast.For,
                                ast.While,
                                ast.Try,
                                ast.BoolOp,
                                ast.ExceptHandler,
                            ),
                        )
                        for n in ast.walk(node)
                    )
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ) and re.search(r"route|endpoint|api", node.name, re.I):
                    routes.append(
                        Evidence(
                            file=rel,
                            start_line=node.lineno,
                            end_line=node.end_lineno or node.lineno,
                            kind="route-candidate",
                            detail=f"Route-like symbol {node.name}; verify framework registration.",
                        )
                    )
        else:
            for line_no, line in enumerate(text.splitlines(), 1):
                for match in re.finditer(
                    r"(?:from|import)\s+[\w.]+|require\(['\"]([^'\"]+)['\"]\)|(?:fetch|axios\.[a-z]+)\s*\(",
                    line,
                ):
                    detail = match.group(0)
                    target = (match.group(1) or detail.split()[-1]).strip("'\";")
                    dependencies.append(
                        Dependency(
                            source=rel,
                            target=target,
                            kind="import",
                            evidence=Evidence(
                                file=rel,
                                start_line=line_no,
                                end_line=line_no,
                                kind="import",
                                detail=detail,
                            ),
                        )
                    )
                    incoming[target] += 1
                if re.search(
                    r"\b(app|router)\.(get|post|put|patch|delete)\s*\(", line
                ) or re.search(r"@(Get|Post|Put|Patch|Delete)Mapping", line):
                    routes.append(
                        Evidence(
                            file=rel,
                            start_line=line_no,
                            end_line=line_no,
                            kind="api-route",
                            detail=line.strip()[:240],
                        )
                    )
                if re.search(
                    r"(mongoose|MongoClient|createConnection|\.collection\(|\.find\(|@Entity|PrismaClient|sequelize)",
                    line,
                    re.I,
                ):
                    db_access.append(
                        Evidence(
                            file=rel,
                            start_line=line_no,
                            end_line=line_no,
                            kind="database-access",
                            detail=line.strip()[:240],
                        )
                    )

    names = {p.name for p in files}
    if "package.json" in names:
        technologies.add("Node.js")
    if any(p.name in {"pom.xml", "build.gradle", "build.gradle.kts"} for p in files):
        technologies.add("Java/JVM")
    if "Dockerfile" in names or "docker-compose.yml" in names:
        hints.add("containerized deployment")
    if any("frontend" in p.parts or "client" in p.parts for p in files) and any(
        "backend" in p.parts or "server" in p.parts for p in files
    ):
        hints.add("frontend/backend separation")
    if any(p.name in {"manage.py", "settings.py"} for p in files):
        hints.add("framework-managed application")
    directories = {part.lower() for path in files for part in path.parts[:-1]}
    if {"controllers", "services", "repositories"}.issubset(directories):
        hints.add("layered architecture signals")
    if {"controllers", "models", "views"}.issubset(directories):
        hints.add("MVC structure signals")
    if any("serverless" in path.name.lower() for path in files):
        hints.add("serverless configuration signal")
    if db_access:
        hints.add("database-backed application")
    if not hints:
        hints.add("architecture not confidently classified from scanned signals")

    risks: list[RiskFactor] = []
    if db_access:
        risks.append(
            RiskFactor(
                name="Database migration surface",
                score=min(90, 25 + len(db_access) * 3),
                detail=f"Found {len(db_access)} database-access code locations; validate query and schema compatibility.",
                evidence=db_access[:20],
            )
        )
    if warnings:
        risks.append(
            RiskFactor(
                name="Analysis coverage",
                score=min(85, 20 + len(warnings) * 10),
                detail=f"{len(warnings)} files or scans produced warnings; findings may be incomplete.",
            )
        )
    if dependencies:
        risks.append(
            RiskFactor(
                name="Dependency coupling",
                score=min(80, 15 + max(incoming.values(), default=0) * 5),
                detail=f"Scanned {len(dependencies)} import edges; high fan-in can increase migration coordination.",
                evidence=[
                    edge.evidence
                    for edge in dependencies
                    if incoming[edge.target] == max(incoming.values(), default=0)
                ][:20],
            )
        )

    total_branch_points = sum(complexity.values())
    if total_branch_points >= 10:
        risks.append(
            RiskFactor(
                name="Python branch complexity",
                score=min(85, 20 + total_branch_points * 2),
                detail=f"Python AST scan found {total_branch_points} branching constructs; review these paths when changing behavior.",
            )
        )

    return AnalysisResult(
        status="incomplete" if warnings else "completed",
        repository_name=root.name,
        file_count=len(files),
        parsed_file_count=parsed,
        unsupported_file_count=unsupported,
        languages=dict(languages),
        technologies=sorted(technologies),
        architecture_hints=sorted(hints),
        dependencies=dependencies[:5000],
        database_access=db_access[:2000],
        api_routes=routes[:2000],
        risks=risks,
        warnings=warnings,
        file_inventory=file_inventory,
    )


def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
