# auto-comfy-draw

[中文](README.md) | [English](README.en.md)

<p>
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.7%2B-blue.svg">
  <img alt="Backend: ComfyUI" src="https://img.shields.io/badge/Backend-ComfyUI-8A2BE2.svg">
</p>

An **agent skill** that drives a local or remote **ComfyUI** server for text-to-image and image-to-image generation.

You describe the image; the skill configures the ComfyUI workflow, builds the prompt, batch-runs it, and returns the saved outputs. Config-driven and content-neutral — what the prompt describes is entirely up to you.

## How to talk to your agent (suggested prompts)

You only **converse** — no need to type any CLI. `--discover` / `--scaffold` etc. are run by the agent under the hood. Just say:

- "Draw a city skyline at dusk"
- "Use waiIllustriousSDXL with LoRA xxx to draw a cat on a roof, output to D:/my_imgs, 4 images"
- "Make this ref.png more realistic" (img2img)
- "Change the seed / give me 4 more / add detail"

| What you say | What the agent does |
|---|---|
| "Draw a <description>" (first time) | scan available models → ask model/LoRA/output/ref image → build config → self-check → generate |
| "Use <model> <lora> to draw <description>" | build config and run with your description |
| "Change this image into <style>" | img2img (`--init` + `--denoise`) |
| "Change seed / add detail" | adjust `--seed-basis` / `--count` and re-run |

> The clearer your description (subject / style / composition / reference image), the closer the result. No CLI to memorize.

**Example output** (produced by this pipeline):

![example output](examples/example_output.png)

---

## What this is

- **`SKILL.md`** — the skill entry (frontmatter `name`/`description`), loaded by your agent so it knows how to set up the workflow and generate prompts on your behalf.
- **`pipeline.py`** — a harness-independent Python driver. It reads a config JSON, submits txt2img/img2img jobs, polls ComfyUI, downloads results, and reports errors.
- **`AGENTS.md`** — the same workflow for harnesses that auto-read `AGENTS.md` from the working directory.

## Requirements

- Python 3.7+
- A running ComfyUI (local or remote) with your models/LoRAs installed.
- `pipeline.py` only calls the ComfyUI HTTP API (`/prompt`, `/queue`, `/history`, `/view`); no other dependencies.

## Install as an agent skill

This is packaged as a **`SKILL.md` skill**, so "install" depends on your agent's skill mechanism:

1. **DSH / Anthropic-compatible loaders** — drop this repo (or just `SKILL.md` + `pipeline.py` + `config.example.json`) into the directory your harness scans for skills. The `SKILL.md` frontmatter (`name: auto-comfy-draw`, `description`) is what registers it, so the agent can invoke it by matching the request.
2. **Harnesses that auto-read `AGENTS.md`** — copy this repo's `AGENTS.md` into your project/workspace root; it is injected into agent context automatically and instructs the agent to use this workflow.
3. **Direct use** — `pipeline.py` is just a CLI; you can run it from a terminal without any agent.

> The exact skill-directory path varies by harness — check your agent's docs for where `SKILL.md` files are loaded from.
> In this repo, `config*.json` is git-ignored (keep only `config.example.json`); your real configs stay local.

## Quick start

```bash
# 1. See what ComfyUI can actually use
python pipeline.py --discover

# 2. Generate a config from your choices (model / lora / output dir)
python pipeline.py --scaffold --model sdxl_foo.safetensors --lora bar.safetensors \
    --output-dir D:/my_imgs --name demo --config config.demo.json

# 3. Self-check (ComfyUI reachable? model present? output dir writable?)
python pipeline.py --check --config config.demo.json

# 4. Generate
python pipeline.py --config config.demo.json --prompt "a city at dusk" --count 4
```

## Commands

| Mode | Purpose |
|---|---|
| `--discover` | List the checkpoints & LoRAs ComfyUI currently exposes. |
| `--scaffold --model <m> [--lora <l>] --output-dir <dir> [--name <n>] [--config <c>] [--prompts "a\|b"]` | Write a config JSON. |
| `--check [--config c]` | Verify ComfyUI reachable, model exists, output dir writable. |
| `--start [--start-cmd "<cmd>"]` | Launches ComfyUI and waits until reachable (**only after user consent**). |
| `--config c --count N [--prompt ...] [--names a,b] [--init ref.png --denoise 0.6] [--seed-basis N] [--host/--port]` | Batch run. |

Batch behavior: probe port (8188/8189) → submit all jobs → poll `/queue` + `/history/<pid>` → download to `output_dir` → exit non-zero on failure/timeout. Cancel a batch with `POST /queue {"clear": true}`.

## Prompt & config

`--prompt` takes prompt strings; separate **multiple prompts with `|`**. `--names a,b` runs named prompts from the config.

`config.example.json` fields: `name`, `model`, `lora`/`lora_strength`, `positive`, `negative`, `width/height`, `steps/cfg/sampler/scheduler/denoise`, `start_cmd`, `output_dir`, `prefix`, `prompts`.

- **img2img**: `--init <basename>` + `--denoise N` (put the reference image in ComfyUI's `input` dir).
- **Reproducible**: `--seed-basis N` → per-prompt seed = `N + index*100000 + k`.
- **Remote**: `--host/--port` to target a forwarded/tunneled ComfyUI; results are pulled back to `output_dir`.

## Auto-starting ComfyUI (consent-gated)

If ComfyUI isn't running, `--discover`/`--check` fail with a clear message. You can **let the agent start it for you**, but only after you agree:

- Ask first; if you consent, run `python pipeline.py --start --start-cmd "<comfyui launch command>"` (or set `start_cmd` in the config). It waits up to 120s for `/system_stats`.
- The agent must **never** auto-start without your consent; if you decline or it fails, start ComfyUI yourself and re-run.

## License

MIT (see `LICENSE`). This repo contains only tooling/documentation — no generated art or third-party assets.

## Example output

See [examples/example_output.png](examples/example_output.png) for one image produced by this pipeline.
