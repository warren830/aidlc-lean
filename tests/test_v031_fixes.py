"""Regression tests for AI-DLC Lean 0.3.1, a fixes-only release (docs/design-v0.2.md §10).

Covers the round-1 review items R1-106 to R1-120 (each test is named after its item), the read-only shell reads of
the record paths that the records gate used to block, and the follow-ups from the first live Kiro run of the v0.3
phases (live-1 to live-8).

Run: python3 -m unittest discover -s tests -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_aidlc_lean import DOCS, REPO, SUMMARY, TOOL  # noqa: E402
from test_v02_live_fixes import BEGIN, END, LEAN, Live  # noqa: E402


class Fix31(Live):
    def progress(self, intent):
        """The Stage progress lines of aidlc-state.md (after `status` refreshed it)."""
        self.ok("status")
        return self.state(intent).split("## Stage progress\n")[1].split("\n\n## Stage log")[0].splitlines()


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


# ---------------------------------------------------------------- R1-112: no space between the kind and the reason
class RejectNoSpace(Requested):
    def test_r1_112_a_rejection_with_no_space_after_the_kind_is_recorded(self):
        self.requested()
        out = self.say("驳回 REQUIREMENTS需要补充验收标准")
        self.assertIn("Recorded: REQUIREMENTS rejected by the human", out.stdout)
        self.assertEqual(self.events("REJECTED")[-1]["data"]["words"], "驳回 REQUIREMENTS需要补充验收标准")
        self.assertIn("- [-] Requirements Analysis — rejected", self.status())
        n = len(self.events("REJECTED"))
        self.say("reject REQUIREMENTSX now")  # a longer word is not the kind
        self.say("reject DESIGNS")
        self.assertEqual(len(self.events("REJECTED")), n)


# ---------------------------------------------------------------- R1-113: only `git commit` goes through the commit gate
class CommitWord(Fix31):
    def test_r1_113_commands_that_only_mention_commit_pass_and_real_commits_are_gated(self):
        self.cfg(checks=["true"])
        self.commit_all("init")
        self.put("app.py", "x = 1\n")  # an unverified code change in the working tree
        for c in ('git log -1 --format="%h %s (last commit)"', "git merge --no-commit --no-ff HEAD",
                  "git stash push -m 'wip before commit'", "git log -1 --stat", "git show HEAD --stat | grep commit",
                  "git commit --dry-run -m x", "git status && echo 'commit later'",
                  "python3 .kiro/aidlc-lean/aidlc_lean.py stage done units --note 'git commit after this'"):
            r = self.bash(c)
            self.assertEqual(r.returncode, 0, (c, r.stderr))
        for c in ("git commit -m x", "git -C . commit -m x", "git add -A && git commit -qm x",
                  "git -c user.name=x commit -am x", "GIT_AUTHOR_NAME=x git commit -m y", "sh -c 'git commit -m x'",
                  "cd . && git commit -m 'fix the commit gate'", 'git commit -m "$(cat msg.txt)"',
                  "git --no-pager commit -m x"):
            r = self.bash(c)
            self.assertEqual(r.returncode, 2, c)
            self.assertIn("blocked (verify)", r.stderr, c)


# ---------------------------------------------------------------- R1-114: a commit of records only needs no verify
class RecordsOnlyCommit(Fix31):
    def blocked(self, c):
        r = self.bash(c)
        self.assertEqual(r.returncode, 2, c)
        self.assertIn("blocked (verify)", r.stderr, c)

    def test_r1_114_what_the_commit_holds_decides_not_the_whole_working_tree(self):
        self.cfg(checks=["true"])
        self.put("src/app.py", "x = 1\n")
        self.commit_all("init")
        i = self.intent()  # new records in aidlc-docs/
        self.put("src/app.py", "x = 2  # step 2 of the plan, not verified yet\n")  # not staged
        self.assertEqual(self.bash("git add aidlc-docs/ && git commit -m 'session notes'").returncode, 0)
        self.assertEqual(self.bash("git add %s %s && git commit -m notes" % (
            self.ipath(i, "aidlc-state.md"), self.ipath(i, "decisions.md"))).returncode, 0)
        self.sh(["git", "add", "aidlc-docs/"])
        self.assertEqual(self.bash("git commit -m 'session notes'").returncode, 0)  # only records are staged
        self.assertEqual(self.bash("git commit -qm notes -- ").returncode, 0)
        for c in ("git commit -am notes", "git add -A && git commit -m all", "git add . && git commit -m all",
                  "git add src/app.py && git commit -m x", "git add -u && git commit -m x",
                  "git commit -m notes src/app.py", 'git commit -m "$(cat msg.txt)"',
                  "cd src && git add app.py && git commit -m x"):
            self.blocked(c)
        self.put("aidlc-docs/contracts/api.yaml", "openapi: 3.0.0\n")  # a contract is code
        self.blocked("git add aidlc-docs/ && git commit -m 'session notes'")
        os.remove(os.path.join(self.dir, "aidlc-docs", "contracts", "api.yaml"))
        self.sh(["git", "add", "src/app.py"])  # product code staged: verify first
        self.blocked("git commit -m x")
        self.ok("verify")
        self.assertEqual(self.bash("git commit -m x").returncode, 0)


# ---------------------------------------------------------------- R1-115: an approval line for another intent
class TwoIntents(Fix31):
    def test_r1_115_the_refusal_names_the_intent_the_line_is_for(self):
        a = self.intent("alpha")
        self.requirements(a)
        h = self.request_hash("REQUIREMENTS")
        b = self.intent("beta")
        out = self.say("approve REQUIREMENTS %s" % h)
        self.assertIn("Approval of REQUIREMENTS NOT recorded: that line answers the REQUIREMENTS request of intent "
                      "%s, but the active intent is %s. Switch back first (`python3 .kiro/aidlc-lean/aidlc_lean.py use "
                      "%s`), then type the line again." % (a, b, a), out.stdout)
        self.assertNotIn("changed", out.stdout)
        self.assertEqual(self.events("APPROVAL_REFUSED")[-1]["data"]["check"], "intent")
        self.say("approve DESIGN %s" % h)  # beta has no design page yet: the hash still names alpha's request
        self.assertEqual(self.events("APPROVAL_REFUSED")[-1]["data"]["check"], "target")
        self.ok("use", "alpha")
        out = self.say("approve REQUIREMENTS %s" % h)
        self.assertIn("Recorded: REQUIREMENTS approved (sha %s)" % h, out.stdout)
        self.ok("use", "beta")
        out = self.say("approve REQUIREMENTS 1a2b3c4d")  # a hash no request has: the old reason
        self.assertIn("the file changed since that request", out.stdout)


# ---------------------------------------------------------------- R1-116: one date for the folder and Created
class IntentDates(Fix31):
    def test_r1_116_the_folder_name_and_created_use_the_same_utc_date(self):
        utc = datetime.now(timezone.utc)
        tz = "Etc/GMT+12" if utc.hour < 12 else "Etc/GMT-14"  # UTC-12 or UTC+14: the local date is not UTC's now
        p = self.sh(TOOL + ["new", "refunds"], env=dict(self.env(), TZ=tz))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        intent = re.search(r"aidlc-docs/(\S+) \(", p.stdout).group(1)
        created = re.search(r"Created: \d\d(\d\d)-(\d\d)-(\d\d)", self.state(intent))
        self.assertEqual(intent[:6], "".join(created.groups()))
        self.assertEqual(intent[:6], utc.strftime("%y%m%d"))  # UTC, like every date the tool records


# ---------------------------------------------------------------- R1-117: `lean new` with a Chinese name
class NewName(Fix31):
    def test_r1_117_a_name_without_a_folder_letter_says_why(self):
        for args in (["new", "退款"], ["new", "退款", "--title", "退款"], ["new", "--ideation", "退款"]):
            p = self.tool(*args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn("the intent name names its folder: use a-z, 0-9 and - (e.g. `new refunds`); a title in any "
                          "language goes in --title (e.g. `new refunds --title \"退款\"`).", p.stdout)
        p = self.ok("new", "refunds", "--title", "退款")
        self.assertIn("# AI-DLC State: 退款", self.state(re.search(r"aidlc-docs/(\S+) \(", p.stdout).group(1)))
        self.assertTrue(self.tool("new").stdout.startswith("usage: new <slug>"))


# ---------------------------------------------------------------- R1-118: `lean init --regulated` on a configured project
class InitModeFlags(Fix31):
    def test_r1_118_init_says_the_mode_flags_were_not_applied(self):
        p = self.ok("init", "--regulated")
        self.assertIn("WARNING: aidlc-docs/lean.json already exists, so it was kept as it is (regulated: false, "
                      "multi_team: false): --regulated was NOT applied. To change the mode, a person edits "
                      "\"regulated\" / \"multi_team\" in aidlc-docs/lean.json and commits it.", p.stdout)
        self.assertFalse(json.loads(self.read("aidlc-docs/lean.json"))["regulated"])
        self.assertIn("| mode: standard", self.status())
        p = self.ok("init", "--multi-team", "--regulated")
        self.assertIn("--regulated and --multi-team was NOT applied", p.stdout)
        self.assertIn("For multi-team, then run `python3 .kiro/aidlc-lean/aidlc_lean.py init --team NAME`", p.stdout)
        self.cfg(regulated=True)
        self.assertNotIn("WARNING", self.ok("init", "--regulated").stdout)  # already that mode
        p = self.sh(["bash", os.path.join(REPO, "install.sh"), self.dir, "--multi-team"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((p.stdout + p.stderr).count("WARNING"), 1)  # install.sh's own, not a second one


# ---------------------------------------------------------------- R1-119: the README quotes the Release row as printed
class ReadmeReleaseRow(Fix31):
    def test_r1_119_the_readme_quotes_the_release_row_the_tool_prints(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.skip_to_code()
        self.build_unit(i)
        self.commit_all()
        self.ok("release")
        self.requirements(i, extra="\n| AC-2 | refund day 15 | 409 |\n")  # approved again after `release`
        self.approve("REQUIREMENTS")
        row = [l.strip() for l in self.status().splitlines() if l.strip().startswith("- [-] Release")]
        with open(os.path.join(REPO, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        quoted = "[-] Release — release.md (written <日期>) does not list <种类> approved: run `release` again"
        self.assertIn("``%s``" % quoted, readme)
        self.assertNotIn("release.md was written (", readme)
        pattern = re.escape(quoted).replace(re.escape("<日期>"), r"\d{4}-\d{2}-\d{2}").replace(
            re.escape("<种类>"), "[A-Z]+")
        self.assertEqual(len(row), 1, row)
        self.assertRegex(row[0], "^- " + pattern + "$")


# ---------------------------------------------------------------- false block: read-only shell reads of the records
READS = ("cat aidlc-docs/lean.json",
         "cat aidlc-docs/lean.json && python3 .kiro/aidlc-lean/aidlc_lean.py status",  # blocked in the benchmark
         "ls -R src && cat aidlc-docs/lean.json && cat requirements.txt",
         "cd /tmp && cat aidlc-docs/lean.json 2>/dev/null; echo ---",
         "jq .checks aidlc-docs/lean.json",
         "cat aidlc-docs/lean.json | jq .checks",
         "tail -5 aidlc-docs/audit/*.jsonl",
         "ls aidlc-docs/audit/ && wc -l aidlc-docs/audit/*.jsonl",
         "grep -c STAGE_ aidlc-docs/audit/*.jsonl 2>&1",
         "head -c 200 .aidlc-lean/turn.json",
         "git log --oneline -3 && cat aidlc-docs/lean.json",
         "stat aidlc-docs/lean.json > /dev/null && echo ok")
WRITES = ("echo '{}' > aidlc-docs/lean.json",
          "cat /tmp/x > aidlc-docs/lean.json",
          "cat aidlc-docs/lean.json >> aidlc-docs/lean.json",
          "cat aidlc-docs/lean.json | tee aidlc-docs/lean.json",
          "cat aidlc-docs/lean.json && rm aidlc-docs/audit/a.jsonl",
          "ls aidlc-docs/audit && rm -f .aidlc-lean/turn.json",
          "cat aidlc-docs/lean.json | xargs rm",
          "tail -5 aidlc-docs/audit/a.jsonl | python3 -c 'import sys; print(sys.stdin.read())'",
          "cp /tmp/x aidlc-docs/lean.json",
          "sed -i '' s/x/y/ aidlc-docs/lean.json",
          "python3 -c \"open('aidlc-docs/lean.json','w')\"",
          "cat > aidlc-docs/lean.json <<EOF\n{}\nEOF",
          "cat aidlc-docs/lean.json $(rm aidlc-docs/audit/a.jsonl)",
          "cat aidlc-docs/lean.json <> aidlc-docs/lean.json",
          "git show HEAD:aidlc-docs/lean.json > aidlc-docs/lean.json",
          "cd aidlc-docs/audit && rm a.jsonl",
          "'cat' aidlc-docs/lean.json > aidlc-docs/audit/a.jsonl",
          "cat aidlc-docs/lean.json && python3 .kiro/aidlc-lean/aidlc_lean.py cr new x --owner payments --paths "
          "aidlc-docs/lean.json",
          "cat aidlc-docs/lean.json && python3 .kiro/aidlc-lean/aidlc_lean.py hook PreToolUse")
# still blocked: other programs that read (the file-read tool is the way for them)
OTHER_READS = ("sed -n 1,20p aidlc-docs/lean.json", "awk 'NR<5' aidlc-docs/lean.json",
               "find aidlc-docs/audit -name '*.jsonl'", "python3 -m json.tool aidlc-docs/lean.json")


class ShellReads(Fix31):
    def test_reading_the_records_passes_and_writing_them_is_still_blocked(self):
        self.intent()
        for c in READS:
            r = self.bash(c)
            self.assertEqual(r.returncode, 0, (c, r.stderr))
        self.assertEqual(self.events("BLOCKED"), [])
        for c in WRITES + OTHER_READS:
            r = self.bash(c)
            self.assertEqual(r.returncode, 2, c)
            self.assertIn("blocked (records)", r.stderr, c)
        self.assertEqual(len(self.events("BLOCKED")), len(WRITES + OTHER_READS))


class ShellReadsRegulated(ShellReads):
    flags = ["--regulated"]


def kit_text(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


class ShellReadTexts(unittest.TestCase):
    def test_the_texts_say_which_shell_reads_pass_and_keep_the_file_read_tool_for_the_rest(self):
        construction = kit_text("kit", ".kiro", "skills", "aidlc-lean-construction", "SKILL.md")
        self.assertIn("Read them with a file-read tool (in the shell: only cat, head, tail, grep, ls or jq).",
                      construction)
        self.assertNotIn("Reading them is fine", construction)
        hook = json.loads(kit_text("kit", ".kiro", "hooks", "aidlc-lean-guard.json"))["hooks"][0]["description"]
        self.assertIn("A shell line that only reads the kit's records with cat, head, tail, grep, jq, ls and the like "
                      "passes; other shell commands that touch the kit's records (sed, awk, find, python, any write) "
                      "are blocked: read those with a file-read tool.", hook)
        readme = kit_text("README.md")
        limits = readme.split("## 已知限制")[1].split("\n## ")[0]
        self.assertNotIn("`cat aidlc-docs/lean.json`、`ls aidlc-docs/audit/`，11-08 实测碰到过）也会被拦", limits)
        self.assertIn("用 `sed`、`awk`、`find`、`python3` 这类程序读记录文件", limits)
        self.assertIn("改用读文件工具或 `lean status`", limits)
        gates = readme.split("## hook 会拦的事")[1].split("\n## ")[0]
        self.assertIn("只读的 shell 命令读审计日志、本机状态和 `aidlc-docs/lean.json`，不拦", gates)
        self.assertIn("照旧拦：改用读文件工具或 `lean status`", gates)


# ---------------------------------------------------------------- live-1: a stage recorded after `lean release`
RELEASE_DOC = "operations/release.md"


class BuildToRelease(Fix31):
    def build(self):
        """An intent built and verified in standard mode: what is left is the release."""
        self.cfg(checks=["true"])
        i = self.ready()
        self.skip_to_code()
        self.build_unit(i)
        return i


class RegulatedBuild:
    """Mixin: the same, in regulated mode (hash-bound approvals, the unit's PLAN approved)."""
    flags = ["--regulated"]

    def build(self):
        self.cfg(checks=["true"])
        i = self.intent()
        self.requirements(i, "small")
        for sid in ("application-design", "reverse-engineering", "user-stories", "units"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.approve("REQUIREMENTS")
        self.skip_to_code("app")
        self.ok("stage", "start", "code-generation", "--unit", "app")
        self.put(self.ipath(i, "construction/plans/app-code-generation-plan.md"), "# Plan\n\n- [x] 1. skeleton\n")
        self.approve("PLAN", "--unit", "app")
        self.ok("verify")
        self.ok("stage", "done", "code-generation", "--unit", "app", "--note", "built")
        return i


class StageRecordsAfterRelease(BuildToRelease):
    """A stage or phase record made after `lean release` and before the RELEASE approval was missing from the
    approved release.md. It now counts like a missing approval: `lean release` again."""

    def released_md(self):
        i = self.build()
        self.commit_all()
        self.ok("release")
        return i

    def test_live_1_a_phase_skip_after_release_needs_release_again(self):
        i = self.released_md()
        self.ok("stage", "skip", "operations", "--reason", "the platform team ships it")
        p = self.tool("request", "RELEASE")
        self.assertEqual(p.returncode, 1)
        self.assertIn("operations/release.md was written before Operations skipped: its Stages section is out of date "
                      "(run %srelease` again)" % LEAN, p.stdout)
        self.assertRegex("\n".join(self.progress(i)),
                         r"- \[-\] Release — release.md \(written \d{4}-\d{2}-\d{2}\) is older than Operations "
                         r"skipped: run `release` again")
        self.assertIn("%srelease` again (its Stages section is older than Operations skipped)" % LEAN, self.status())
        self.ok("release")
        self.assertIn("- [S] Operations — skipped: the platform team ships it", self.read(self.ipath(i, RELEASE_DOC)))
        self.approve("RELEASE")
        self.assertIn("- [x] Release — released", "\n".join(self.progress(i)))

    def test_live_1_the_approval_line_is_refused_for_a_stage_recorded_after_the_request(self):
        self.released_md()
        h = self.request_hash("RELEASE")
        self.ok("stage", "skip", "ci-pipeline", "--reason", "no CI here")
        out = self.say("approve RELEASE %s" % h)
        self.assertIn("NOT recorded", out.stdout + out.stderr)
        ref = self.events("APPROVAL_REFUSED")[-1]["data"]
        self.assertEqual(ref["check"], "release")
        self.assertIn("written before CI Pipeline skipped", ref["reason"])
        self.assertEqual([e for e in self.events("APPROVED") if e["data"]["kind"] == "RELEASE"], [])
        self.assertNotIn("[A] Release", self.status())

    def test_live_1_after_the_approval_operations_records_keep_it(self):
        i = self.released_md()
        self.approve("RELEASE")
        self.ok("stage", "skip", "operations", "--reason", "nothing to deploy")
        self.ok("stage", "start", "deployment-execution")
        lines = "\n".join(self.progress(i))
        self.assertIn("- [x] Release — released", lines)
        self.assertIn("- [-] Deployment Execution — in progress", lines)

    def test_live_1_records_before_release_are_part_of_it(self):
        i = self.build()
        self.ok("stage", "skip", "ci-pipeline", "--reason", "the platform team ships it")
        self.ok("stage", "skip", "operations", "--reason", "the platform team ships it")
        self.commit_all()
        self.ok("release")
        self.assertEqual(self.tool("request", "RELEASE").returncode, 0)
        seen = [e for e in self.events("STAGE_STARTED") if e["data"]["stage"] == "release"][-1]["data"]
        hashes = {e["hash"][:16] for e in self.events() if e.get("intent") == i and (
            e["event"] == "PHASE_SKIPPED" or (e["event"] in ("STAGE_STARTED", "STAGE_COMPLETED", "STAGE_SKIPPED")
                                              and e["data"].get("stage") not in ("release", "build-and-test")))}
        self.assertEqual(set(seen["stage_records"]), hashes)
        self.ok("verify")  # a verify on the same code records Build and Test again: it does not void release.md
        self.assertEqual(self.tool("request", "RELEASE").returncode, 0)

    def test_live_1_a_release_md_from_before_0_3_1_is_not_checked(self):
        i = self.released_md()
        path = os.path.join(self.dir, DOCS, "audit")
        for name in os.listdir(path):  # the release run as 0.3.0 logged it: no stage_records
            full = os.path.join(path, name)
            with open(full, encoding="utf-8") as f:
                lines = f.read().splitlines()
            with open(full, "w", encoding="utf-8") as f:
                for line in lines:
                    if '"stage_records"' in line:
                        e = json.loads(line)
                        del e["data"]["stage_records"]
                        line = json.dumps(e, ensure_ascii=False)
                    f.write(line + "\n")
        self.ok("stage", "skip", "operations", "--reason", "later")
        self.assertEqual(self.tool("request", "RELEASE").returncode, 0)
        self.assertIn("- [A] Release — waiting for approval", "\n".join(self.progress(i)))


class StageRecordsAfterReleaseRegulated(RegulatedBuild, StageRecordsAfterRelease):
    pass


class StageRecordsAfterReleaseTexts(unittest.TestCase):
    def test_live_1_the_steering_and_the_release_skill_say_when_stages_are_recorded(self):
        steering = kit_text("kit", ".kiro", "steering", "aidlc-lean.md")
        self.assertIn("**Operations** (optional; record or skip before `lean release`, or after the RELEASE approval;",
                      steering)
        release = kit_text("kit", ".kiro", "skills", "aidlc-lean-release", "SKILL.md")
        self.assertIn("after any code change, or a stage recorded or skipped since, run `lean verify` and `lean release` "
                      "again", release)


# ---------------------------------------------------------------- live-3: the approvers are named
class ApproversNamed(Fix31):
    def test_live_3_request_and_stage_progress_name_the_approvers(self):
        self.cfg(approvers={"INCEPTION": ["pm@corp.example", "lead@corp.example"],
                            "REQUIREMENTS": ["lead@corp.example", "dev@example.com"]})
        i = self.intent()
        self.requirements(i, "large")
        self.ok("stage", "start", "application-design")
        self.design(i)
        p = self.ok("request", "INCEPTION")
        only = "Only lead@corp.example may approve INCEPTION (approvers in aidlc-docs/lean.json)"
        self.assertIn(only + ".", p.stdout)
        lines = "\n".join(self.progress(i))
        self.assertRegex(lines, r"- \[A\] Requirements Analysis — waiting for approval: approve INCEPTION "
                         r"[0-9a-f]{8}; " + re.escape("only lead@corp.example may approve INCEPTION (approvers in "
                                                      "aidlc-docs/lean.json)"))
        self.assertIn("approve INCEPTION", self.status())
        p = self.ok("request", "REQUIREMENTS")
        self.assertIn("Only lead@corp.example, dev@example.com may approve REQUIREMENTS", p.stdout)
        self.cfg(approvers={"INCEPTION": ["pm@corp.example"], "REQUIREMENTS": ["dev@example.com"]})
        self.assertIn("Only no one (the approvers lists that apply have no email in common) may approve INCEPTION",
                      self.ok("request", "INCEPTION").stdout)

    def test_live_3_no_list_no_line(self):
        i = self.intent()
        self.requirements(i, "large")
        p = self.ok("request", "REQUIREMENTS")
        self.assertNotIn("may approve", p.stdout)
        self.assertNotIn("may approve", "\n".join(self.progress(i)))


# ---------------------------------------------------------------- live-5: no second start record
STORIES = "inception/user-stories/stories.md"


class StartTwice(Fix31):
    def started(self, sid):
        return [e for e in self.events("STAGE_STARTED") if e["data"]["stage"] == sid]

    def test_live_5_a_stage_in_progress_is_not_started_again(self):
        i = self.intent()
        p = self.ok("stage", "start", "requirements")  # `new` started it
        self.assertIn("Kept the existing %s. Requirements Analysis is already in progress (started " % self.req_path(i),
                      p.stdout)
        self.assertIn("nothing new recorded", p.stdout)
        self.assertEqual(len(self.started("requirements")), 1)
        for _ in range(2):
            self.ok("stage", "start", "user-stories")
            self.ok("stage", "start", "units")
        self.assertEqual((len(self.started("user-stories")), len(self.started("units"))), (1, 1))
        self.fill(self.ipath(i, STORIES), "\n| US-1 | buyer | refund | AC-1 |\n")
        self.ok("stage", "done", "user-stories", "--note", "one story")
        self.ok("stage", "start", "user-stories")  # re-opening a done stage is a new record
        self.assertEqual(len(self.started("user-stories")), 2)
        self.assertIn("- [-] User Stories — in progress", self.progress(i))

    def test_live_5_after_new_with_ideation(self):
        p = self.ok("new", "idea", "--ideation")
        self.ok("stage", "start", "intent-capture")
        self.assertEqual(len(self.started("intent-capture")), 1)
        self.ok("stage", "skip", "ideation", "--reason", "not now")  # a start after a phase skip re-opens it
        self.ok("stage", "start", "intent-capture")
        self.assertEqual(len(self.started("intent-capture")), 2)
        self.assertTrue(p.stdout)


# ---------------------------------------------------------------- live-2: edited pages are recorded again
class EditedSinceTexts(unittest.TestCase):
    def test_live_2_ideation_and_inception_record_an_edited_stage_again_before_the_request(self):
        line = ("Record a stage marked `(edited since)` again (`lean stage done`, noting what changed) before the "
                "request.")
        for skill in ("aidlc-lean-ideation", "aidlc-lean-inception"):
            self.assertIn(line, kit_text("kit", ".kiro", "skills", skill, "SKILL.md"), skill)


# ---------------------------------------------------------------- live-6: commitments are not invented
class CommitmentTexts(unittest.TestCase):
    def test_live_6_the_brief_template_and_the_ideation_skill_never_guess_a_commitment(self):
        brief = kit_text("kit", ".kiro", "aidlc-lean", "templates", "initiative-brief.md")
        self.assertIn('"yes" only when the PM (or the person who decides) said so; otherwise write "not confirmed (ask '
                      '<who>)", never a guess.', brief)
        ideation = kit_text("kit", ".kiro", "skills", "aidlc-lean-ideation", "SKILL.md")
        self.assertIn("stakeholders, dates or commitments (budget, people): they come from the PM or a named source",
                      ideation)
        self.assertIn('an unconfirmed commitment is "not confirmed (ask <who>)"', ideation)


# ---------------------------------------------------------------- live-7: after RELEASE, pages only
class AfterReleaseOpsTexts(unittest.TestCase):
    def test_live_7_the_operations_skill_keeps_product_config_out_of_a_released_intent(self):
        ops = kit_text("kit", ".kiro", "skills", "aidlc-lean-operations", "SKILL.md")
        self.assertIn("After RELEASE, write pages only. Product config (CI or deploy jobs, manifests, an alarm "
                      "threshold) is a new intent; in standard mode a small edit may go in, named in the stage note "
                      "and followed by `lean verify`", ops)
        self.assertIn("Regulated mode: always a new intent.", ops)
        self.assertNotIn("follows the released-intent rule", ops)


# ---------------------------------------------------------------- live-8: design changes after RELEASE
class AfterReleaseDesignTexts(unittest.TestCase):
    def test_live_8_the_release_skill_sends_design_changes_to_a_new_intent(self):
        release = kit_text("kit", ".kiro", "skills", "aidlc-lean-release", "SKILL.md")
        self.assertIn("only its Operations pages and ci-pipeline still take edits and stage commands", release)
        self.assertIn("Design changes, follow-ups and fixes start a new intent (`lean new <slug>`)", release)


if __name__ == "__main__":
    unittest.main()
