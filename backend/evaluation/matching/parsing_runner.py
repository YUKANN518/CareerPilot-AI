"""Deterministic text-layer and requirement parsing evaluation for Phase 3.5."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.files.extraction import ResumeTextExtractor
from app.matching.normalization import SkillNormalizationService
from app.matching.requirements import JobRequirementExtractor
from app.models.jobs import Job


def _canonical(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def run(input_path: Path) -> dict[str, object]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    normalizer = SkillNormalizationService()
    extractor = ResumeTextExtractor()
    resume_results: list[dict[str, object]] = []
    for case in payload["resumes"]:
        path = input_path.parent / case["file"]
        output = extractor.extract(path, case["format"])
        found = {item[3].normalized_name for item in normalizer.find_mentions(output.raw_text)}
        sections = {
            line.strip().casefold()
            for line in output.raw_text.splitlines()
            if line.strip()
        }
        attached = {
            skill
            for skill in case["expected_skills"]
            if any(_canonical(skill) in _canonical(block.text) for block in output.blocks)
        }
        resume_results.append(
            {
                "case_id": case["case_id"],
                "format": case["format"],
                "extraction_success": bool(output.raw_text.strip()),
                "block_count": len(output.blocks),
                "found_skills": sorted(found),
                "expected_skills": case["expected_skills"],
                "expected_structured": case["expected_structured"],
                "expected_sections": case["expected_sections"],
                "found_sections": sorted(
                    section
                    for section in case["expected_sections"]
                    if section.casefold() in sections
                ),
                "evidence_attached_skills": sorted(attached),
            }
        )

    job_results: list[dict[str, object]] = []
    for case in payload["jobs"]:
        path = input_path.parent / case["file"]
        text = path.read_text(encoding="utf-8")
        job = Job(
            id=10000 + int(str(case["case_id"])[1:]),
            title=str(case["title"]),
            company="Synthetic Parsing Company",
            requirements=text,
            description=text,
            responsibilities="Deliver reliable work with the team.",
            content_hash=(str(case["case_id"]) * 64)[:64],
            raw_data={},
            status="ACTIVE",
        )
        requirements = JobRequirementExtractor(normalizer).extract(job)
        detected_required = sorted(
            item.normalized_name for item in requirements.skills if item.required
        )
        detected_preferred = sorted(
            item.normalized_name for item in requirements.skills if not item.required
        )
        job_results.append(
            {
                "case_id": case["case_id"],
                "extraction_success": bool(text.strip()),
                "detected_required": detected_required,
                "detected_preferred": detected_preferred,
                "expected_required": case["expected_required"],
                "expected_preferred": case["expected_preferred"],
            }
        )
    return {
        "dataset_version": payload["dataset_version"],
        "resume_results": resume_results,
        "job_results": job_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run parsing-v1 evaluation")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"dataset_version": result["dataset_version"]}))


if __name__ == "__main__":
    main()
