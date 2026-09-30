from pydantic import BaseModel, Field


class Evidence(BaseModel):
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    kind: str
    detail: str


class Dependency(BaseModel):
    source: str
    target: str
    kind: str
    evidence: Evidence


class RiskFactor(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)
    detail: str
    evidence: list[Evidence] = Field(default_factory=list)


class FileInventory(BaseModel):
    path: str
    language: str | None = None
    size_bytes: int
    sha256: str | None = None
    line_count: int | None = None
    status: str


class AnalysisResult(BaseModel):
    status: str
    repository_name: str
    file_count: int
    parsed_file_count: int
    unsupported_file_count: int
    languages: dict[str, int]
    technologies: list[str]
    architecture_hints: list[str]
    dependencies: list[Dependency]
    database_access: list[Evidence]
    api_routes: list[Evidence]
    risks: list[RiskFactor]
    warnings: list[str]
    file_inventory: list[FileInventory] = Field(default_factory=list)
