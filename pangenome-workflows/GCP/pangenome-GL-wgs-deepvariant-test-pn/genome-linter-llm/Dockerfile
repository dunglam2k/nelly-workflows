# Local-LLM genome-linter: grounded narrative from Exomiser output. No network at
# run time (model is baked in), so it replaces the OpenRouter dependency.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl build-essential cmake && rm -rf /var/lib/apt/lists/*

# Build llama-cpp-python from source against this image's glibc (the prebuilt
# CPU wheels are musl-linked and will not load on Debian). CPU-only build.
ENV CMAKE_ARGS="-DGGML_NATIVE=OFF"
RUN pip install --no-cache-dir "llama-cpp-python==0.3.2"

# Bake a small, strong instruction-following model. Default: Qwen2.5-3B-Instruct
# Q4_K_M (single-file GGUF, ~1.9 GB) -- fast on CPU and strong enough for grounded
# summarisation. Swap MODEL_URL at build time for a larger model (e.g. the 7B, or
# a MedGemma GGUF) without changing the workflow.
ARG MODEL_URL=https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf
RUN mkdir -p /model && curl -fL --retry 8 -o /model/model.gguf "${MODEL_URL}"
ENV GL_MODEL_PATH=/model/model.gguf

COPY blurb.py /app/blurb.py
WORKDIR /work
# No ENTRYPOINT: CWL supplies the command (baseCommand: [python, /app/blurb.py]).
# An ENTRYPOINT would be prepended to the CWL command by the Arvados runtime.
CMD ["python"]
