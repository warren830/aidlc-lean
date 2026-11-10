"""Regression tests for AI-DLC Lean 0.3.1, a fixes-only release (docs/design-v0.2.md §10).

Covers the round-1 review items R1-106 to R1-120 (each test is named after its item), the read-only shell reads of
the record paths that the records gate used to block, and the follow-ups from the first live Kiro run of the v0.3
phases (live-1 to live-8).

Run: python3 -m unittest discover -s tests -v
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_aidlc_lean import DOCS, REPO, SUMMARY, TOOL  # noqa: E402
from test_v02_live_fixes import BEGIN, END, Live  # noqa: E402


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


# ---------------------------------------------------------------- R1-107: team names with -, . or Chinese
class TeamNames(Fix31):
    flags = ["--multi-team", "--team", "web-team"]
    own = "aidlc-docs/contracts/web-team/api.yaml"
    other = "aidlc-docs/contracts/catalog/items.yaml"

    def setUp(self):
        super().setUp()
        self.put("aidlc-docs/contracts/OWNERS",
                 "aidlc-docs/contracts/web-team/** web-team\naidlc-docs/contracts/catalog/** catalog\n")

    def inception(self):
        """An approved intent with unit api (team web-team, this clone) and unit web (team catalog)."""
        i = self.intent()
        self.requirements(i, "large")
        self.design(i)
        self.units(i, [("api", "web-team", "src/api/, aidlc-docs/contracts/web-team/**"),
                       ("web", "catalog", "src/web/")])
        self.ok("stage", "done", "units", "--note", "api, web")
        for sid in ("reverse-engineering", "user-stories"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        out, _ = self.approve("INCEPTION")
        self.assertIn("Recorded: INCEPTION approved", out.stdout)
        return i

    def test_r1_107_a_hyphenated_team_keeps_its_name_its_contract_its_unit_and_its_crs(self):
        self.assertEqual(self.read(".aidlc-lean/local.json").count('"web-team"'), 1)  # kept as written
        self.assertIn("multi-team (this clone: team web-team)", self.status())
        self.inception()
        self.assertEqual(self.write(self.own, "openapi: 3.0.0\n").returncode, 0)  # its own contract: no CR
        self.assertIn("Next: unit api: record its design stages first", self.status())  # its own unit
        self.assertNotIn("wait for unit api", self.status())
        self.assertEqual(self.write(self.other, "x: 1\n").returncode, 2)
        p = self.ok("cr", "new", "items", "--owner", "catalog", "--paths", self.other)
        self.assertIn("CR-web_team-1", p.stdout)  # the CR id keeps to letters, digits and _
        self.assertIn("- Requested by team: web-team", self.read("aidlc-docs/contracts/changes/CR-web_team-1-items.md"))
        out, _ = self.approve("CR-web_team-1", team="catalog")
        self.assertIn("Recorded: CR-web_team-1 approved", out.stdout)
        self.assertEqual(self.write(self.other, "x: 1\n").returncode, 0)  # unlocked for the requesting team
        self.ok("cr", "new", "api-field", "--owner", "web-team", "--paths", self.own, team="catalog")
        out, _ = self.approve("CR-catalog-1")  # this clone (web-team) owns the contract: it approves
        self.assertIn("Recorded: CR-catalog-1 approved", out.stdout)
        self.assertEqual(self.write(self.own, "openapi: 3.1.0\n", team="catalog").returncode, 0)
        self.assertIn("Change requests involving your team: CR-catalog-1 (open, approved), CR-web_team-1 (open, "
                      "approved)", self.status())

    def test_r1_107_the_environment_variable_and_init_team_agree(self):
        os.remove(os.path.join(self.dir, ".aidlc-lean", "local.json"))
        self.inception()
        for team in ("web-team", "web_team", "web.team"):  # -, . and _ name the same team
            self.assertEqual(self.write(self.own, "openapi: 3.0.0\n", team=team).returncode, 0, team)
            self.assertIn("Next: unit api: record its design stages first", self.tool("status", team=team).stdout)
        self.assertEqual(self.write(self.own, "openapi: 3.0.0\n", team="webteam").returncode, 2)


class TeamNamesChinese(Fix31):
    flags = ["--multi-team", "--team", "支付"]
    pay = "aidlc-docs/contracts/pay/api.yaml"

    def test_r1_107_chinese_team_names_stay_apart(self):
        self.assertIn('"支付"', self.read(".aidlc-lean/local.json"))
        self.put("aidlc-docs/contracts/OWNERS", "aidlc-docs/contracts/pay/** 支付\naidlc-docs/contracts/order/** 订单\n")
        i = self.intent()
        self.requirements(i, "large")
        self.design(i)
        self.units(i, [("api", "支付", "src/api/"), ("web", "订单", "src/web/")])
        self.ok("stage", "done", "units", "--note", "api, web")
        for sid in ("reverse-engineering", "user-stories"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.approve("INCEPTION")
        self.assertIn("Owner team: 支付", self.state(i))
        self.assertEqual(self.write(self.pay, "openapi: 3.0.0\n").returncode, 0)
        self.assertEqual(self.write(self.pay, "openapi: 3.0.0\n", team="订单").returncode, 2)  # another team
        self.assertIn("Next: unit api: record its design stages first", self.status())  # its own unit
        self.assertIn("Next: unit web: record its design stages first", self.tool("status", team="订单").stdout)
        p = self.ok("cr", "new", "refund-field", "--owner", "支付", "--paths", self.pay, team="订单")
        self.assertIn("CR-订单-1", p.stdout)
        out, _ = self.approve("CR-订单-1", team="订单")  # the requesting team cannot approve it
        self.assertIn("it needs someone from team 支付 (this clone is team 订单)", out.stdout)
        out, _ = self.approve("CR-订单-1")
        self.assertIn("Recorded: CR-订单-1 approved", out.stdout)
        self.assertEqual(self.write(self.pay, "openapi: 3.1.0\n", team="订单").returncode, 0)
        self.assertEqual(self.write(self.pay, "openapi: 3.1.0\n", team="物流").returncode, 2)
        p = self.ok("init", "--team", "订单")
        self.assertIn("is now team 订单 (was 支付)", p.stdout)


# ---------------------------------------------------------------- R1-108: fingerprint_exclude adds to the defaults
class FingerprintExclude(Fix31):
    def test_r1_108_the_teams_paths_add_to_the_record_paths_and_release_passes(self):
        self.cfg(checks=["true"], fingerprint_exclude=["dist/**"])
        i = self.ready()
        self.skip_to_code()
        self.build_unit(i)  # verify records itself in the ledger: that must not change the code fingerprint
        self.sh(["git", "add", "-A"])
        self.assertEqual(self.bash("git commit -m work").returncode, 0)
        self.commit_all()
        self.put("dist/bundle.js", "built\n")  # the team's own exclusion still counts
        self.assertEqual(self.bash("git commit -m bundle").returncode, 0)
        self.sh(["git", "checkout", "--", "."])
        os.remove(os.path.join(self.dir, "dist", "bundle.js"))
        self.assertIn("Wrote", self.ok("release").stdout)
        self.put("app.py", "x = 2\n")  # product code still counts
        r = self.bash("git commit -m app")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (verify)", r.stderr)


# ---------------------------------------------------------------- R1-109: a merge conflict across the region's end
class MergeConflict(Fix31):
    def clone(self):
        b = os.path.realpath(tempfile.mkdtemp(prefix="lean-clone-"))
        self.addCleanup(shutil.rmtree, b, True)
        for cmd in (["git", "clone", "-q", self.dir, b], ["git", "-C", b, "config", "user.email", "b@example.com"],
                    ["git", "-C", b, "config", "user.name", "B"]):
            p = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
        return b

    def run_in(self, d, *args):
        p = subprocess.run(TOOL + list(args), cwd=d, capture_output=True, text=True, env=self.env())
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    @staticmethod
    def set_status(path, status):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(re.sub(r"(?m)^Status: .*$", "Status: " + status, text, count=1))

    def conflicted(self):
        """Two clones each record a stage and change the Status line; the merge conflicts in aidlc-state.md, in one
        hunk that runs across the region's end marker into the Session notes."""
        self.cfg(checks=["true"])
        i = self.intent()
        self.commit_all("intent")
        b = self.clone()
        self.run_in(b, "init")
        self.run_in(b, "use", i)
        self.run_in(b, "stage", "skip", "user-stories", "--reason", "b: no stories")
        self.set_status(os.path.join(b, DOCS, i, "aidlc-state.md"), "b: stories skipped")
        for cmd in (["git", "-C", b, "add", "-A"], ["git", "-C", b, "commit", "-qm", "b"]):
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        self.ok("stage", "skip", "reverse-engineering", "--reason", "a: greenfield")
        path = os.path.join(self.dir, self.ipath(i, "aidlc-state.md"))
        self.set_status(path, "a: reverse engineering skipped")
        self.commit_all("a")
        p = self.sh(["git", "pull", "-q", "--no-rebase", "--no-edit", b, "HEAD"])
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.sh(["git", "diff", "--name-only", "--diff-filter=U"]).stdout.split(),
                         [self.ipath(i, "aidlc-state.md")])
        text = self.read(self.ipath(i, "aidlc-state.md"))
        last = text.rindex("\n<<<<<<< ")
        self.assertLess(last, text.index(END), "the precondition: a conflict hunk spans the end marker")
        self.assertLess(text.index(END), text.index("\n>>>>>>> ", last))
        return i, path

    def test_r1_109_the_region_is_rewritten_and_the_conflict_outside_it_is_kept_whole(self):
        i, path = self.conflicted()
        p = self.ok("verify")  # README and the multi-team skill: verify rewrites what the tool writes
        self.assertIn("merge conflict", p.stdout)
        text = self.read(self.ipath(i, "aidlc-state.md"))
        self.assertEqual((text.count(BEGIN), text.count(END)), (1, 1))
        lines = text.splitlines()
        marks = [(n, l.split(" ")[0]) for n, l in enumerate(lines) if re.match(r"^(<{7}|={7}|>{7})( |$)", l)]
        self.assertEqual([m for _, m in marks], ["<<<<<<<", "=======", ">>>>>>>"])  # one whole conflict
        end = lines.index(END)
        self.assertGreater(marks[0][0], end)  # outside the region, in the Session notes
        hunk = "\n".join(lines[marks[0][0]:marks[2][0] + 1])
        self.assertIn("Status: a: reverse engineering skipped", hunk)
        self.assertIn("Status: b: stories skipped", hunk)
        region = text[text.index(BEGIN):text.index(END)]
        self.assertIn("- Skipped: a: greenfield", region)  # both clones' ledgers, regenerated
        self.assertIn("- Skipped: b: no stories", region)
        self.assertNotIn("<<<<<<<", region)
        self.ok("status")
        self.assertEqual(self.read(self.ipath(i, "aidlc-state.md")), text)  # stable while the conflict stays
        resolved = "\n".join(lines[:marks[0][0]] + ["Status: both skipped"] + lines[marks[2][0] + 1:]) + "\n"
        self.put(self.ipath(i, "aidlc-state.md"), resolved)
        p = self.ok("status")
        self.assertNotIn("merge conflict", p.stdout)
        self.assertNotIn("<<<<<<<", self.read(self.ipath(i, "aidlc-state.md")))

    def test_r1_109_markers_it_cannot_read_leave_the_page_alone(self):
        i = self.intent()
        self.ok("stage", "skip", "user-stories", "--reason", "no stories")
        text = self.state(i)
        broken = text.replace("## Session notes", "=======\n## Session notes\n>>>>>>> 1a2b3c4d", 1)  # half a conflict
        self.put(self.ipath(i, "aidlc-state.md"), broken)
        p = self.ok("stage", "skip", "reverse-engineering", "--reason", "greenfield")
        self.assertIn("Recorded: Reverse Engineering skipped", p.stdout)
        self.assertIn("merge conflict markers", p.stdout)
        self.assertEqual(self.state(i), broken)  # nothing rewritten
        self.assertEqual(len([e for e in self.events("STAGE_SKIPPED") if e["data"]["stage"] == "reverse-engineering"]),
                         1)  # the record is in the ledger all the same


# ---------------------------------------------------------------- R1-110: a .gitignore that is not UTF-8
class GitignoreBytes(unittest.TestCase):
    def test_r1_110_install_appends_to_a_gitignore_that_is_not_utf8(self):
        d = os.path.realpath(tempfile.mkdtemp(prefix="lean-gi-"))
        self.addCleanup(shutil.rmtree, d, True)
        subprocess.run(["git", "init", "-q", d], check=True)
        old = b"# caf\xe9 build output\ndist/\n"  # Latin-1, as an old editor saved it
        with open(os.path.join(d, ".gitignore"), "wb") as f:
            f.write(old)
        for _ in range(2):  # a re-install adds nothing more
            p = subprocess.run(["bash", os.path.join(REPO, "install.sh"), d], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertNotIn("Traceback", p.stderr)
        with open(os.path.join(d, ".gitignore"), "rb") as f:
            data = f.read()
        self.assertTrue(data.startswith(old))
        self.assertEqual(data.count(b".aidlc-lean/"), 1)
        p = subprocess.run(TOOL + ["audit", "verify"], cwd=d, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("OK ", p.stdout)


# ---------------------------------------------------------------- R1-111: a full-width space in an approval line
class Requested(Fix31):
    def requested(self):
        i = self.intent()
        self.requirements(i)
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        return i, self.request_hash("REQUIREMENTS")


class FullWidthSpace(Requested):
    def test_r1_111_a_full_width_space_counts_as_a_space(self):
        i, h = self.requested()
        out = self.say("批准\u3000REQUIREMENTS %s" % h)  # the IME's full-width space after 批准
        self.assertIn("Recorded: REQUIREMENTS approved (sha %s)" % h, out.stdout)
        self.requirements(i, extra="\nmore\n")
        h = self.request_hash("REQUIREMENTS")
        out = self.say("批准 REQUIREMENTS\u3000%s\u3000" % h)
        self.assertIn("Recorded: REQUIREMENTS approved (sha %s)" % h, out.stdout)
        self.requirements(i, extra="\nmore again\n")
        self.request_hash("REQUIREMENTS")
        out = self.say("驳回\u3000REQUIREMENTS\u3000需要补充验收标准")
        self.assertIn("Recorded: REQUIREMENTS rejected", out.stdout)


if __name__ == "__main__":
    unittest.main()
