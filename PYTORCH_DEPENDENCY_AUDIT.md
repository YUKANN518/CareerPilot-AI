# Phase 5.1 — PyTorch Dependency Audit

Audit date: 2026-09-17

## Direct dependency graph

- Before this phase, `torch` was **not** a direct dependency in `backend/pyproject.toml`.
- `sentence-transformers>=3.3,<6` is a direct dependency and brings in `torch` transitively.
- `torchvision` is not declared and is not present in the current lock graph.
- `torchaudio` is not declared and is not present in the current lock graph.
- The current lock resolves `sentence-transformers==5.7.0` → `torch==2.14.0`.
- `uv tree` confirms the relevant path: `sentence-transformers==5.7.0` → `torch==2.14.0`.
- To make source selection apply to the transitive runtime dependency, this phase explicitly pins
  the compatible `torch>=2.14,<2.15` range as a direct dependency. This makes the existing
  embedding dependency reproducible; it does not add an application capability.

## Why the Docker build downloaded CUDA

The pre-fix `uv.lock` records the PyPI `torch==2.14.0` package with Linux dependencies for:

- `cuda-bindings` and `cuda-toolkit`
- `nvidia-cublas`, `nvidia-cuda-*`, `nvidia-cudnn-cu13`, `nvidia-cufft`, `nvidia-curand`
- `nvidia-cusolver`, `nvidia-cusparse`, `nvidia-nccl-cu13`, `nvidia-nvshmem-cu13`, `nvidia-nvtx`
- `triton`

Those packages are transitive consequences of the default PyPI Linux PyTorch distribution, not
application imports. The locked torch Linux x86_64 wheel is approximately 555 MB before those
additional CUDA packages.

## Source audit for GPU requirements

- No `torch.cuda`, `cuda.is_available`, GPU-only inference, `torchvision`, or `torchaudio` usage
  exists in the application, tests, scripts, or evaluation code.
- `SentenceTransformersEmbeddingProvider` accepts a device but the project setting defaults to
  `embedding_device = "cpu"`; the Docker Demo uses `EMBEDDING_PROVIDER=fake` and CPU semantics.
- Sentence Transformers remains a real semantic-retrieval dependency and is not removed. Its
  lazy provider must continue to support CPU execution.

Conclusion: **Docker / Portfolio build only requires CPU PyTorch.** No GPU runtime is required by
the current source code or frozen product scope.

## CPU source validation before the change

`uv pip install --dry-run --python backend/.venv/Scripts/python.exe --index-url
https://download.pytorch.org/whl/cpu torch==2.14.0` reported that the CPU-index resolution is
available for the locked torch version. The source pinning change is applied in
`backend/pyproject.toml`; the regenerated lock and post-change checks are recorded in the Phase
5.1 report.

## Post-change lock result

The source pinning change is applied in `backend/pyproject.toml` using the official PyTorch CPU
wheel index `https://download.pytorch.org/whl/cpu`. The regenerated lock resolves Linux to
`torch==2.14.0+cpu` and contains no
`cuda-*`, `nvidia-*`, or `triton` packages. Wheel hashes for supported platforms are recorded in
`backend/uv.lock`; post-change sync, tests, and Docker checks are recorded in the Phase 5.1 report.
