"""Shared prompt parsing, configuration validation and read-only API preflight."""
import json
import math
import os
from pathlib import Path
import random
import re
import tempfile


def split_prompts(text):
    """Split only top-level pipes. Nested and unbalanced braces are rejected."""
    parts, start, depth = [], 0, 0
    for i, char in enumerate(text):
        if char == "{":
            if depth:
                raise ValueError("Nested prompt braces are not supported")
            depth = 1
        elif char == "}":
            if not depth:
                raise ValueError("Unbalanced prompt braces")
            depth = 0
        elif char == "|" and not depth:
            parts.append(text[start:i].strip())
            start = i + 1
    if depth:
        raise ValueError("Unbalanced prompt braces")
    parts.append(text[start:].strip())
    parts = [part for part in parts if part]
    if not parts:
        raise ValueError("Prompt must not be empty")
    return parts


def resolve_prompts(cfg, prompt, names):
    if prompt is not None and names is not None:
        raise ValueError("--prompt and --names are mutually exclusive")
    if prompt is not None:
        parts = split_prompts(prompt)
        return ["p%d" % (i + 1) for i in range(len(parts))], parts
    pairs = [(s["name"], s["prompt"]) if isinstance(s, dict) else (s, s)
             for s in cfg.get("prompts", [])]
    all_names = [n for n, _ in pairs]
    if len(set(all_names)) != len(all_names):
        raise ValueError("Prompt names must be unique")
    if names is not None:
        wanted = [n.strip() for n in names.split(",")]
        missing = [n for n in wanted if n not in all_names]
        if missing:
            raise ValueError("--names not found: %s" % missing)
        # Keep config order to preserve existing seed ordering.
        pairs = [(n, p) for n, p in pairs if n in wanted]
    if not pairs:
        return ["default"], [""]
    return [n for n, _ in pairs], [p for _, p in pairs]


def expand_prompt(text, seed, pick, index):
    split_prompts(text) if text.strip() else None
    rng = random.Random(seed)
    def replace(match):
        options = [part.strip() for part in match.group(1).split("|")]
        return options[index % len(options)] if pick == "cycle" else rng.choice(options)
    return re.sub(r"\{([^{}]*)\}", replace, text)


def validate_schema(value, schema, path="config"):
    """Validate the subset used by config.schema.json; no external dependency.

    Supports type, required, properties, items, anyOf/oneOf, enum, string
    length and numeric limits. This is not a general JSON Schema engine.
    """
    for key in ("oneOf", "anyOf"):
        if key in schema:
            matches = 0
            for choice in schema[key]:
                try:
                    validate_schema(value, choice, path)
                    matches += 1
                except ValueError:
                    pass
            if (key == "oneOf" and matches != 1) or not matches:
                raise ValueError("%s does not match %s" % (path, key))
    types = {"object": lambda v: isinstance(v, dict),
             "array": lambda v: isinstance(v, list),
             "string": lambda v: isinstance(v, str),
             "integer": lambda v: type(v) is int,
             "number": lambda v: type(v) in (int, float) and math.isfinite(v),
             "boolean": lambda v: type(v) is bool,
             "null": lambda v: v is None}
    expected = schema.get("type")
    if expected:
        expected = [expected] if isinstance(expected, str) else expected
        if not any(types[t](value) for t in expected):
            raise ValueError("%s must be %s" % (path, expected))
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("%s must be one of %s" % (path, schema["enum"]))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError("%s.%s is required" % (path, key))
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                validate_schema(value[key], sub, path + "." + key)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            validate_schema(item, schema["items"], "%s[%d]" % (path, i))
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        raise ValueError("%s must not be empty" % path)
    if type(value) in (int, float):
        for key, bad in (("minimum", lambda n: value < n),
                         ("maximum", lambda n: value > n),
                         ("multipleOf", lambda n: value % n != 0)):
            if key in schema and bad(schema[key]):
                raise ValueError("%s violates %s=%s" % (path, key, schema[key]))


def normalize_config(cfg, server_out=None):
    cfg = dict(cfg)
    # Older scaffold versions emitted a boolean marker and null denoise.
    if type(cfg.get("server_out")) is bool:
        if cfg["server_out"] and not (server_out or cfg.get("server_output_dir")):
            raise ValueError("Legacy server_out=true needs a server_output_dir path")
        cfg.pop("server_out")
    if cfg.get("denoise", 1.0) is None:
        cfg["denoise"] = 1.0
    canonical, alias = cfg.get("server_output_dir"), cfg.get("server_out")
    if not server_out and canonical and alias and canonical != alias:
        raise ValueError("server_output_dir and server_out disagree")
    cfg["server_output_dir"] = server_out or canonical or alias or None
    cfg.pop("server_out", None)
    if cfg.get("output_dir") is None:
        cfg.pop("output_dir", None)
    schema = json.loads(Path(__file__).with_name("config.schema.json").read_text(encoding="utf-8"))
    validate_schema(cfg, schema)
    resolve_prompts(cfg, None, None)
    return cfg


def validate_run(args):
    if args.count < 1:
        raise ValueError("--count must be at least 1")
    if args.prompt is not None and args.names is not None:
        raise ValueError("--prompt and --names are mutually exclusive")
    if getattr(args, "timeout", 1) <= 0:
        raise ValueError("--timeout must be positive")
    if args.seed_basis is not None and not 0 <= args.seed_basis <= 2**64 - 3:
        raise ValueError("--seed-basis is outside the supported seed range")
    denoise = getattr(args, "denoise", None)
    if denoise is not None and not 0 <= denoise <= 1:
        raise ValueError("--denoise must be between 0 and 1")


def check_output(cfg):
    if cfg.get("server_output_dir"):
        print("[ok] direct output: server owns its configured output directory")
        return
    outdir = cfg["output_dir"]
    os.makedirs(outdir, exist_ok=True)
    with tempfile.TemporaryFile(dir=outdir) as stream:
        stream.write(b"write-check")
        stream.flush()
    print("[ok] output_dir write verified: " + outdir)


def preflight(base, graphs, api):
    """Check nodes, required inputs and advertised enum choices, without queueing."""
    info = api(base, "/object_info")
    checked = set()
    for graph in graphs:
        for node in graph.values():
            kind = node["class_type"]
            if kind not in info:
                raise ValueError("Required ComfyUI node missing: " + kind)
            spec = info[kind].get("input", {})
            inputs = node["inputs"]
            for key in spec.get("required", {}):
                if key not in inputs:
                    raise ValueError("%s.%s is required by this server" % (kind, key))
            for key, definition in dict(spec.get("required", {}), **spec.get("optional", {})).items():
                if key not in inputs or isinstance(inputs[key], list):
                    continue
                value = inputs[key]
                signature = (kind, key, str(value))
                if signature in checked:
                    continue
                checked.add(signature)
                if isinstance(definition[0], list) and value not in definition[0]:
                    raise ValueError("%s.%s unavailable: %s" % (kind, key, value))
                if len(definition) > 1 and isinstance(definition[1], dict) and type(value) in (int, float):
                    for bound, compare in (("min", lambda v: value < v), ("max", lambda v: value > v)):
                        if bound in definition[1] and compare(definition[1][bound]):
                            raise ValueError("%s.%s outside server %s" % (kind, key, bound))
    print("[ok] workflow nodes, required inputs and advertised choices checked")


def validate_graphs(graphs):
    for graph in graphs:
        for node in graph.values():
            seed = node["inputs"].get("seed")
            if seed is not None and not 0 <= seed <= 2**64 - 1:
                raise ValueError("Derived seed exceeds ComfyUI uint64 range")
