# Existing reproducible experiments

These are the original synthetic retrieval, educational decoder/LoRA, scratch-ASGI
and pretrained HTTP serving harnesses. They were copied byte-for-byte from the
reviewed companion source; adding them is not a new benchmark run or a model release.
Synthetic fixtures are included; model weights and dependencies are not.

## Retrieval
Use Python 3.13 and an installed Job Intelligence environment with its dependencies,
including NumPy, psutil, PyTorch and Sentence Transformers. Clone job-portal
separately. Historical retrieval used source 3d3c02b and the cached MiniLM revision
identified in the raw report; current main is a different source revision.
Run `python experiments/retrieval.py --help` for required checkout, local encoder
and fresh report arguments. The encoder is loaded with local_files_only and the
script enables offline Hugging Face mode. Read the raw report for exact historical
config/hardware. Do not compare changed source/dependencies as the same trial.

## Educational decoder and LoRA
`adaptation.py` uses `extraction-v1.json`, `tiny_decoder.py` and a separately cloned
Job Intelligence checkout. It recreates scratch weights locally, not pretrained
adaptation. `serving.py --asgi-only` measures before TCP; omitting that flag requires
working local sockets. Read each --help. The historical adapter was rejected.
The held-out set has already been examined; it is not fresh for further tuning.

## Actual pretrained Qwen HTTP SSE
`qwen_http.py` uses Python's standard library. `../tools/run-qwen-http.ps1` checks
the accepted local GGUF hash and pinned cached llama.cpp image, creates an isolated
one-slot CPU server on a disposable loopback port, and preserves raw requests.
Provide ModelFile, Python and a new OutputDirectory to that runner. It does not
download weights/images or require an API key. The original accepted numbers are
in ../evidence/qwen-http-benchmark.json. Do not rerun solely to refresh a date.

Every run must use a fresh output. Authored fixtures, exact scope and negative
results remain explicit. Original personal harness source is MIT under the root
licence; installed libraries/model/image rights remain with their owners.
