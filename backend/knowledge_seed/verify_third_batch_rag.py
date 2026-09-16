"""Run real Career Assistant acceptance questions for knowledge-seed batch three.

The script deliberately calls the running HTTP API rather than service internals.
Set ``CAREERPILOT_TEST_PASSWORD`` before execution; no credential is stored here.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import requests

BASE_URL = os.getenv("CAREERPILOT_API_URL", "http://127.0.0.1:8000/api")
EMAIL = os.getenv("CAREERPILOT_TEST_EMAIL", "admin@careerpilot.local")


@dataclass(frozen=True)
class AcceptanceCase:
    label: str
    question: str
    expected_document_ids: tuple[int, ...]
    expects_refusal: bool = False


CASES = (
    AcceptanceCase(
        "software_development",
        "软件开发岗位中，怎样用一个 API 项目证明接口、校验和测试能力？",
        (17,),
    ),
    AcceptanceCase(
        "data_analysis",
        "数据分析项目怎样展示数据清洗、SQL、图表和结论限制？",
        (18,),
    ),
    AcceptanceCase(
        "qa",
        "软件测试与 QA 应怎样用测试场景、缺陷报告和复测证明能力？",
        (19,),
    ),
    AcceptanceCase(
        "it_support",
        "IT Support 的工单记录应包含什么，何时需要升级问题？",
        (20,),
    ),
    AcceptanceCase(
        "business_analyst",
        "Business Analyst 如何用访谈和流程图把业务需求写成可确认的材料？",
        (21,),
    ),
    AcceptanceCase(
        "iang_single",
        "IANG 官方页面如何区分 non-local recent graduate 和 non-recent graduate 的申请安排？",
        (22,),
    ),
    AcceptanceCase(
        "role_selection",
        "初级 IT 岗位选择时，怎样比较软件开发、数据分析、QA、IT Support 和 Business Analyst？",
        (23,),
    ),
    AcceptanceCase(
        "workplace_basics",
        "入职前沟通与职场基本习惯中，怎样通过正式渠道确认事项？",
        (24,),
    ),
    AcceptanceCase(
        "cross_support_qa_ba",
        "IT Support 的工单排障、QA 的测试场景与缺陷报告、"
        "Business Analyst 的需求访谈与流程图，分别怎样作为项目证据？",
        # IT Support document explicitly contrasts its evidence with BA evidence;
        # the separate BA single-document case verifies the BA primary source.
        (19, 20),
    ),
    AcceptanceCase(
        "cross_development_data_qa",
        "软件开发、数据分析和软件测试分别适合用什么项目证明能力？",
        (17, 18, 19),
    ),
    AcceptanceCase(
        "iang_documents",
        "申请 IANG 时，官方页面提示非本地毕业生先核对哪些毕业证明和时间点？",
        (22,),
    ),
    AcceptanceCase(
        "unrelated",
        "CareerPilot 已部署到哪个云服务商？",
        (),
        expects_refusal=True,
    ),
)


def login() -> dict[str, str]:
    password = os.environ["CAREERPILOT_TEST_PASSWORD"]
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": EMAIL, "password": password},
        timeout=15,
    )
    response.raise_for_status()
    access_token = response.json()["data"]["tokens"]["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def wait_for_run(headers: dict[str, str], run_id: int) -> dict[str, object]:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        response = requests.get(
            f"{BASE_URL}/career-assistant/qa/{run_id}", headers=headers, timeout=15
        )
        response.raise_for_status()
        row = response.json()["data"]
        if row["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return row
        time.sleep(1)
    raise TimeoutError(f"QA run {run_id} did not finish in 120 seconds")


def run_case(headers: dict[str, str], case: AcceptanceCase) -> dict[str, object]:
    response = requests.post(
        f"{BASE_URL}/career-assistant/qa",
        headers=headers,
        json={"question": case.question, "scope": "knowledge"},
        timeout=15,
    )
    response.raise_for_status()
    created = response.json()["data"]
    row = wait_for_run(headers, int(created["id"]))
    citations = list(row.get("citations") or [])
    citation_ids = [int(citation["document_id"]) for citation in citations]
    expected_found = all(document_id in citation_ids for document_id in case.expected_document_ids)
    refusal_ok = (
        not citations
        and bool(row.get("answer"))
        and row["status"] == "SUCCEEDED"
        if case.expects_refusal
        else True
    )
    return {
        "label": case.label,
        "run_id": row["id"],
        "status": row["status"],
        "question": case.question,
        "answer": row.get("answer"),
        "citation_ids": citation_ids,
        "citations": [
            {
                "document_id": citation["document_id"],
                "title": citation["title"],
                "chunk_index": citation["chunk_index"],
                "score": citation["score"],
                "quote": citation["quote"],
            }
            for citation in citations
        ],
        "expected_document_ids": list(case.expected_document_ids),
        "expected_documents_found": expected_found,
        "refusal_ok": refusal_ok,
    }


def main() -> None:
    headers = login()
    selected_label = os.getenv("CAREERPILOT_ACCEPTANCE_CASE")
    selected_cases = (
        tuple(case for case in CASES if case.label == selected_label)
        if selected_label
        else CASES
    )
    if not selected_cases:
        raise ValueError(f"Unknown acceptance case: {selected_label}")
    results = [run_case(headers, case) for case in selected_cases]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    failed = [
        result
        for result in results
        if result["status"] != "SUCCEEDED"
        or not result["expected_documents_found"]
        or not result["refusal_ok"]
    ]
    if failed:
        raise SystemExit(f"Acceptance cases failed: {[row['label'] for row in failed]}")


if __name__ == "__main__":
    main()
