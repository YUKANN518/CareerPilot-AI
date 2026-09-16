# CareerPilot AI Architecture

CareerPilot is a modular FastAPI + Vue application. The diagram reflects the frozen portfolio
scope; optional integrations are shown explicitly and no unimplemented infrastructure is implied.

```mermaid
flowchart TD
    UI[Vue 3 Frontend]
    API[FastAPI API]
    RES[Resume Service\nPDF/DOCX extraction + evidence]
    AI[OpenAI-compatible Provider\nreal Resume parsing / Mock Demo]
    JOB[Structured Job Input\nmanual + CSV deterministic normalization]
    MATCH[Matching Engine\n6 dimensions + optional semantic signal]
    REPORT[Explainable Match Report\nblocking risk + evidence coverage]
    APP[Applications]
    RAG[Optional Career Assistant\nlocal retrieval + Fake/Dify]
    DB[(SQLite + private file storage)]
    FAISS[(FAISS index)]

    UI --> API
    API --> RES
    RES --> AI
    API --> JOB
    API --> MATCH
    MATCH --> REPORT
    REPORT --> APP
    API --> RAG
    RAG --> FAISS
    RES --> DB
    JOB --> DB
    MATCH --> DB
    REPORT --> DB
    APP --> DB
    RAG --> DB
```

## Core boundaries

- Resume parsing may use the configured OpenAI-compatible Provider; Demo Mode uses Mock output.
- Matching consumes confirmed resume evidence and structured Job Input. It does not require an
  LLM Job parser and remains deterministic/hybrid according to the frozen scoring policy.
- Applications are a lightweight state-tracking layer over persisted jobs and reports.

## Optional and hidden boundaries

- Career Assistant is an optional Dify integration. Local retrieval/citation logic remains in the
  backend; Fake mode is safe for Demo and CI.
- Resume Optimization and Chat Interview remain hidden experimental modules and are not part of
  the portfolio Core path.

