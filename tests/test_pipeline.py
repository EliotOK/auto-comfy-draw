import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pipeline
import pipeline_twopass as twopass
from pipeline_common import normalize_config, preflight, resolve_prompts, split_prompts


class PipelineTests(unittest.TestCase):
    def cli(self, script, *args, ok=True):
        module = pipeline if script == "pipeline.py" else twopass
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with patch.object(sys, "argv", [str(ROOT / script), *map(str, args)]), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                module.main()
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
                if not isinstance(exc.code, int):
                    stderr.write(str(exc.code))
            except (ValueError, RuntimeError, OSError) as exc:
                code = 1
                stderr.write(str(exc))
        result = argparse.Namespace(returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def config(self, directory, **overrides):
        cfg = {"model": "dummy.safetensors", "name": "birds", "positive": "quality",
               "output_dir": str(Path(directory) / "must-not-exist"), "prompts": []}
        cfg.update(overrides)
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        return path

    def preview(self, script, cfg, *args):
        result = self.cli(script, "--config", cfg, "--dry-run", *args)
        return json.loads(result.stdout[result.stdout.index("{"):])

    def test_braces_and_empty_segments(self):
        self.assertEqual(split_prompts("a {red|blue} bird|| cat|"), ["a {red|blue} bird", "cat"])
        self.assertEqual(resolve_prompts({}, "|bird||cat", None), (["p1", "p2"], ["bird", "cat"]))
        for invalid in ("{{a|b}|c}", "a {b|c", "a}", "||"):
            with self.assertRaises(ValueError):
                split_prompts(invalid)

    def test_unknown_and_duplicate_names(self):
        cfg = {"prompts": [{"name": "a", "prompt": "bird"}]}
        with self.assertRaises(ValueError):
            resolve_prompts(cfg, None, "a,typo")
        with self.assertRaises(ValueError):
            resolve_prompts(cfg, "bird", "a")
        with self.assertRaises(ValueError):
            resolve_prompts({"prompts": ["a", "a"]}, None, None)

    def test_offline_full_batch_branches_and_seed_fixed(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = self.config(directory)
            for script in ("pipeline.py", "pipeline_twopass.py"):
                data = self.preview(script, cfg, "--prompt", "{red|blue} bird|cat", "--count", 2,
                                    "--pick", "cycle", "--seed-fixed")
                self.assertEqual(len(data["graphs"]), 4)
                jobs = data["jobs"]
                self.assertEqual([j["pos"] for j in jobs], ["quality, red bird", "quality, blue bird", "quality, cat", "quality, cat"])
                self.assertEqual(jobs[0]["seed"], jobs[2]["seed"])
                self.assertEqual(jobs[1]["seed"], jobs[3]["seed"])
            self.assertFalse((Path(directory) / "must-not-exist").exists())

    def test_base_positive_once(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = self.config(directory)
            for script in ("pipeline.py", "pipeline_twopass.py"):
                data = self.preview(script, cfg, "--count", 1)
                self.assertEqual(data["graphs"][0]["3"]["inputs"]["text"], "quality")

    def test_seed_basis_preserves_existing_formula(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = self.config(directory, prompts=["bird", "cat"])
            for script in ("pipeline.py", "pipeline_twopass.py"):
                data = self.preview(script, cfg, "--seed-basis", 42, "--count", 2)
                self.assertEqual([j["seed"] for j in data["jobs"]], [42, 43, 100042, 100043])

    def test_direct_config_and_new_series(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = self.config(directory, output_dir=None, server_output_dir=directory)
            for script in ("pipeline.py", "pipeline_twopass.py"):
                data = self.preview(script, cfg, "--count", 1)
                graph = data["graphs"][0]
                save = next(n for n in graph.values() if n["class_type"] == "SaveImage")
                self.assertRegex(save["inputs"]["filename_prefix"], r"^birds/birds_0*1$")
            self.assertFalse((Path(directory) / "birds").exists())

    def test_scaffold_contract_and_direct_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = Path(directory) / "scaffold.json"
            self.cli("pipeline.py", "--scaffold", "--model", "dummy", "--server-out", directory,
                     "--config", cfg, "--prompts", "a {red|blue} bird|cat")
            data = json.loads(cfg.read_text())
            self.assertEqual(normalize_config(data)["denoise"], 1.0)
            self.assertEqual(len(data["prompts"]), 2)
            self.preview("pipeline_twopass.py", cfg)

    def test_legacy_alias_and_validation(self):
        base = {"model": "dummy", "output_dir": "output"}
        self.assertEqual(normalize_config(dict(base, denoise=None, server_out=False))["denoise"], 1.0)
        self.assertEqual(normalize_config({"model": "dummy", "server_out": "server"})["server_output_dir"], "server")
        with self.assertRaises(ValueError):
            normalize_config(dict(base, server_out="one", server_output_dir="two"))
        self.assertEqual(normalize_config(dict(base, server_out="one", server_output_dir="two"), "cli")["server_output_dir"], "cli")
        for override in ({"width": 0}, {"width": 17}, {"steps": 0}, {"denoise": 2},
                         {"detail": {"face": {"denoise": -0.1}}}):
            with self.assertRaises(ValueError):
                normalize_config(dict(base, **override))

    def test_cli_invalid_inputs_and_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = self.config(directory)
            for script in ("pipeline.py", "pipeline_twopass.py"):
                for args in (("--count", "0"), ("--prompt", "bird", "--names", "a"),
                             ("--check",), ("--seed-basis", str(2**64 - 3), "--count", "4")):
                    self.cli(script, "--config", cfg, "--dry-run", *args, ok=False)
            self.cli("pipeline_twopass.py", "--config", cfg, "--dry-run", "--face-denoise", "2", ok=False)

    def test_img2img_uses_reference_latent(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = self.config(directory)
            data = self.preview("pipeline.py", cfg, "--init", "ref.png", "--denoise", "0.6", "--count", 1)
            graph = data["graphs"][0]
            self.assertEqual(graph["5"]["inputs"]["image"], "ref.png")
            self.assertEqual(graph["7"]["inputs"]["denoise"], 0.6)
            self.assertEqual(graph["7"]["inputs"]["latent_image"], ["6", 0])

    def test_preflight_checks_dependency_and_enum(self):
        graph = {"1": {"class_type": "LoraLoader", "inputs": {"lora_name": "missing"}}}
        info = {"LoraLoader": {"input": {"required": {"lora_name": [["available"]]}}}}
        for response in ({}, info):
            with self.assertRaises(ValueError):
                preflight("mock", [graph], lambda *args: response)
        graph["1"]["inputs"]["lora_name"] = "available"
        preflight("mock", [graph], lambda *args: info)

    def test_check_never_submits(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = self.config(directory)
            for module in (pipeline, twopass):
                with patch.object(sys, "argv", [module.__file__, "--config", str(cfg), "--check"]), \
                     patch.object(module, "probe", return_value=8188 if module is pipeline else "mock"), \
                     patch.object(module, "preflight") as check, \
                     patch.object(module, "api", side_effect=AssertionError("unexpected submission")):
                    module.main()
                    check.assert_called_once()

    def test_partial_download_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = self.config(directory)
            response = {"pid": {"status": {"status_str": "success"}, "outputs": {
                "9": {"images": [{"filename": "one.png"}, {"filename": "two.png"}]}}}}
            with patch.object(sys, "argv", [twopass.__file__, "--config", str(cfg), "--count", "1"]), \
                 patch.object(twopass, "probe", return_value="mock"), \
                 patch.object(twopass, "preflight"), \
                 patch.object(twopass, "api", side_effect=[{"prompt_id": "pid"}, response]), \
                 patch.object(twopass, "download", side_effect=["one.png", OSError("offline")]):
                with self.assertRaises(SystemExit) as raised:
                    twopass.main()
                self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
