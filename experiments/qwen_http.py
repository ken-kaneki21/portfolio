"""Bounded native llama.cpp SSE benchmark. Python standard library only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import http.client
import json
from pathlib import Path
import statistics
import time

PROMPTS = [
    "Write one sentence explaining why a financial total may need adjustment after a monthly close.",
    "List three checks that help detect missing records in a synthetic claims dataset.",
    "Explain in two sentences the difference between a SQL count and a sum of amounts.",
    "Write a short caveat for a report calculated from synthetic financial records.",
]
SETTINGS = dict(n_predict=32, temperature=0.0, top_k=1, top_p=1.0,
                repeat_penalty=1.0, seed=42, cache_prompt=False, stream=True,
                return_tokens=True)
TIMEOUT_S = 30


def request(port, prompt, index):
    begin = time.perf_counter()
    first = headers = terminal = None
    status = None
    event_count = visible_bytes = 0
    ids = 0
    row = {"index": index, "prompt_sha256": sha256(prompt.encode()).hexdigest()}
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT_S)
    try:
        conn.request("POST", "/completion", json.dumps({"prompt": prompt, **SETTINGS}),
                     {"Content-Type": "application/json", "Accept": "text/event-stream",
                      "Connection": "close"})
        resp = conn.getresponse()
        status = resp.status
        headers = time.perf_counter()
        if status != 200 or "text/event-stream" not in resp.getheader("Content-Type", ""):
            raise ValueError("expected HTTP 200 and an SSE response")
        data = []
        while line := resp.readline(65537):
            observed = time.perf_counter()
            if observed - begin > TIMEOUT_S:
                raise TimeoutError("stream exceeded request budget")
            if len(line) > 65536:
                raise ValueError("oversized SSE line")
            line = line.rstrip(b"\r\n")
            if line.startswith(b"data:"):
                data.append(line[5:].lstrip(b" "))
            elif not line and data:
                payload = b"\n".join(data)
                data.clear()
                if payload == b"[DONE]":
                    break
                event = json.loads(payload)
                if not isinstance(event, dict):
                    raise ValueError("invalid SSE event shape")
                if event.get("error"):
                    raise ValueError("server error event")
                event_count += 1
                piece = event.get("content")
                tokens = event.get("tokens", [])
                if isinstance(tokens, list):
                    ids += len(tokens)
                if isinstance(piece, str) and piece:
                    if first is None:
                        first = observed
                    visible_bytes += len(piece.encode())
                if event.get("stop") is True:
                    terminal = event
                    break
        if terminal is None or first is None:
            raise ValueError("incomplete stream or no visible generated text")
        timings = terminal.get("timings", {})
        if not isinstance(timings, dict):
            raise ValueError("invalid server timings")
        count = timings.get("predicted_n")
        native_count = terminal.get("tokens_predicted")
        if count is None:
            count = native_count
        if type(count) is not int or not 0 < count <= SETTINGS["n_predict"]:
            raise ValueError("missing or invalid server-generated token count")
        if native_count is not None and native_count != count:
            raise ValueError("server token counters disagree")
        keys = ("cache_n", "prompt_n", "prompt_ms", "predicted_n", "predicted_ms",
                "predicted_per_second")
        row.update(generated_tokens=count, server_prompt_tokens=terminal.get("tokens_evaluated"),
                   server_decode={k: timings[k] for k in keys if k in timings},
                   stop_type=terminal.get("stop_type"), ok=True)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        row.update(ok=False, failure_type=type(exc).__name__, failure=str(exc))
    finally:
        end = time.perf_counter()
        conn.close()
    elapsed = end - begin
    row.update(http_status=status, client_completion_ms=elapsed * 1000,
               client_headers_ms=None if headers is None else (headers-begin)*1000,
               client_observed_ttft_ms=None if first is None else (first-begin)*1000,
               sse_events=event_count, stream_token_id_entries=ids, visible_bytes=visible_bytes)
    if row["ok"]:
        row["client_tokens_per_second_e2e"] = row["generated_tokens"] / elapsed
    return row


def workload(port, concurrency):
    # Keep the same ordered prompt sequence in both arms. Concurrency two
    # issues two client requests to the same one-slot server.
    start = time.perf_counter()
    prompts = PROMPTS * 2
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        rows = list(pool.map(lambda item: request(port, item[1], item[0]), enumerate(prompts)))
    elapsed = time.perf_counter() - start
    ok = [r for r in rows if r["ok"]]
    count = sum(r["generated_tokens"] for r in ok)
    median = lambda name: statistics.median(r[name] for r in ok) if ok else None
    rates = [r["server_decode"]["predicted_per_second"] for r in ok
             if "predicted_per_second" in r["server_decode"]]
    return dict(concurrency=concurrency, requests=len(rows), failures=len(rows)-len(ok),
                wall_seconds=elapsed, successful_generated_tokens=count,
                client_aggregate_tokens_per_second=count/elapsed if ok else None,
                median_client_ttft_ms=median("client_observed_ttft_ms"),
                median_client_completion_ms=median("client_completion_ms"),
                server_decode_rate_samples=len(rates),
                median_server_decode_tokens_per_second=statistics.median(rates) if rates else None,
                rows=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    # Reserve output before issuing requests and retain warmup failures.
    with args.out.open("x", encoding="utf-8") as out:
        warmups = [request(args.port, p, i) for i, p in enumerate(PROMPTS[:2])]
        arms = [workload(args.port, n) for n in (1, 2)] if all(r["ok"] for r in warmups) else []
        report = dict(model_sha256=args.model_sha256, image=args.image,
                      transport="real loopback HTTP SSE", endpoint="/completion",
                      workload_version="qwen-synthetic-finance-v1", prompts=PROMPTS,
                      decode=SETTINGS, request_budget_seconds=TIMEOUT_S,
                      server=dict(slots=1, context=2048, threads=5, gpu_layers=0),
                      warmups=warmups, arms=arms,
                      measurement="TTFT is first non-empty decoded text event at the client. "
                                  "Completion ends at the native terminal event. "
                                  "Server token counts and timings come from that event.")
        json.dump(report, out, indent=2, allow_nan=False)
    print(json.dumps({k: [{m: v for m, v in arm.items() if m != "rows"} for arm in arms]
                      if k == "arms" else report[k] for k in ("transport", "arms")}, indent=2))
    return 2 if not arms or any(arm["failures"] for arm in arms) else 0


if __name__ == "__main__":
    raise SystemExit(main())
