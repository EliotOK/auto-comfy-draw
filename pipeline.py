#!/usr/bin/env python
"""Drive a local or remote ComfyUI server for text-to-image and image-to-image.

Modes:
  --discover            List ComfyUI's actually-usable models & LoRAs (for onboarding).
  --check [--config c]  Probe ComfyUI, verify the config's model exists, output dir writable.
  --scaffold ...        Write a config JSON from chosen model/LoRA/output (+ defaults).
  (default, needs --config)  Batch run txt2img/img2img.

Content-neutral: what a prompt describes is up to the caller.

Usage:
  python pipeline.py --discover
  python pipeline.py --check --config config.json
  python pipeline.py --scaffold --model foo.safetensors --lora bar.safetensors \\
      --output-dir C:/out --name demo --config config.demo.json
  python pipeline.py --config config.json --count 3 --prompt "a city at dusk"
  python pipeline.py --config config.json --init ref.png --denoise 0.6 --count 4
"""
import json, os, sys, time, random, subprocess, shlex, urllib.request, urllib.parse, argparse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORTS = (8188, 8189)

def log(msg): print(msg, flush=True)

def probe(host, port=None, ports=DEFAULT_PORTS):
    if port:
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/system_stats", timeout=5) as r:
                json.loads(r.read().decode("utf-8"))
            return port
        except Exception as e:
            raise SystemExit(f"ComfyUI not reachable at {host}:{port} ({e}).\n"
                             "Start ComfyUI first (Desktop or `python main.py`). "
                             "I can start it for you if you allow it (run with --start).")
    for p in ports:
        try:
            with urllib.request.urlopen(f"http://{host}:{p}/system_stats", timeout=5) as r:
                json.loads(r.read().decode("utf-8"))
            return p
        except Exception:
            continue
    raise SystemExit(f"ComfyUI not reachable on {host} ports {list(ports)}.\n"
                     "Start ComfyUI first (Desktop or `python main.py`). "
                     "With your consent I can launch it for you (run with --start).")

def api(base, path, data=None, timeout=20):
    try:
        if data is not None:
            req = urllib.request.Request(base + path, data=json.dumps(data).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        with urllib.request.urlopen(base + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} on {path}: {e.read().decode('utf-8','replace')[:500]}")
    except Exception as e:
        raise RuntimeError(f"request {path} failed: {e}")

def list_models(base, key, node):
    """Return the file list ComfyUI currently sees for a loadable folder."""
    info = api(base, f"/object_info/{node}")
    required = info[node]["input"]["required"]
    for k, v in required.items():
        if isinstance(v, list) and v and isinstance(v[0], list) and v[0]:
            return [x for x in v[0]]
    return []

# ---- onboarding modes ----
def cmd_discover(base):
    ck = list_models(base, "ckpt_name", "CheckpointLoaderSimple")
    lora = list_models(base, "lora_name", "LoraLoader")
    print("Available checkpoints:", len(ck))
    for x in ck: print("  -", x)
    print("Available LoRAs:", len(lora))
    for x in lora: print("  -", x)
    print("TIP: if a model/LoRA is missing, restart ComfyUI (new files are picked up on boot).")

def cmd_check(base, cfg_path):
    ok = True
    ck = list_models(base, "ckpt_name", "CheckpointLoaderSimple")
    if cfg_path:
        cfg = json.load(open(cfg_path, encoding="utf-8"))
        model = cfg.get("model")
        if model and model not in ck:
            print(f"[FAIL] model '{model}' not found in ComfyUI checkpoints.")
            ok = False
        else:
            print(f"[ok] model '{model}' found.")
        outdir = cfg.get("output_dir")
        if outdir:
            try:
                os.makedirs(outdir, exist_ok=True)
                print(f"[ok] output_dir writable: {outdir}")
            except Exception as e:
                print(f"[FAIL] output_dir not writable: {outdir}: {e}")
                ok = False
    else:
        print(f"[ok] ComfyUI reachable ({len(ck)} checkpoints, " +
              f"{len(list_models(base, 'lora_name', 'LoraLoader'))} LoRAs).")
    if not ok:
        sys.exit(1)
    print("ALL CHECKS PASSED")

def cmd_scaffold(args, base):
    ck = list_models(base, "ckpt_name", "CheckpointLoaderSimple")
    if args.model and args.model not in ck:
        print(f"[warn] model '{args.model}' not in current ComfyUI checkpoint list; it may need a restart.")
    cfg = {
        "name": args.name or "demo",
        "model": args.model,
        "lora": args.lora,
        "lora_strength": args.lora_strength,
        "positive": args.positive or "masterpiece, best quality, very aesthetic, absurdres",
        "negative": args.negative or ("lowres, bad anatomy, bad hands, extra fingers, extra limbs, mutated, "
                                      "deformed, blurry, jpeg artifacts, watermark, text, signature, logo, "
                                      "username, monochrome, low quality, worst quality"),
        "width": args.width, "height": args.height,
        "steps": args.steps, "cfg": args.cfg,
        "sampler": args.sampler, "scheduler": args.scheduler, "denoise": args.denoise,
        "start_cmd": getattr(args, "start_cmd", None) or "",
        "output_dir": args.output_dir,
        "prefix": args.prefix or f"{args.name or 'pipeline'}/pipeline",
        "prompts": [] if args.prompts is None else [{"name": f"p{i+1}", "prompt": p.strip()}
                                                    for i, p in enumerate(args.prompts.split("|")) if p.strip()],
    }
    target = args.config or f"config.{cfg['name']}.json"
    with open(target, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"[ok] wrote config -> {target}")

def cmd_start(args, host, ports=DEFAULT_PORTS):
    """Launch ComfyUI (only called after the user has consented) and wait until reachable."""
    cmd = args.start_cmd
    if not cmd and args.config:
        try:
            cmd = json.load(open(args.config, encoding="utf-8")).get("start_cmd")
        except Exception:
            pass
    if not cmd:
        raise SystemExit("--start needs --start-cmd '<launch command>' (or a config['start_cmd']).\n"
                         "If you'd rather start ComfyUI yourself, omit --start and open it manually.")
    print("starting ComfyUI:", cmd)
    try:
        subprocess.Popen(shlex.split(cmd), shell=False)
    except Exception as e:
        raise SystemExit(f"[FAIL] could not launch ComfyUI ({e}). Please start it manually, then re-run.")
    deadline = time.time() + 120
    while time.time() < deadline:
        for p in ([args.port] if args.port else list(ports)):
            try:
                with urllib.request.urlopen(f"http://{host}:{p}/system_stats", timeout=3) as r:
                    json.loads(r.read().decode("utf-8"))
                print(f"[ok] ComfyUI is up at {host}:{p}.")
                return
            except Exception:
                pass
        time.sleep(3)
    raise SystemExit("[timeout] ComfyUI did not become reachable in 120s. Please start it manually, then re-run.")

# ---- graph + run (unchanged logic) ----
def lora_nodes(cfg):
    if cfg.get("lora"):
        return {"2": {"class_type": "LoraLoader", "inputs": {"model": ["1", 0], "clip": ["1", 1],
                    "lora_name": cfg["lora"], "strength_model": cfg.get("lora_strength", 0.9),
                    "strength_clip": cfg.get("lora_strength", 0.9)}}}, ("2", 0), ("2", 1)
    return {}, ("1", 0), ("1", 1)

def build_graph(cfg, pos, seed, prefix, w, h, init=None, denoise=None):
    g = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": cfg["model"]}}}
    extra, model, clip = lora_nodes(cfg); g.update(extra)
    g["3"] = {"class_type": "CLIPTextEncode", "inputs": {"text": pos, "clip": clip}}
    g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": cfg.get("negative", ""), "clip": clip}}
    d = cfg.get("denoise", 1.0) if denoise is None else denoise
    if init:
        g["5"] = {"class_type": "LoadImage", "inputs": {"image": init}}
        g["6"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["1", 2]}}
        g["7"] = {"class_type": "KSampler", "inputs": {"model": model, "positive": ["3", 0], "negative": ["4", 0],
                  "latent_image": ["6", 0], "seed": seed, "steps": cfg.get("steps", 28), "cfg": cfg.get("cfg", 6.5),
                  "sampler_name": cfg.get("sampler", "dpmpp_2m"), "scheduler": cfg.get("scheduler", "karras"), "denoise": d}}
        g["8"] = {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}}
        g["9"] = {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}}
    else:
        g["5"] = {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
        g["6"] = {"class_type": "KSampler", "inputs": {"model": model, "positive": ["3", 0], "negative": ["4", 0],
                  "latent_image": ["5", 0], "seed": seed, "steps": cfg.get("steps", 28), "cfg": cfg.get("cfg", 6.5),
                  "sampler_name": cfg.get("sampler", "dpmpp_2m"), "scheduler": cfg.get("scheduler", "karras"), "denoise": d}}
        g["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}}
        g["8"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}}
    return g

def download(base, outdir, img):
    q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": "output"})
    data = urllib.request.urlopen(base + "/view?" + q, timeout=60).read()
    dest = os.path.join(outdir, img.get("subfolder", ""), img["filename"])
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f: f.write(data)
    return dest

def resolve_prompts(cfg, prompt, names):
    base = cfg.get("positive", "")
    if prompt is not None:
        return [f"p{i+1}" for i in range(len(prompt.split("|")))], [p.strip() for p in prompt.split("|") if p.strip()]
    cfg_prompts = cfg.get("prompts", [])
    if names is not None:
        wanted = [n.strip() for n in names.split(",")]
        picks = []
        for s in cfg_prompts:
            if isinstance(s, dict):
                if s.get("name") in wanted: picks.append((s["name"], s["prompt"]))
            else:
                if s in wanted: picks.append((s, s))
        if not picks: raise SystemExit(f"--names not found: {wanted}")
        return [n for n, _ in picks], [p for _, p in picks]
    if not cfg_prompts:
        return ["default"], [base]
    names_list, prompts_list = [], []
    for s in cfg_prompts:
        if isinstance(s, dict): names_list.append(s["name"]); prompts_list.append(s["prompt"])
        else: names_list.append(s); prompts_list.append(s)
    return names_list, prompts_list

def run(base, args, cfg):
    w, h = cfg.get("width", 832), cfg.get("height", 1216)
    outdir = cfg["output_dir"]; os.makedirs(outdir, exist_ok=True)
    prefix = cfg.get("prefix", cfg.get("name", "pipeline"))
    base_positive = cfg.get("positive", "")
    names_list, prompt_list = resolve_prompts(cfg, args.prompt, args.names)
    def pos_for(t): return ", ".join(x for x in (base_positive, t) if x)
    basis = args.seed_basis if args.seed_basis is not None else random.randrange(1, 2**31 - 1)
    jobs = []
    for idx, (name, txt) in enumerate(zip(names_list, prompt_list)):
        pos = pos_for(txt)
        base_seed = (basis + idx * 100000) if args.seed_basis is not None else random.randrange(1, 2**31 - 1)
        for k in range(args.count):
            seed = base_seed + k
            jobs.append({"name": name, "k": k + 1, "count": args.count, "seed": seed, "pos": pos,
                         "prefix": f"{prefix}/{name}_{seed}", "w": w, "h": h})
    ids = []
    for j in jobs:
        resp = api(base, "/prompt", {"prompt": build_graph(cfg, j["pos"], j["seed"], j["prefix"], j["w"], j["h"], args.init, args.denoise),
                                     "client_id": "auto-comfy-draw"})
        if "prompt_id" not in resp:
            raise SystemExit(f"/prompt validation failed: {json.dumps(resp, ensure_ascii=False)[:800]}")
        j["pid"] = resp["prompt_id"]; ids.append(j["pid"])
        log(f"[{j['name']}#{j['k']}/{j['count']}] queued pid={j['pid']} seed={j['seed']}")
    pending = set(ids); failures = []
    deadline = time.time() + 2400
    while pending and time.time() < deadline:
        for pid in list(pending):
            try:
                hist = api(base, "/history/" + pid, timeout=20)
            except Exception as e:
                log(f"poll error for {pid}: {e}"); continue
            if pid not in hist: continue
            entry = hist[pid]; status = (entry.get("status") or {}).get("status_str")
            if status == "error":
                msgs = []
                for nid, node in (entry.get("status") or {}).get("messages", []) if isinstance(entry.get("status"), dict) else []:
                    if isinstance(node, dict) and node.get("error"): msgs.append(str(node["error"]["message"])[:300])
                failures.append(pid); log(f"[error] pid={pid} failed: {' | '.join(msgs) if msgs else 'unknown'}")
                pending.discard(pid); continue
            outs = entry.get("outputs", {})
            if not outs:
                if status in ("success", "completed"):
                    failures.append(pid); log(f"[error] pid={pid} finished with no output")
                pending.discard(pid); continue
            for nid, out in outs.items():
                for img in out.get("images", []): log(f"SAVED: {download(base, outdir, img)}")
            pending.discard(pid)
        time.sleep(4)
    if pending:
        failures.extend(pending); log(f"[timeout] {len(pending)} unresolved")
    log(f"remaining: {len(pending)} failures: {len(failures)} DONE")
    if failures: sys.exit(1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="config JSON (required for run/check; target path for --scaffold)")
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--names", default=None)
    ap.add_argument("--init", default=None)
    ap.add_argument("--denoise", type=float, default=None)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--seed-basis", type=int, default=None)
    # onboarding modes
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--scaffold", action="store_true")
    ap.add_argument("--start", action="store_true", help="launch ComfyUI (only with user consent) then wait until reachable")
    ap.add_argument("--start-cmd", default=None, help="command to start ComfyUI, used with --start")
    # scaffold inputs
    ap.add_argument("--model", default=None)
    ap.add_argument("--lora", default=None)
    ap.add_argument("--lora-strength", type=float, default=0.9)
    ap.add_argument("--name", default=None)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--positive", default=None)
    ap.add_argument("--negative", default=None)
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=1216)
    ap.add_argument("--steps", type=int, default=28)
    ap.add_argument("--cfg", type=float, default=6.5)
    ap.add_argument("--sampler", default="dpmpp_2m")
    ap.add_argument("--scheduler", default="karras")
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--prompts", default=None, help="'|'-separated initial prompts for --scaffold")
    args = ap.parse_args()

    if args.start:
        cmd_start(args, args.host, DEFAULT_PORTS)
        return
    base = f"http://{args.host}:{probe(args.host, args.port)}"
    log(f"using {base}")
    if args.discover:
        cmd_discover(base); return
    if args.scaffold:
        if not args.model or not args.output_dir:
            raise SystemExit("--scaffold requires --model and --output-dir")
        cmd_scaffold(args, base); return
    if args.check:
        cmd_check(base, args.config); return
    if not args.config:
        raise SystemExit("--config is required to run (or use --discover/--scaffold/--check)")
    cfg = json.load(open(args.config, encoding="utf-8"))
    run(base, args, cfg)

if __name__ == "__main__":
    main()
