"""Regression tests for AI-DLC Lean 0.3.1, a fixes-only release (docs/design-v0.2.md §10).

Covers the round-1 review items R1-106 to R1-120 (each test is named after its item), the read-only shell reads of
the record paths that the records gate used to block, and the follow-ups from the first live Kiro run of the v0.3
phases (live-1 to live-8).

Run: python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_aidlc_lean import SUMMARY  # noqa: E402
from test_v02_live_fixes import Live  # noqa: E402


class Fix31(Live):
    pass


# ---------------------------------------------------------------- R1-106: check output that is not UTF-8
class VerifyBytes(Fix31):
    def test_r1_106_check_output_that_is_not_utf8_is_recorded_by_exit_code(self):
        i = self.intent()
        self.cfg(checks=["printf 'ok \\377\\n'", "printf '\\315\\313\\277\\356\\n'; exit 3"])  # 0xff; GBK bytes
        p = self.tool("verify")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)  # the second check fails by its exit code
        self.assertNotIn("Traceback", p.stderr)
        self.assertIn("PASS  printf 'ok \\377\\n'", p.stdout)
        self.assertIn("FAIL  printf", p.stdout)
        data = self.events("VERIFY")[-1]["data"]
        self.assertEqual([r["exit"] for r in data["results"]], [0, 3])
        self.assertIn("\n    �", p.stdout)  # the failing check's output, its bad bytes replaced
        self.assertIn("| 2 | `printf", self.read(self.ipath(i, SUMMARY)))
        self.cfg(checks=["printf 'ok \\377\\n'"])
        self.assertIn("verify: PASS", self.ok("verify").stdout)
        self.assertTrue(self.events("VERIFY")[-1]["data"]["ok"])


if __name__ == "__main__":
    unittest.main()
