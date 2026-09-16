"""Generate small, deterministic PDF/DOCX parsing fixtures for Phase 3.5.

The fixtures are synthetic and intentionally text-layer documents; no real candidate data
or AI provider is involved.  Keeping generation in a reviewed script makes the binary
fixtures reproducible without hand-editing compressed DOCX/PDF bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
from reportlab.lib.styles import getSampleStyleSheet  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

ROOT = Path(__file__).resolve().parents[1] / "dataset" / "parsing"
RESUME_SECTIONS = ["Summary", "Skills", "Projects", "Experience", "Education", "Languages"]

RESUMES = [
    ("R01", "pdf", "Ada Chen", ["Python", "FastAPI", "PostgreSQL"], RESUME_SECTIONS),
    ("R02", "pdf", "Bo Li", ["JavaScript", "React", "Git"], RESUME_SECTIONS),
    ("R03", "pdf", "Chloe Wong", ["Docker", "Kubernetes", "CI/CD"], RESUME_SECTIONS),
    ("R04", "pdf", "Dinesh Rao", ["SQL", "Python", "Data Analysis"], RESUME_SECTIONS),
    ("R05", "pdf", "Eva Sun", ["Machine Learning", "NLP", "Python"], RESUME_SECTIONS),
    ("R06", "docx", "Faye Zhang", ["Python", "SQL", "Git"], RESUME_SECTIONS),
    ("R07", "docx", "Gao Wei", ["Vue", "TypeScript", "RESTful API"], RESUME_SECTIONS),
    ("R08", "docx", "Hana Kim", ["Java", "Python"], RESUME_SECTIONS),
    ("R09", "docx", "Iris Lau", ["Project Management", "Communication"], RESUME_SECTIONS),
    ("R10", "docx", "Jun Wu", ["React", "JavaScript", "SQL"], RESUME_SECTIONS),
]

JOBS = [
    ("J01", "Backend Engineer", "Required: Python, FastAPI, and PostgreSQL. Docker is preferred.", ["Python", "FastAPI", "PostgreSQL"], ["Docker"]),
    ("J02", "Frontend Engineer", "Required: JavaScript and React. TypeScript is a nice to have.", ["JavaScript", "React"], ["TypeScript"]),
    ("J03", "Platform Engineer", "Must have Docker and Kubernetes. CI/CD is preferred.", ["Docker", "Kubernetes"], ["CI/CD"]),
    ("J04", "Data Analyst", "SQL and Python are required. Data Analysis is a plus.", ["SQL", "Python"], ["Data Analysis"]),
    ("J05", "NLP Engineer", "Natural language processing and Python are required. Machine Learning is preferred.", ["NLP", "Python"], ["Machine Learning"]),
    ("J06", "API Engineer", "Required: RESTful API and Git. FastAPI is preferred.", ["RESTful API", "Git"], ["FastAPI"]),
    ("J07", "Web Engineer", "Vue is required. TypeScript and JavaScript are preferred.", ["Vue"], ["TypeScript", "JavaScript"]),
    ("J08", "Software Engineer", "Python and SQL are mandatory; Git is a bonus.", ["Python", "SQL"], ["Git"]),
    ("J09", "Delivery Lead", "Project Management is required. Communication is preferred.", ["Project Management"], ["Communication"]),
    ("J10", "UI Engineer", "React and JavaScript are required; SQL is nice to have.", ["React", "JavaScript"], ["SQL"]),
]


def _resume_text(name: str, skills: list[str]) -> str:
    return "\n".join(
        [
            f"{name}",
            "Summary",
            "Software professional building reliable products and collaborating with teams.",
            "Skills",
            ", ".join(skills),
            "Projects",
            "Built a synthetic project with tests, documentation and a measurable release outcome.",
            "Experience",
            "Delivered a synthetic product project with measurable release improvements.",
            "Education",
            "Bachelor of Computer Science",
            "Languages",
            "English; Mandarin",
        ]
    )


def _write_pdf(path: Path, text: str) -> None:
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(path), pagesize=letter)
    story = []
    for line in text.splitlines():
        story.append(Paragraph(line, styles["BodyText"]))
        story.append(Spacer(1, 5))
    document.build(story)


def _write_docx(path: Path, text: str) -> None:
    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    document.save(str(path))


def main() -> None:
    resume_dir = ROOT / "resumes"
    job_dir = ROOT / "jobs"
    resume_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)
    expected_resumes: list[dict[str, object]] = []
    for case_id, file_format, name, skills, sections in RESUMES:
        text = _resume_text(name, skills)
        path = resume_dir / f"{case_id}.{file_format}"
        if file_format == "pdf":
            _write_pdf(path, text)
        else:
            _write_docx(path, text)
        expected_resumes.append(
            {
                "case_id": case_id,
                "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "format": file_format,
                "expected_sections": sections,
                "expected_skills": skills,
                "expected_structured": {
                    "education": "Bachelor of Computer Science",
                    "skills": skills,
                    "projects": "Built a synthetic project with tests and documentation.",
                    "experience": "Delivered a synthetic product project.",
                },
            }
        )
    expected_jobs: list[dict[str, object]] = []
    for case_id, title, requirements, required, preferred in JOBS:
        text = f"{title}\nRequirements\n{requirements}\nResponsibilities\nDeliver reliable work with the team."
        path = job_dir / f"{case_id}.txt"
        path.write_text(text, encoding="utf-8")
        expected_jobs.append(
            {
                "case_id": case_id,
                "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "title": title,
                "expected_required": required,
                "expected_preferred": preferred,
            }
        )
    (ROOT / "cases.json").write_text(
        json.dumps(
            {"dataset_version": "parsing-v1", "resumes": expected_resumes, "jobs": expected_jobs},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
