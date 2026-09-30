from pathlib import Path

from .db import SessionLocal
from .entities import (
    AnalysisArtifact,
    AnalysisRun,
    DependencyEdge,
    EvidenceRecord,
    Repository,
    RepositoryFile,
    RiskRecord,
)


def analyze_run(analysis_id: str) -> None:
    from .analyzer import analyze_repository

    with SessionLocal() as db:
        run = db.get(AnalysisRun, analysis_id)
        if run is None:
            return
        run.status, run.stage = "running", "repository_scan"
        db.commit()
        repo = db.get(Repository, run.repository_id)
        if repo is None:
            run.status, run.error_message = (
                "failed",
                "Repository source is unavailable.",
            )
            db.commit()
            return
        try:
            result = analyze_repository(Path(repo.source_path))
            run.result = result.model_dump(mode="json")
            run.status = "incomplete" if result.status == "incomplete" else "completed"
            run.stage = "complete"
            db.add_all(
                RepositoryFile(analysis_id=run.id, **item.model_dump())
                for item in result.file_inventory
            )
            db.add_all(
                DependencyEdge(
                    analysis_id=run.id,
                    source_path=edge.source,
                    target=edge.target,
                    kind=edge.kind,
                    start_line=edge.evidence.start_line,
                    end_line=edge.evidence.end_line,
                )
                for edge in result.dependencies
            )
            file_hashes = {item.path: item.sha256 for item in result.file_inventory}
            evidence = [
                *[("database", item) for item in result.database_access],
                *[("api", item) for item in result.api_routes],
                *[(risk.name, item) for risk in result.risks for item in risk.evidence],
            ]
            db.add_all(
                EvidenceRecord(
                    analysis_id=run.id,
                    file_path=item.file,
                    start_line=item.start_line,
                    end_line=item.end_line,
                    evidence_type=kind,
                    detail=item.detail,
                    content_hash=file_hashes.get(item.file),
                )
                for kind, item in evidence
            )
            db.add_all(
                RiskRecord(
                    analysis_id=run.id,
                    name=risk.name,
                    score=risk.score,
                    detail=risk.detail,
                    factors=[item.model_dump(mode="json") for item in risk.evidence],
                )
                for risk in result.risks
            )
            db.add(
                AnalysisArtifact(
                    analysis_id=run.id,
                    artifact_type="summary",
                    payload={
                        "languages": result.languages,
                        "technologies": result.technologies,
                        "architecture_hints": result.architecture_hints,
                        "warnings": result.warnings,
                    },
                )
            )
            db.commit()
        except Exception:
            run.status, run.stage = "failed", "failed"
            run.error_message = (
                "Repository scan failed. Check that the uploaded archive is readable."
            )
            db.commit()
