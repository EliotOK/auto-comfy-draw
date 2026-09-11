"""pipeline_twopass 的序号逻辑单测（不需 GPU、不需 ComfyUI 在线）。

覆盖 2026-09 修掉的那个 bug：直写模式下拿拼出来的精确文件名去 exists() 探测，
而 SaveImage 实际写的是 5 位补零，探测恒为假 → 避让逻辑静默失效。
"""
import atexit
import os
import shutil
import sys
import uuid
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from pipeline_twopass import seq_max, seq_next  # noqa: E402

# 沙箱只允许写工作区，系统的 temp 目录建不了 → 测试自己的临时根也放工作区内。
_TMP_ROOT = os.path.join(REPO, "tests", "_tmp")
atexit.register(lambda: shutil.rmtree(_TMP_ROOT, ignore_errors=True))


def tmpdir():
    p = os.path.join(_TMP_ROOT, uuid.uuid4().hex[:12])
    os.makedirs(p, exist_ok=True)
    return p


class SeqMaxTest(unittest.TestCase):
    def setUp(self):
        self.d = tmpdir()

    def _touch(self, *names):
        for n in names:
            open(os.path.join(self.d, n), "w").close()

    def test_empty_dir_starts_at_zero(self):
        self.assertEqual(seq_max(self.d, "sparkle"), 0)

    def test_missing_dir_returns_zero(self):
        self.assertEqual(seq_max(os.path.join(self.d, "nope"), "sparkle"), 0)

    def test_reads_five_digit_server_padding(self):
        """SaveImage 的 5 位补零形态。"""
        self._touch("sparkle_00001_00001_.png", "sparkle_00002_00001_.png")
        self.assertEqual(seq_max(self.d, "sparkle"), 2)

    def test_reads_legacy_three_digit_padding(self):
        """--seq 时代的 3 位形态，必须与 5 位同属一个序列。"""
        self._touch("sparkle_001.png", "sparkle_002.png")
        self.assertEqual(seq_max(self.d, "sparkle"), 2)

    def test_mixed_padding_shares_one_series(self):
        """两代格式混存时取到真正的最大值（旧的精确探测会漏掉 5 位那批）。"""
        self._touch("sparkle_001.png", "sparkle_002.png", "sparkle_00049_00001_.png")
        self.assertEqual(seq_max(self.d, "sparkle"), 49)

    def test_phase_prefixes_are_independent_series(self):
        """阶段化命名：各阶段 prefix 是独立序号空间。"""
        self._touch(
            "sparkle_phase1_meet_00001_00001_.png",
            "sparkle_phase1_meet_00002_00001_.png",
            "sparkle_phase2_defeat_00001_00001_.png",
        )
        self.assertEqual(seq_max(self.d, "sparkle_phase1_meet"), 2)
        self.assertEqual(seq_max(self.d, "sparkle_phase2_defeat"), 1)

    def test_series_number_is_not_the_trailing_counter(self):
        """序号取自 prefix 段，不是末尾的 SaveImage 计数器。"""
        self._touch("sparkle_phase1_meet_00003_00001_.png",
                    "sparkle_phase1_meet_00003_00002_.png")
        self.assertEqual(seq_max(self.d, "sparkle_phase1_meet"), 3)

    def test_similar_prefix_does_not_leak(self):
        """前缀相似但不能互相污染。"""
        self._touch("sparkle_extra_00099_00001_.png")
        self.assertEqual(seq_max(self.d, "sparkle"), 0)

    def test_unrelated_files_ignored(self):
        self._touch("other_00007.png", "readme.txt", "sparkle_00005_00001_.png")
        self.assertEqual(seq_max(self.d, "sparkle"), 5)


class SeqNextTest(unittest.TestCase):
    def setUp(self):
        self.root = tmpdir()

    def test_fresh_series_starts_at_one(self):
        self.assertEqual(seq_next(self.root, "sparkle", "sparkle"), 1)

    def test_continues_from_disk_max(self):
        sub = os.path.join(self.root, "sparkle")
        os.makedirs(sub)
        for n in ("sparkle_phase9_probe_00001_00001_.png",
                  "sparkle_phase9_probe_00002_00001_.png"):
            open(os.path.join(sub, n), "w").close()
        # 扩跑同一阶段 → 接着数，不回退、不覆盖
        self.assertEqual(seq_next(self.root, "sparkle", "sparkle_phase9_probe"), 3)

    def test_subdir_with_slashes_normalised(self):
        sub = os.path.join(self.root, "sparkle")
        os.makedirs(sub)
        open(os.path.join(sub, "c_00004_00001_.png"), "w").close()
        self.assertEqual(seq_next(self.root, "/sparkle/", "c"), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)