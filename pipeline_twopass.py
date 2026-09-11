#!/usr/bin/env python
"""Two-pass driver: txt2img -> Impact Pack detail passes -> optional ESRGAN upscale.

Reads the SAME config JSON format as pipeline.py and adds an optional "detail"
block (every field has a default, so existing configs work unchanged):

  "detail": {
    "face":    {"enabled": true, "detector": "bbox/face_yolov8m.pt",
                "sam": "sam_vit_b_01ec64.pth",
                "guide_size": 512, "max_size": 1024, "denoise": 0.45,
                "steps": 20, "cfg": 6.5, "feather": 8,
                "bbox_threshold": 0.5, "bbox_dilation": 10, "bbox_crop_factor": 3.0},
    "hand":    {"enabled": true, "detector": "bbox/hand_yolov8s.pt",
                "guide_size": 384, "max_size": 768, "denoise": 0.45,
                "steps": 20, "cfg": 6.5, "feather": 8,
                "threshold": 0.5, "dilation": 10, "crop_factor": 3.0},
    "upscale": {"enabled": false, "model": "RealESRGAN_x4plus_anime_6B.pth",
                "target_width": 2048}
  }

All passes live in ONE /prompt submission per image (no file round-trip).
Detailer seeds are derived from the image seed (seed+1 face, seed+2 hand), so a
given --seed-basis records the seeds of the whole chain; pixel identity is not guaranteed.
Content-neutral: all prompt text comes from the config or the CLI.
"""
import argparse, json, os, random, re, sys, time, urllib.parse, urllib.request

from pathlib import Path
from pipeline_common import (resolve_prompts, split_prompts, expand_prompt, normalize_config,
                             validate_run, check_output, preflight, validate_graphs)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORTS = (8188, 8189)

FACE_DEFAULTS = dict(enabled=True, detector="bbox/face_yolov8m.pt", sam="sam_vit_b_01ec64.pth",
                      guide_size=512, max_size=1024, denoise=0.45, steps=20, cfg=6.5, feather=8,
                      bbox_threshold=0.5, bbox_dilation=10, bbox_crop_factor=3.0)
HAND_DEFAULTS = dict(enabled=True, detector="bbox/hand_yolov8s.pt",
                     guide_size=384, max_size=768, denoise=0.45, steps=20, cfg=6.5, feather=8,
                     threshold=0.5, dilation=10, crop_factor=3.0)
UPSCALE_DEFAULTS = dict(enabled=False, model="RealESRGAN_x4plus_anime_6B.pth", target_width=2048)


def log(m): print(m, flush=True)

BRACE_RE = re.compile(r"\{([^{}]*)\}")

def brace_options(text):
    """Option lists for each {a|b|c} group in text, in order. No nesting support."""
    return [m.group(1).split("|") for m in BRACE_RE.finditer(text)]

def expand_braces(text, choices):
    it = iter(choices)
    return BRACE_RE.sub(lambda m: next(it, m.group(0)), text)

def branch_tag(choices):
    """Shorthand for a branch choice, safe to use inside a filename."""
    parts = []
    for c in choices:
        head = c.split(",")[0].strip()
        m = re.match(r"^\(([^:)]+):", head)   # "(wariza:1.3)" -> "wariza"
        if m:
            head = m.group(1)
        head = re.sub(r"[^A-Za-z0-9._-]+", "-", head).strip("-")
        parts.append(head[:20])
    return "_".join(x for x in parts if x)


def probe(host, port=None, ports=DEFAULT_PORTS):
    cands = [port] if port else list(ports)
    for p in cands:
        try:
            with urllib.request.urlopen("http://%s:%d/system_stats" % (host, p), timeout=5) as r:
                json.loads(r.read().decode("utf-8"))
            return "http://%s:%d" % (host, p)
        except Exception:
            continue
    raise SystemExit("ComfyUI not reachable at %s ports %s. Start it first." % (host, cands))


def api(base, path, data=None, timeout=30):
    if data is None:
        with urllib.request.urlopen(base + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    req = urllib.request.Request(base + path, data=json.dumps(data).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def download(base, outdir, img):
    q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                "type": img.get("type", "output")})
    data = urllib.request.urlopen(base + "/view?" + q, timeout=120).read()
    dest = os.path.join(outdir, img.get("subfolder", ""), img["filename"])
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)   # atomic: never leave a half-written image
    return dest


def merge(defaults, override):
    d = dict(defaults)
    if override:
        d.update({k: v for k, v in override.items() if v is not None})
    return d


def detail_cfg(cfg, args):
    raw = cfg.get("detail") or {}
    face = merge(FACE_DEFAULTS, raw.get("face"))
    hand = merge(HAND_DEFAULTS, raw.get("hand"))
    up = merge(UPSCALE_DEFAULTS, raw.get("upscale"))
    if args.no_face: face["enabled"] = False
    if args.no_hand: hand["enabled"] = False
    if args.upscale: up["enabled"] = True
    if args.no_upscale: up["enabled"] = False
    if args.face_denoise is not None: face["denoise"] = args.face_denoise
    if args.hand_denoise is not None: hand["denoise"] = args.hand_denoise
    if args.upscale_width is not None: up["target_width"] = args.upscale_width
    normalize_config(dict(cfg, detail={"face": face, "hand": hand, "upscale": up}))
    return face, hand, up


def build_graph(cfg, pos, seed, prefix, w, h, face, hand, up):
    g = {}
    g["1"] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": cfg["model"]}}
    model, clip = ["1", 0], ["1", 1]
    if cfg.get("lora"):
        s = cfg.get("lora_strength", 0.9)
        g["2"] = {"class_type": "LoraLoader",
                  "inputs": {"model": model, "clip": clip, "lora_name": cfg["lora"],
                             "strength_model": s, "strength_clip": s}}
        model, clip = ["2", 0], ["2", 1]
    vae = ["1", 2]
    g["3"] = {"class_type": "CLIPTextEncode", "inputs": {"text": pos, "clip": clip}}
    g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": cfg.get("negative", ""), "clip": clip}}
    g["5"] = {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
    g["6"] = {"class_type": "KSampler",
              "inputs": {"model": model, "positive": ["3", 0], "negative": ["4", 0],
                         "latent_image": ["5", 0], "seed": seed,
                         "steps": cfg.get("steps", 28), "cfg": cfg.get("cfg", 6.5),
                         "sampler_name": cfg.get("sampler", "dpmpp_2m"),
                         "scheduler": cfg.get("scheduler", "karras"),
                         "denoise": cfg.get("denoise", 1.0)}}
    g["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": vae}}
    img = ["7", 0]
    state = {"n": 10}

    def nn():
        state["n"] += 1
        return str(state["n"])

    passes = []
    if face.get("enabled"):
        det = nn()
        g[det] = {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": face["detector"]}}
        sam_id = None
        if face.get("sam"):
            sam_id = nn()
            g[sam_id] = {"class_type": "SAMLoader",
                         "inputs": {"model_name": face["sam"], "device_mode": "AUTO"}}
        fd = nn()
        inp = {"image": img, "model": model, "clip": clip, "vae": vae,
               "guide_size": float(face["guide_size"]), "guide_size_for": True,
               "max_size": float(face["max_size"]), "seed": seed + 1,
               "steps": int(face["steps"]), "cfg": float(face["cfg"]),
               "sampler_name": cfg.get("sampler", "dpmpp_2m"),
               "scheduler": cfg.get("scheduler", "karras"),
               "positive": ["3", 0], "negative": ["4", 0],
               "denoise": float(face["denoise"]), "feather": int(face["feather"]),
               "noise_mask": True, "force_inpaint": True,
               "bbox_threshold": float(face["bbox_threshold"]),
               "bbox_dilation": int(face["bbox_dilation"]),
               "bbox_crop_factor": float(face["bbox_crop_factor"]),
               "sam_detection_hint": "center-1", "sam_dilation": 0, "sam_threshold": 0.93,
               "sam_bbox_expansion": 0, "sam_mask_hint_threshold": 0.7,
               "sam_mask_hint_use_negative": "False", "drop_size": 10,
               "bbox_detector": [det, 0], "wildcard": "", "cycle": 1}
        if sam_id:
            inp["sam_model_opt"] = [sam_id, 0]
        g[fd] = {"class_type": "FaceDetailer", "inputs": inp}
        img = [fd, 0]
        passes.append("face")
    if hand.get("enabled"):
        det = nn()
        g[det] = {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": hand["detector"]}}
        segs = nn()
        g[segs] = {"class_type": "BboxDetectorSEGS",
                   "inputs": {"bbox_detector": [det, 0], "image": img,
                              "threshold": float(hand["threshold"]),
                              "dilation": int(hand["dilation"]),
                              "crop_factor": float(hand["crop_factor"]),
                              "drop_size": 10, "labels": "all"}}
        df = nn()
        g[df] = {"class_type": "DetailerForEach",
                 "inputs": {"image": img, "segs": [segs, 0], "model": model, "clip": clip, "vae": vae,
                            "guide_size": float(hand["guide_size"]), "guide_size_for": True,
                            "max_size": float(hand["max_size"]), "seed": seed + 2,
                            "steps": int(hand["steps"]), "cfg": float(hand["cfg"]),
                            "sampler_name": cfg.get("sampler", "dpmpp_2m"),
                            "scheduler": cfg.get("scheduler", "karras"),
                            "positive": ["3", 0], "negative": ["4", 0],
                            "denoise": float(hand["denoise"]), "feather": int(hand["feather"]),
                            "noise_mask": True, "force_inpaint": True,
                            "wildcard": "", "cycle": 1}}
        img = [df, 0]
        passes.append("hand")
    if up.get("enabled"):
        ul = nn()
        g[ul] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": up["model"]}}
        iu = nn()
        g[iu] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": [ul, 0], "image": img}}
        tw = int(up["target_width"])
        th = int(round(tw * float(h) / float(w) / 8.0) * 8)
        sc = nn()
        g[sc] = {"class_type": "ImageScale",
                 "inputs": {"image": [iu, 0], "upscale_method": "lanczos",
                            "width": tw, "height": th, "crop": "disabled"}}
        img = [sc, 0]
        passes.append("upscale(%dx%d)" % (tw, th))
    sv = nn()
    g[sv] = {"class_type": "SaveImage", "inputs": {"images": img, "filename_prefix": prefix}}
    return g, passes


def seq_max(d, base):
    """Largest existing <base>_NNN number in d, or 0.

    Padding-agnostic on purpose: ComfyUI's SaveImage appends its own
    `_00001_` counter to whatever prefix it is given, so the number of
    zero-padded digits in an on-disk series number is NOT ours to fix. An
    exact-name probe (`%03d` + `_00001_.png`) therefore never matches what
    the server actually wrote and silently disables sequence avoidance.
    Matching any run of digits keeps both spellings (`_001.png`,
    `_00001_.png`) in one series.
    """
    try:
        names = os.listdir(d)
    except FileNotFoundError:
        return 0
    pat = re.compile(re.escape(base) + r"_(\d+)")
    mx = 0
    for b in names:
        m = pat.match(b)
        if m:
            mx = max(mx, int(m.group(1)))
    return mx


def seq_next(server_out, sub, base):
    """Read the next series number. An absent series under a readable root starts at 1."""
    os.listdir(server_out)
    return seq_max(os.path.join(server_out, sub.strip("/")), base) + 1


def seq_rename(path, base):
    """Rename a downloaded image to <base>_NNN.png, continuing from the dir's max."""
    d = os.path.dirname(path)
    mx = 0
    for b in os.listdir(d):
        m = re.match(re.escape(base) + r"_(\d+)\.png$", b)
        if m:
            mx = max(mx, int(m.group(1)))
    newp = os.path.join(d, "%s_%03d.png" % (base, mx + 1))
    os.rename(path, newp)
    return newp


def run(base, args, cfg):
    cfg = normalize_config(cfg, args.server_out)
    validate_run(args)
    w, h = cfg.get("width", 832), cfg.get("height", 1216)
    args.server_out = cfg.get("server_output_dir")
    args.server_sub = args.server_sub or cfg.get("server_sub") or cfg.get("name", "pipeline")
    args.seq_name = args.seq_name or cfg.get("name", "pipeline")
    direct = bool(args.server_out)
    outdir = cfg.get("output_dir")
    # Output directories are checked only after offline planning.
    prefix = args.prefix if args.prefix is not None else cfg.get("prefix", cfg.get("name", "pipeline"))
    next_seq = seq_next(args.server_out, args.server_sub, args.seq_name) if direct else 0
    base_positive = cfg.get("positive", "")
    names_list, prompt_list = resolve_prompts(cfg, args.prompt, args.names)
    face, hand, up = detail_cfg(cfg, args)

    def pos_for(t): return ", ".join(x for x in (base_positive, t) if x)

    basis = args.seed_basis if args.seed_basis is not None else random.randrange(1, 2 ** 31 - 1)
    log("SEED_BASIS: %d" % basis)
    jobs = []
    for idx, (name, txt) in enumerate(zip(names_list, prompt_list)):
        raw = pos_for(txt)
        split_prompts(raw) if raw.strip() else None
        groups = brace_options(raw)
        bs = basis + (0 if args.seed_fixed else idx * 100000)
        for k in range(args.count):
            seed = bs + k
            jname, pos = name, raw
            if groups:
                if args.pick == "cycle":
                    cs = [g[(idx * args.count + k) % len(g)] for g in groups]
                else:
                    rng = random.Random(seed)
                    cs = [rng.choice(g) for g in groups]
                pos = expand_braces(raw, cs)
                tag = branch_tag(cs)
                if tag:
                    jname = "%s__%s" % (name, tag)
            if direct:
                # 序号来自一次目录扫描（seq_next），补零位数与磁盘上已有的对齐。
                # 不要在这里拿拼出来的精确文件名去 exists() 探测：SaveImage 会再补一层
                # `_00001_` 计数器，拼出来的名字永远对不上，探测恒为假（等于没有避让）。
                fname = "%s_%05d" % (args.seq_name, next_seq)
                next_seq += 1
                jprefix = "%s/%s" % (args.server_sub.strip("/"), fname)
            else:
                fname = jname
                jprefix = ("%s/%s_%d" % (prefix, fname, seed)) if prefix else ("%s_%d" % (fname, seed))
            jobs.append({"name": jname, "file": fname, "k": k + 1, "count": args.count, "seed": seed,
                         "pos": pos, "prefix": jprefix})

    built = [build_graph(cfg, j["pos"], j["seed"], j["prefix"], w, h, face, hand, up) for j in jobs]
    graphs = [g for g, _ in built]
    validate_graphs(graphs)
    if args.dry_run:
        log(json.dumps({"jobs": jobs, "graphs": graphs}, ensure_ascii=False, indent=2))
        return
    preflight(base, graphs, api)
    check_output(cfg)
    if args.check:
        return
    ids = []
    for j, (g, passes) in zip(jobs, built):
        resp = api(base, "/prompt", {"prompt": g, "client_id": "auto-comfy-draw-twopass"})
        if "prompt_id" not in resp:
            raise SystemExit("/prompt validation failed: " + json.dumps(resp, ensure_ascii=False)[:1500])
        j["pid"] = resp["prompt_id"]
        ids.append(j["pid"])
        log("[%s -> %s#%d/%d] queued pid=%s seed=%d base=%dx%d passes=%s"
            % (j["name"], j["file"], j["k"], j["count"], j["pid"], j["seed"], w, h, ",".join(passes) or "none"))

    pending = set(ids)
    saved, failures = {}, []
    deadline = time.time() + args.timeout
    while pending and time.time() < deadline:
        for pid in list(pending):
            try:
                hist = api(base, "/history/" + pid)
            except Exception:
                continue
            if pid not in hist:
                continue
            entry = hist[pid]
            status = entry.get("status") or {}
            if status.get("status_str") not in ("error", "success", "completed"):
                continue
            files = []
            download_failed = False
            for _nid, out in (entry.get("outputs") or {}).items():
                for im in (out.get("images") or []):
                    if direct:
                        sp = os.path.join(args.server_out, im.get("subfolder", ""), im["filename"])
                        files.append(sp)
                        log("  on server: %s" % sp)
                        continue
                    try:
                        fp = download(base, outdir, im)
                        if args.seq:
                            old = os.path.basename(fp)
                            fp = seq_rename(fp, args.seq_name)
                            log("  seq: %s  <- %s" % (os.path.basename(fp), old))
                        files.append(fp)
                    except Exception as e:
                        download_failed = True
                        log("  ! download failed %s: %s" % (im.get("filename"), e))
            if status.get("status_str") == "error":
                failures.append(pid)
                log("  ! %s errored: %s" % (pid, json.dumps(status.get("messages"), ensure_ascii=False)[:400]))
            elif download_failed or not files:
                failures.append(pid)
                log("  ! %s produced no image" % pid)
            saved[pid] = files
            pending.discard(pid)
            for f in files:
                log("SAVED: " + f)
        if pending:
            time.sleep(3)

    log("remaining: %d failures: %d %s" % (len(pending), len(failures), "DONE" if not pending and not failures else "INCOMPLETE"))
    if pending or failures:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="ComfyUI two-pass (sample + detail + upscale) driver.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--prompt", default=None, help="'|'-separated prompts, overrides config prompts")
    ap.add_argument("--names", default=None, help="comma-separated config prompt names")
    ap.add_argument("--seed-basis", type=int, default=None)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-face", action="store_true")
    ap.add_argument("--no-hand", action="store_true")
    ap.add_argument("--upscale", action="store_true")
    ap.add_argument("--no-upscale", action="store_true")
    ap.add_argument("--face-denoise", type=float, default=None)
    ap.add_argument("--hand-denoise", type=float, default=None)
    ap.add_argument("--upscale-width", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--prefix", default=None, help="override the config prefix/subfolder")
    ap.add_argument("--server-out", default=None,
                    help="ComfyUI server output ROOT; enables direct-to-server output (no local download)")
    ap.add_argument("--server-sub", default=None,
                    help="subfolder under --server-out; files are written there as <seq-name>_NNN_*.png")
    ap.add_argument("--seq-name", default=None,
                    help="base name for sequential output (default config.name)")
    ap.add_argument("--seq", action="store_true",
                    help="rename outputs to <seq-name>_NNN.png, continuing the sequence in the output dir")
    ap.add_argument("--seed-fixed", action="store_true",
                    help="shared base seed for every prompt; prompt changes may alter layout "
                         "(use with --count 1 for a true controlled sweep)")
    ap.add_argument("--pick", choices=["random", "cycle"], default="random",
                    help="how to resolve {a|b|c}: random=seed-derived draw (native-style), cycle=round-robin per group; count must cover the largest group")
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="offline batch preview; no writes or submissions")
    modes.add_argument("--check", action="store_true", help="online preflight; submit nothing")
    args = ap.parse_args()
    if args.upscale and args.no_upscale:
        ap.error("--upscale and --no-upscale are mutually exclusive")

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    base = None if args.dry_run else probe(args.host, args.port)
    if base:
        log("using " + base)
    run(base, args, cfg)


if __name__ == "__main__":
    main()