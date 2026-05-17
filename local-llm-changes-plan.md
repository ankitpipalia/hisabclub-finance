# Local LLM Changes Plan

## Objective
Stop treating this repo as a partial LLM owner. Use `/home/ankit/Documents/local-llm` as the single shared model runtime and control plane.

## Current Problems
- `scripts/start-local-stack.sh` hardcodes:
  - `LLM_ROOT=/home/ankit/Documents/local-llm`
  - `DEFAULT_LLM_PORT=8472`
  - `DEFAULT_LLM_MODEL_PATH=.../Qwen3.5-27B-Q3_K_M.gguf`
- README still documents the old shared endpoint on `:8472`.
- The repo still contains app-local startup logic for the shared LLM.

## Target Contract
- source of truth:
  - `/home/ankit/Documents/local-llm/shared-local-llm.env`
  - `/home/ankit/Documents/local-llm/shared-local-llm.sh`
- text endpoint:
  - host: `http://127.0.0.1:8097/v1`
  - model: `Qwen3.6-27B-Q5_K_S.gguf`
- optional vision endpoint:
  - host: `http://127.0.0.1:8096/v1`

## Required Changes
1. Update `scripts/start-local-stack.sh`
   - remove `DEFAULT_LLM_PORT=8472`
   - remove `DEFAULT_LLM_MODEL_PATH=...`
   - source `/home/ankit/Documents/local-llm/shared-local-llm.env`
   - if the configured Qwen endpoint is down and startup validation is explicitly enabled, start it via:
     - `bash /home/ankit/Documents/local-llm/shared-local-llm.sh start qwen`
   - stop invoking `llama-turbo-cuda.sh` directly from this app

2. Normalize app env usage
   - standardize `LLM_BASE_URL` to `http://127.0.0.1:8097/v1`
   - standardize `LLM_MODEL` to `Qwen3.6-27B-Q5_K_S.gguf`
   - if this app adds multimodal parsing later, use:
     - `LOCAL_LLM_VISION_API_BASE=http://127.0.0.1:8096/v1`

3. Update documentation
   - in `README.md`, replace `:8472` references with `:8097`
   - document the shared runtime commands:
     - `bash /home/ankit/Documents/local-llm/shared-local-llm.sh start qwen`
     - `bash /home/ankit/Documents/local-llm/shared-local-llm.sh status qwen`
   - remove direct model-path ownership from the app README

4. Update repo guidance
   - in `AGENTS.md`, replace:
     - `/home/ankit/Documents/local-llm/llama-turbo-cuda.sh start`
   - with:
     - `/home/ankit/Documents/local-llm/shared-local-llm.sh start qwen`

## Integration Example
```bash
# host-native app startup
source /home/ankit/Documents/local-llm/shared-local-llm.env
export LLM_BASE_URL="$LOCAL_LLM_QWEN_HOST_API_BASE"
export LLM_MODEL="$LOCAL_LLM_QWEN_MODEL"
bash /home/ankit/Documents/local-llm/shared-local-llm.sh start qwen
```

## Expected End State
- this app does not own model ports or model file paths
- this app uses the shared Qwen text LLM through one shared command
- future apps can follow the same structure without copying custom llama startup logic
