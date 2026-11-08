"""Regression tests for the fixes from the live Kiro 3.1.0 runs of AI-DLC Lean v0.2 (2026-11-08: regulated,
multi-team, multi-day resume, brownfield with the pstack pack).

Covers: subagent starts and prompts (Kiro runs the workspace SessionStart and UserPromptSubmit hooks for a subagent
with the parent chat's session_id; its prompt is the one the agent dispatched), change requests that unlock only
for the requesting team while open (`cr close`), mid-plan progress, '(edited since)' for completed stages including
the code-generation plan, the Next step once the review is written, the wording about the review context, refused
approvals in the ledger, the base commit and working tree of a verify, `release` refusing uncommitted product code,
superseded approvals in release.md, approvals in the Stage log, who recorded each entry, the owner team in
multi-team mode and each team's own Next items, `init --team` in a configured clone, which events a per-intent
audit pack holds, and the Session notes reminder of `request`.

Run: python3 -m unittest discover -s tests -v
"""
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_aidlc_lean import REPO, SUMMARY  # noqa: E402
from test_v02_stages import V02  # noqa: E402

KIT_SCRIPT = os.path.join(REPO, "kit", ".kiro", "aidlc-lean", "aidlc_lean.py")
PLAN = "construction/plans/%s-code-generation-plan.md"
REVIEW = "construction/build-and-test/review.md"
RELEASE = "operations/release.md"
BEGIN = "<!-- lean:begin progress -->"
END = "<!-- lean:end progress -->"
LEAN = "`python3 .kiro/aidlc-lean/aidlc_lean.py "
SESSION = "sess_5325d81c-9db8-4fe3-b2d0-8e7894164ddc"  # the shape Kiro 3.1.0 sends
UNIT_DESIGNS = ("functional-design", "nfr-design", "infrastructure-design")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def epoch(ts):
    return datetime.strptime(ts[:23], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc).timestamp()


def load_kit():
    spec = importlib.util.spec_from_file_location("aidlc_lean_live_fixes", KIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no __pycache__ in kit/
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


class Live(V02):
    def turn(self):
        return json.loads(self.read(".aidlc-lean/turn.json"))

    def section(self, text, title):
        """The lines of a `## <title> (n)` section of audit.md."""
        m = re.search(r"(?ms)^## %s \(\d+\)\n(.*?)(?=^## |\Z)" % re.escape(title), text)
        self.assertIsNotNone(m, title)
        return [l for l in m.group(1).splitlines() if re.match(r"- \d{4}-\d{2}-\d{2}T", l)]

    def skip_to_code(self, unit=None, team=None):
        """Record every Inception stage left and the unit's design stages as skipped."""
        extra = ["--unit", unit] if unit else []
        if unit is None:
            for sid in ("reverse-engineering", "user-stories", "units"):
                self.ok("stage", "skip", sid, "--reason", "not needed")
        for sid in UNIT_DESIGNS:
            self.ok("stage", "skip", sid, *extra, "--reason", "not needed", team=team)

    def build_unit(self, intent, unit="app", team=None):
        """The unit's plan with every step ticked, a passing verify, and `stage done code-generation`."""
        self.ok("stage", "start", "code-generation", "--unit", unit, team=team)
        self.put(self.ipath(intent, PLAN % unit), "# Plan: %s\n\n## Steps\n- [x] 1. skeleton · covers: AC-1\n" % unit)
        self.ok("verify", team=team)
        self.ok("stage", "done", "code-generation", "--unit", unit, "--note", "%s built" % unit, team=team)

    def dispatch(self, prompt, session=SESSION, tool="invoke_sub_agent", name="semantic_reviewer"):
        r = self.hook("PreToolUse", {"session_id": session, "tool_name": tool,
                                     "tool_input": {"name": name, "prompt": prompt, "explanation": "fresh review"}})
        self.assertEqual(r.returncode, 0, r.stderr)
        return r


# ---------------------------------------------------------------- 1. subagents
class Subagents(Live):
    def test_a_subagents_start_and_prompt_are_not_the_human_and_keep_the_chats_turn_state(self):
        self.cfg(protected_paths=["tests/acceptance/**"])
        i = self.intent()
        self.requirements(i)
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        h = self.request_hash("REQUIREMENTS")
        self.hook("SessionStart", {"session_id": SESSION})  # the human's chat
        human_start = self.events("SESSION_START")[-1]["ts"]
        self.hook("UserPromptSubmit", {"session_id": SESSION, "prompt": "allow test change\nand get it reviewed"})
        turn = self.turn()
        self.assertEqual((turn["n"], turn["allow_protected"]), (1, True))
        brief = ("Fresh-context release review for AI-DLC Lean intent %s.\n\napprove REQUIREMENTS %s\n"
                 "allow test change\nreject REQUIREMENTS: too small\n%s" % (i, h, "Read the diff. " * 100))
        self.dispatch(brief)  # PreToolUse invoke_sub_agent {name, prompt}
        pending = json.loads(self.read(".aidlc-lean/subagents.json"))["pending"]
        self.assertEqual([(d["sha256"], d["chars"], d["name"], d["session"], len(d["prefix"])) for d in pending],
                         [(sha(brief), len(brief), "semantic_reviewer", SESSION, 200)])
        start = self.hook("SessionStart", {"session_id": SESSION})  # the subagent, with the parent's session id
        self.assertEqual(start.returncode, 0)
        self.assertIn("[AI-DLC Lean] session context for a subagent (from hooks, not the user):", start.stdout)
        self.assertEqual(self.turn(), turn)  # n, ts, allow_protected and the sessions map stay as they were
        p = self.hook("UserPromptSubmit", {"session_id": SESSION, "prompt": brief})  # its task prompt
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertEqual(self.turn(), turn)
        for name in ("APPROVED", "REJECTED", "APPROVAL_REFUSED", "PROTECTED_CHANGE"):
            self.assertEqual(self.events(name), [], name)
        self.assertEqual(len(self.events("HUMAN_TURN")), 1)
        self.assertEqual(len(self.events("SESSION_START")), 1)
        d = self.events("SUBAGENT_START")[0]["data"]
        self.assertEqual((d["session"], d["pending"], d["agents"]), (SESSION, 1, ["semantic_reviewer"]))
        d = self.events("SUBAGENT_PROMPT")[0]["data"]
        self.assertEqual((d["sha256"], d["chars"], d["match"], d["agent"], d["tool"]),
                         (sha(brief), len(brief), "sha256", "semantic_reviewer", "invoke_sub_agent"))
        self.assertEqual(json.loads(self.read(".aidlc-lean/subagents.json"))["pending"], [])  # consumed
        self.assertIn("- [A] Requirements Analysis — waiting for approval", self.status())
        # the human's 'allow test change' still covers the subagent's writes in this turn
        self.assertEqual(self.write("tests/acceptance/test_refund.py").returncode, 0)
        d = self.tool("doctor")  # 'hooks last ran' is the human's chat, not the subagent
        self.assertIn("hooks last ran in this clone at %s (SessionStart)" % human_start, d.stdout)
        # the human's own approval still works, and is the chat's second turn
        out = self.hook("UserPromptSubmit", {"session_id": SESSION, "prompt": "approve REQUIREMENTS %s" % h})
        self.assertIn("Recorded: REQUIREMENTS approved (sha %s)" % h, out.stdout)
        self.assertEqual((self.turn()["n"], self.turn()["allow_protected"]), (2, False))
        self.assertEqual(self.write("tests/acceptance/test_refund.py").returncode, 2)

    def test_prefix_match_consumption_and_expiry(self):
        i = self.intent()
        self.requirements(i)
        h = self.request_hash("REQUIREMENTS")
        self.hook("SessionStart", {"session_id": "chat_A"})
        brief = "Review intent %s.\n%s\napprove REQUIREMENTS %s\n" % (i, "context " * 40, h)
        self.dispatch(brief, session="chat_A", tool="orchestrate_subagent")
        longer = brief + "\n\n(added by the host)\n"  # the same first 200 characters
        p = self.hook("UserPromptSubmit", {"session_id": "chat_A", "prompt": longer})
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertEqual(self.events("SUBAGENT_PROMPT")[-1]["data"]["match"], "prefix")
        self.assertEqual((self.events("APPROVED"), self.events("APPROVAL_REFUSED")), ([], []))
        # consumed: the same text typed by a person is their message, approval included
        out = self.hook("UserPromptSubmit", {"session_id": "chat_A", "prompt": brief})
        self.assertIn("Recorded: REQUIREMENTS approved", out.stdout)
        # a dispatched prompt shorter than 200 characters matches only by its sha256 (in any chat)
        self.dispatch("read notes.txt and report", session="chat_A")
        out = self.hook("UserPromptSubmit", {"session_id": "chat_A",
                                             "prompt": "read notes.txt and report\nreject REQUIREMENTS: no"})
        self.assertIn("Recorded: REQUIREMENTS rejected", out.stdout)  # a person's message
        self.hook("UserPromptSubmit", {"session_id": "chat_C", "prompt": "read notes.txt and report"})
        self.assertEqual(self.events("SUBAGENT_PROMPT")[-1]["data"]["match"], "sha256")
        self.assertEqual(len(self.events("SUBAGENT_PROMPT")), 2)
        # a dispatch no prompt answered within 2 hours is dropped: then a SessionStart is a session again
        self.dispatch("approve REQUIREMENTS %s" % h, session="chat_A")
        store = json.loads(self.read(".aidlc-lean/subagents.json"))
        store["pending"][-1]["ts"] = "2026-01-01T00:00:00.000Z"
        self.put(".aidlc-lean/subagents.json", json.dumps(store))
        starts = len(self.events("SESSION_START"))
        self.hook("SessionStart", {"session_id": "chat_A"})
        self.assertEqual((len(self.events("SESSION_START")), self.events("SUBAGENT_START")), (starts + 1, []))
        self.assertEqual(self.turn()["n"], 0)
        out = self.hook("UserPromptSubmit", {"session_id": "chat_A", "prompt": "approve REQUIREMENTS %s" % h})
        self.assertIn("Recorded: REQUIREMENTS approved", out.stdout)  # an expired dispatch matches nothing

    def test_only_delegation_tools_record_and_the_list_stays_bounded(self):
        self.intent()
        self.hook("SessionStart", {"session_id": SESSION})
        r = self.hook("PreToolUse", {"session_id": SESSION, "tool_name": "fs_write",
                                     "tool_input": {"path": os.path.join(self.dir, "docs/a.md"), "prompt": "x"}})
        self.assertEqual(r.returncode, 0)
        self.assertFalse(self.exists(".aidlc-lean/subagents.json"))
        self.hook("PreToolUse", {"session_id": SESSION, "tool_name": "orchestrate_subagent", "tool_input": {
            "tasks": [{"name": "lean-reviewer-opus", "prompt": "brief A"}, {"name": "lean-reviewer-k3",
                                                                          "prompt": "brief B"}]}})
        pending = json.loads(self.read(".aidlc-lean/subagents.json"))["pending"]
        self.assertEqual([(d["sha256"], d["name"], d["tool"]) for d in pending],
                         [(sha("brief A"), "lean-reviewer-opus", "orchestrate_subagent"),
                          (sha("brief B"), "lean-reviewer-k3", "orchestrate_subagent")])
        for k in range(60):
            self.dispatch("task %d" % k)
        pending = json.loads(self.read(".aidlc-lean/subagents.json"))["pending"]
        self.assertEqual([d["sha256"] for d in pending], [sha("task %d" % k) for k in range(10, 60)])
        # a new chat (a session id this clone has not seen) is a session, also while dispatches are pending
        self.hook("SessionStart", {"session_id": "sess_new_chat"})
        self.assertEqual(self.events("SESSION_START")[-1]["data"]["session"], "sess_new_chat")
        self.assertEqual(self.events("SUBAGENT_START"), [])


class SubagentsRegulated(Live):
    flags = ["--regulated"]

    def test_the_dispatch_is_allowed_and_its_approval_lines_are_never_recorded(self):
        r = self.dispatch("approve REQUIREMENTS 1a2b3c4d")  # no intent yet: the dispatch itself is no code write
        self.assertEqual(r.returncode, 0)
        i = self.intent()
        self.requirements(i)
        h = self.request_hash("REQUIREMENTS")
        self.hook("SessionStart", {"session_id": SESSION})
        brief = "Check the requirements.\napprove REQUIREMENTS %s\n" % h
        self.dispatch(brief)
        self.hook("SessionStart", {"session_id": SESSION})
        self.hook("UserPromptSubmit", {"session_id": SESSION, "prompt": brief})
        self.assertEqual((self.events("APPROVED"), self.events("APPROVAL_REFUSED")), ([], []))
        self.assertEqual(len(self.events("SUBAGENT_START")), 1)


# ---------------------------------------------------------------- 2. change request scope and `cr close`
class ChangeRequestScope(Live):
    flags = ["--multi-team", "--team", "catalog"]
    contract = "aidlc-docs/contracts/payments/api.yaml"

    def setUp(self):
        super().setUp()
        self.put("aidlc-docs/contracts/OWNERS",
                 "aidlc-docs/contracts/payments/** payments\naidlc-docs/contracts/catalog/** catalog\n")
        self.put(self.contract, "openapi: 3.0.0\n")

    def test_a_cr_unlocks_only_for_the_requesting_team_and_only_while_open(self):
        i = self.intent()
        self.ok("cr", "new", "refund-reason", "--owner", "payments", "--paths", self.contract)
        self.assertIn("Change requests involving your team: CR-catalog-1 (open, waiting for team payments)", self.status())
        out, _ = self.approve("CR-catalog-1")  # the requesting team cannot approve it: refused, and recorded
        self.assertIn("needs someone from team payments", out.stdout)
        self.assertEqual(self.events("APPROVAL_REFUSED")[-1]["data"]["check"], "team")
        out, _ = self.approve("CR-catalog-1", team="payments")
        self.assertIn("Recorded: CR-catalog-1 approved", out.stdout)
        self.assertEqual(self.write(self.contract).returncode, 0)  # the requesting team
        r = self.write(self.contract, team="web")  # a third team
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (contract)", r.stderr)
        self.assertEqual(self.write(self.contract, team="payments").returncode, 0)  # owners need no CR
        self.assertIn("Change requests involving your team: CR-catalog-1 (open, approved)", self.status())
        self.assertIn("Change requests involving your team: CR-catalog-1 (open, approved)",
                      self.tool("status", team="payments").stdout)
        p = self.tool("cr", "close", "CR-catalog-1", "--reason", "mine now", team="web")
        self.assertEqual(p.returncode, 1)
        self.assertIn("Only team catalog or team payments can close CR-catalog-1 (this clone is team web).", p.stdout)
        p = self.tool("cr", "close", "CR-catalog-1")
        self.assertEqual(p.returncode, 1)
        self.assertIn("`cr close` needs --reason", p.stdout)
        p = self.ok("cr", "close", "CR-catalog-1", "--reason", "receipt field shipped in 00629d7")
        self.assertIn("Closed CR-catalog-1: it no longer unlocks %s for team catalog." % self.contract, p.stdout)
        d = self.events("CR_CLOSED")[-1]["data"]
        self.assertEqual((d["id"], d["reason"], d["owner_team"], d["requested_by"]),
                         ("CR-catalog-1", "receipt field shipped in 00629d7", "payments", "catalog"))
        for team in (None, "web"):  # after the close no other team can edit the contract
            r = self.write(self.contract, team=team)
            self.assertEqual(r.returncode, 2, team)
            self.assertIn("blocked (contract)", r.stderr)
        self.assertIn("Change requests involving your team: CR-catalog-1 (closed)", self.status())
        self.assertNotIn("waiting for your team", self.tool("status", team="payments").stdout)
        p = self.tool("request", "CR-catalog-1", team="payments")
        self.assertEqual(p.returncode, 1)
        self.assertIn("CR-catalog-1 was closed on ", p.stdout)
        out = self.say("approve CR-catalog-1 1a2b3c4d", team="payments")
        self.assertIn("Approval of CR-catalog-1 NOT recorded: CR-catalog-1 was closed", out.stdout)
        p = self.tool("cr", "close", "CR-catalog-1", "--reason", "again")
        self.assertEqual(p.returncode, 1)
        self.assertIn("CR-catalog-1 is already closed", p.stdout)
        # the owner team may close a CR too
        self.ok("cr", "new", "tax-field", "--owner", "payments", "--paths", self.contract)
        self.ok("cr", "close", "CR-catalog-2", "--reason", "not needed after all", team="payments")
        self.ok("audit", "pack")
        pack = self.read(self.ipath(i, "audit.md"))
        self.assertIn("- State now: CR-catalog-1 closed; CR-catalog-2 closed", pack)
        rows = self.section(pack, "Contract change requests")
        self.assertEqual([r.split(" · ")[1] for r in rows], ["CR_OPENED", "CR_CLOSED", "CR_OPENED", "CR_CLOSED"])
        self.assertIn("CR-catalog-1 closed — receipt field shipped in 00629d7", rows[1])
        self.assertIn(" · dev@example.com (payments) · via CLI · CR-catalog-2 closed", rows[3])


# ---------------------------------------------------------------- 3. mid-plan progress
class MidPlan(Live):
    def test_next_build_and_test_and_stage_done_follow_the_plan_steps(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.skip_to_code()
        self.ok("stage", "start", "code-generation")
        plan = self.ipath(i, PLAN % "app")
        long_step = "2. refunds within 14 days, " + "with the partial-refund rules from BR-3 " * 4
        self.put(plan, "# Plan\n\n## Steps\n- [x] 1. skeleton · covers: AC-1\n  * [ ] 1a. health check\n"
                       "- [ ] %s\n\n## Tests\n| AC / BR | Test |\n|---|---|\n| AC-1 | t::a |\n" % long_step)
        self.put("src/app.py", "x = 1\n")
        self.ok("verify")  # step 1 done and verified: the unit is not
        st = self.status()
        self.assertIn("Next: continue the code-generation plan of unit app: step 2 of 3 (1a. health check); tick each "
                      "step when it is done (skill aidlc-lean-construction)", st)
        self.assertIn("- [-] Code Generation (app) — in progress", st)
        self.assertRegex(st, r"- \[-\] Build and Test — verify PASS on partial code · \d{4}-\d{2}-\d{2} \d{2}:\d{2} "
                             r"UTC \(code fingerprint [0-9a-f]{8}\); code generation not done yet: app\n")
        p = self.tool("stage", "done", "code-generation", "--note", "all done")
        self.assertEqual(p.returncode, 1)
        self.assertIn("has 2 unticked steps of 3 (the first: step 2, 1a. health check)", p.stdout)
        self.assertEqual([e for e in self.events("STAGE_COMPLETED") if e["data"]["stage"] == "code-generation"], [])
        self.put(plan, self.read(plan).replace("* [ ] 1a.", "* [X] 1a."))
        shown = " ".join(long_step.split())[:97] + "..."  # the step text is shortened
        self.assertIn("Next: continue the code-generation plan of unit app: step 3 of 3 (%s);" % shown, self.status())
        p = self.tool("stage", "done", "code-generation", "--note", "all done")
        self.assertIn("has 1 unticked step of 3 (the first: step 3, ", p.stdout)
        self.put(plan, self.read(plan).replace("- [ ] 2.", "- [x] 2."))
        self.assertIn("Next: record the stages that have no record yet (%sstage done <id> --note ...` or `stage skip "
                      "<id> --reason ...`): Code Generation (app)" % LEAN, self.status())
        self.ok("stage", "done", "code-generation", "--note", "steps 1-2 done; AC-1 -> t::a")
        st = self.status()
        self.assertIn("- [x] Build and Test — verify PASS · ", st)
        self.assertIn("- [x] Code Generation (app) — done · ", st)

    def test_steps_are_the_boxes_plan_sha256_normalises(self):
        L = load_kit()
        text = ("- [x] 1. a\n  * [ ] 1a. b\n- [X] 2. c\n-  [ ] not a box (two spaces)\n  - [ ]no space after\n"
                "+ [ ] not a bullet\n| - [ ] in a table |\n- [ ] 3. d\r\n")
        path = os.path.join(self.dir, "plan.md")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        steps = L.plan_steps(path)
        self.assertEqual(len(L.CHECKBOX_RE.findall(text.encode())), steps.total)
        self.assertEqual((steps.total, steps.open, steps.first, steps.text), (5, 3, 2, "1a. b"))
        ticked = re.sub(r"(?m)^([ \t]*[-*] )\[ \]", r"\1[x]", text)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(ticked)
        self.assertEqual(L.plan_steps(path)[:3], (5, 0, None))
        self.assertEqual(L.plan_sha256(path), hashlib.sha256(text.replace("[x]", "[ ]").replace("[X]", "[ ]")
                                                             .encode()).hexdigest())
        self.assertIsNone(L.plan_steps(os.path.join(self.dir, "missing.md")))


# ---------------------------------------------------------------- 4. (edited since)
class EditedSince(Live):
    def test_completed_stages_show_edits_and_a_new_record_clears_them(self):
        i = self.ready()
        today = time.strftime("%Y-%m-%d", time.gmtime())
        self.ok("stage", "start", "functional-design")
        fd = self.ipath(i, "construction/app/functional-design/functional-design.md")
        self.fill(fd, "\n- BR-1: refunds within 14 days\n")
        self.ok("stage", "done", "functional-design", "--note", "BR-1")
        self.assertRegex(self.status(), r"- \[x\] Functional Design \(app\) — done · \d{4}-\d{2}-\d{2}\n")
        self.fill(fd, "\n- BR-2: partial refunds\n")
        self.assertIn("- [x] Functional Design (app) — done · %s (edited since)\n" % today, self.status())
        self.ok("stage", "done", "functional-design", "--note", "BR-2 added after the review")
        self.assertNotIn("(edited since)", self.status())
        state = self.state(i)
        self.assertEqual(state.count("### Functional Design (app) · "), 2)  # recording again adds an entry
        self.assertIn("- Did: BR-2 added after the review", state)
        self.assertIn("- Outputs: construction/app/functional-design/functional-design.md (sha %s)" % self.sha(fd)[:8],
                      state)
        # the code-generation plan: ticking or unticking a box is no edit, editing a step is
        self.ok("stage", "start", "code-generation")
        plan = self.ipath(i, PLAN % "app")
        text = "# Plan\n- [x] 1. skeleton · covers: AC-1\n- [x] 2. refunds · covers: AC-2\n"
        self.put(plan, text)
        self.ok("stage", "done", "code-generation", "--note", "both steps")
        ev = [e for e in self.events("STAGE_COMPLETED") if e["data"]["stage"] == "code-generation"][-1]
        self.assertEqual(ev["data"]["plan_sha256"], sha(text.replace("[x]", "[ ]")))
        self.assertEqual(ev["data"]["outputs"], {plan: sha(text)})
        self.put(plan, text.replace("- [x] 2.", "- [ ] 2."))
        self.assertRegex(self.status(), r"- \[x\] Code Generation \(app\) — done · \d{4}-\d{2}-\d{2}\n")
        self.put(plan, text.replace("2. refunds", "2. refunds and partial refunds"))
        self.assertIn("- [x] Code Generation (app) — done · %s (edited since)\n" % today, self.status())
        # requirements recorded as done, not requested yet, then edited
        j = self.intent("other")
        self.requirements(j)
        self.ok("stage", "done", "requirements", "--note", "AC-1")
        self.assertIn("- [-] Requirements Analysis — done · %s; waiting for `request REQUIREMENTS`" % today,
                      self.status())
        self.requirements(j, extra="\n| AC-2 | refund day 20 | 409 |\n")
        self.assertIn("- [-] Requirements Analysis — done · %s (edited since); waiting for `request REQUIREMENTS` (or "
                      "INCEPTION)" % today, self.status())


# ---------------------------------------------------------------- 5. the Next step after the review; wording
class ReviewThenRelease(Live):
    def test_release_is_next_once_the_review_is_newer_than_the_last_verify_and_code_write(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.skip_to_code()
        self.build_unit(i)
        hint = "Next: review in a new chat or by a subagent that did not write the code, then %srelease` (skill " \
               "aidlc-lean-release)" % LEAN
        self.assertIn(hint, self.status())
        self.put(self.ipath(i, REVIEW), "# Review\n\n| finding | severity | file:line | fix |\n|---|---|---|---|\n")
        review = os.path.join(self.dir, self.ipath(i, REVIEW))
        later = time.time() + 3600
        os.utime(review, (later, later))
        done = ("Next: run %srelease`; the review (construction/build-and-test/review.md) is newer than the last "
                "verify and code change (skill aidlc-lean-release)" % LEAN)
        self.assertIn(done, self.status())
        self.assertIn(done, self.hook("SessionStart", {}).stdout)
        before = epoch(self.events("VERIFY")[-1]["ts"]) - 60
        os.utime(review, (before, before))  # written before the last verify: it reviewed older code
        self.assertIn(hint, self.status())
        os.utime(review, (later, later))
        self.assertEqual(self.write("src/app.py").returncode, 0)  # a code write the hook let through ...
        counters = json.loads(self.read(".aidlc-lean/counters.json"))
        self.assertAlmostEqual(epoch(counters["last_code_write"]), time.time(), delta=120)
        counters["last_code_write"] = "2099-01-01T00:00:00.000Z"  # ... after the review was written
        self.put(".aidlc-lean/counters.json", json.dumps(counters))
        self.assertIn(hint, self.status())

    def test_no_fresh_session_wording_and_the_resumed_block_says_it_is_the_same_chat(self):
        with open(KIT_SCRIPT, encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("review in a fresh session", source)
        self.assertNotIn("fresh session", source)
        self.intent()
        self.say("hello")
        turn = self.turn()
        turn["ts"], turn["sessions"] = "2026-01-01T00:00:00.000Z", {}
        self.put(".aidlc-lean/turn.json", json.dumps(turn))
        out = self.say("back after the weekend").stdout
        self.assertRegex(out, r"Resumed after \d+ h\. This is the same chat resumed, not a fresh context\. Current "
                              r"status \(pull first if teammates may have pushed\):")


# ---------------------------------------------------------------- 6. refused approvals
class RefusedApprovals(Live):
    flags = ["--regulated"]

    def test_every_refused_approval_line_is_recorded_with_its_reason(self):
        self.cfg(checks=["true"])
        i = self.intent()
        self.requirements(i)
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        h = self.request_hash("REQUIREMENTS")
        self.assertIn("needs the hash", self.say("approve REQUIREMENTS").stdout)
        out = self.say("approve REQUIREMENTS deadbeef (via feishu bridge token=s3cr3t-value)")
        self.assertIn("NOT recorded: the file changed since that request", out.stdout)
        self.cfg(approvers={"REQUIREMENTS": ["lead@example.com"]})
        self.assertIn("not in approvers for REQUIREMENTS", self.say("approve REQUIREMENTS %s" % h).stdout)
        self.cfg(approvers={})
        rel = self.ipath(i, RELEASE)
        self.put(rel, "# Release\n\nwritten by hand\n")
        out = self.say("approve RELEASE %s" % self.sha(rel)[:8])
        self.assertIn("Approval of RELEASE NOT recorded: operations/release.md was not written by", out.stdout)
        self.units(i, [("api", "core", "src/api/**"), ("web", "core", "src/web/**")])
        for u in ("api", "web"):
            self.ok("stage", "start", "code-generation", "--unit", u)
        self.assertIn("several code-generation plans (api, web)", self.say("approve PLAN").stdout)
        refused = self.events("APPROVAL_REFUSED")
        self.assertEqual([(e["data"]["kind"], e["data"]["check"]) for e in refused],
                         [("REQUIREMENTS", "hash"), ("REQUIREMENTS", "hash"), ("REQUIREMENTS", "approvers"),
                          ("RELEASE", "release"), ("PLAN", "target")])
        d = refused[1]["data"]
        self.assertEqual((d["given"], d["path"], d["sha256"], d["session"]),
                         ("deadbeef", self.req_path(i), self.sha(self.req_path(i)), "sess_test"))
        self.assertTrue(d["words"].startswith("approve REQUIREMENTS deadbeef (via feishu bridge token=***"))
        self.assertNotIn("s3cr3t-value", json.dumps(refused))  # masked
        self.assertIn("you approved deadbeef, current is %s" % h, d["reason"])
        self.assertNotIn("given", refused[0]["data"])
        self.assertIn("regulated mode needs the hash shown in the request", refused[0]["data"]["reason"])
        self.assertEqual(self.events("APPROVED"), [])
        state = self.state(i)  # the Stage log lists them
        self.assertRegex(state, r"### REQUIREMENTS approval refused \(no hash typed\) · \d{4}-\d{2}-\d{2} \d{2}:\d{2} "
                                r"UTC · by dev@example.com \(team -\) · human \(prompt\)\n- Reason: regulated mode "
                                r"needs the hash")
        self.assertIn("### REQUIREMENTS approval refused (typed deadbeef) · ", state)
        self.assertIn("### PLAN approval refused (no hash typed) · ", state)
        self.ok("audit", "pack")
        rows = self.section(self.read(self.ipath(i, "audit.md")), "Approvals and rejections")
        refused_rows = [r for r in rows if " · APPROVAL_REFUSED · " in r]
        self.assertEqual(len(refused_rows), 5)
        self.assertIn(" · dev@example.com (-) · human (prompt) · REQUIREMENTS refused (typed deadbeef) — the file "
                      "changed since that request", refused_rows[1])
        self.assertNotIn("s3cr3t-value", self.read(self.ipath(i, "audit.md")))


# ---------------------------------------------------------------- 7, 8. verify's base commit; release needs it committed
class CommittedCode(Live):
    def test_verify_names_the_base_commit_and_the_working_tree(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.commit_all("base")
        head = self.sh(["git", "rev-parse", "HEAD"]).stdout.strip()
        self.ok("verify")
        text = self.read(self.ipath(i, SUMMARY))
        self.assertRegex(text, r"\n- base commit \(HEAD at verify time\): %s \(\S+\)\n- working tree: clean\n" % head[:12])
        self.assertNotIn("- commit:", text)
        d = self.events("VERIFY")[-1]["data"]
        self.assertEqual((d["base_commit"], d["uncommitted"]), (head, 0))
        self.put("src/app.py", "x = 1\n")
        self.put("src/refunds/rules.py", "y = 2\n")  # an untracked folder: each file counts
        self.put(self.ipath(i, "notes.md"), "records do not count\n")
        self.put("aidlc-docs/contracts/api.yaml", "openapi: 3.0.0\n")  # contracts are product code
        self.ok("verify")
        self.assertIn("\n- working tree: 3 uncommitted product changes (the code fingerprint, not the commit, names "
                      "the verified code)\n", self.read(self.ipath(i, SUMMARY)))
        self.assertEqual(self.events("VERIFY")[-1]["data"]["uncommitted"], 3)
        self.commit_all("code")
        self.put("src/app.py", "x = 2\n")
        self.ok("verify")
        self.assertIn("- working tree: 1 uncommitted product change (", self.read(self.ipath(i, SUMMARY)))
        self.ok("audit", "pack")
        self.assertIn("· base commit %s + 1 uncommitted product change(s)" %
                      self.sh(["git", "rev-parse", "HEAD"]).stdout.strip()[:12], self.read(self.ipath(i, "audit.md")))

    def test_release_refuses_uncommitted_product_changes(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.put("src/app.py", "x = 1\n")
        self.ok("verify")
        r = self.tool("release")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Not ready to release: commit the verified code first, then run `python3 "
                      ".kiro/aidlc-lean/aidlc_lean.py release` (2 uncommitted product changes: .gitignore, src/app.py).",
                      r.stdout)
        self.assertFalse(self.exists(self.ipath(i, RELEASE)))
        self.commit_all()
        state = self.ipath(i, "aidlc-state.md")
        self.put(state, self.read(state) + "\n- a note\n")  # records may stay uncommitted
        self.ok("release")
        head = self.sh(["git", "rev-parse", "HEAD"]).stdout.strip()
        self.assertIn("- commit: %s (" % head, self.read(self.ipath(i, RELEASE)))


class RegulatedEvidence(Live):
    flags = ["--regulated"]

    def test_the_evidence_names_the_base_commit_and_the_working_tree(self):
        self.cfg(checks=["true"])
        self.intent()
        self.ok("verify")
        body = self.read(self.events("VERIFY")[-1]["data"]["evidence"])
        self.assertIn("- base commit (HEAD at verify time): none yet (", body)
        self.assertRegex(body, r"- working tree: \d+ uncommitted product changes? \(")


# ---------------------------------------------------------------- 9, 10, 14. approvals in release.md and the Stage log
class ApprovalRecords(Live):
    def test_release_md_marks_superseded_approvals(self):
        self.cfg(checks=["true"])
        i = self.intent()
        self.requirements(i, "large")
        self.ok("stage", "start", "application-design")
        self.design(i)
        _, h1 = self.approve("INCEPTION")
        self.requirements(i, "large", extra="\n| AC-2 | refund day 20 | 409 |\n")
        _, h2 = self.approve("INCEPTION")
        self.design(i, extra="\n## Data model\n- refunds\n")
        _, h3 = self.approve("DESIGN")
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        rows = [l for l in self.read(self.ipath(i, RELEASE)).splitlines() if l.startswith(("| INCEPTION", "| DESIGN"))]
        self.assertEqual([r.split(" | ")[0] for r in rows], [
            "| INCEPTION (superseded)", "| INCEPTION (superseded for inception/application-design/application-design.md)",
            "| DESIGN"])
        self.assertEqual([r.split(" | ")[2][:8] for r in rows], [h1, h2, h3])

    def test_the_stage_log_lists_approvals_in_recording_order_and_who_recorded_each_entry(self):
        i = self.intent()
        self.hook("SessionStart", {})
        self.requirements(i, "large")
        self.ok("stage", "done", "requirements", "--note", "AC-1")
        self.ok("stage", "start", "application-design")
        self.design(i)
        self.say("approve INCEPTION deadbeef")  # refused: the hash does not match
        self.say("reject INCEPTION: the data model is missing")
        rejected = self.events("REJECTED")[-1]["data"]["sha256"][:8]
        self.design(i, extra="\n## Data model\n- refunds\n")
        _, h = self.approve("INCEPTION")
        self.ok("stage", "skip", "user-stories", "--reason", "single persona")
        log = self.state(i).split("## Stage log")[1].split(END)[0]
        heads = [re.sub(r" · \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC · by dev@example.com \(team -\)", " · <when, who>", x)
                 for x in re.findall(r"(?m)^### (.+)$", log)]
        self.assertEqual(heads, ["Requirements Analysis · <when, who> · via CLI",
                                 "INCEPTION approval refused (typed deadbeef) · <when, who> · human (prompt)",
                                 "INCEPTION rejected (sha %s) · <when, who> · human (prompt)" % rejected,
                                 "INCEPTION approved (sha %s) · <when, who> · human (prompt)" % h,
                                 "User Stories · <when, who> · via CLI"])
        self.assertIn("- Covers: inception/application-design/application-design.md, "
                      "inception/requirements/requirements.md\n- Words: reject INCEPTION: the data model is missing",
                      log)
        self.assertIn("- Reason: the file changed since that request (you approved deadbeef, current is ", log)
        self.ok("audit", "pack")
        pack = self.read(self.ipath(i, "audit.md"))
        label = {"SESSION_START": "hook (session start)", "HUMAN_TURN": "human (prompt)",
                 "APPROVED": "human (prompt)", "REJECTED": "human (prompt)", "APPROVAL_REFUSED": "human (prompt)",
                 "APPROVAL_REQUESTED": "via CLI", "STAGE_COMPLETED": "via CLI", "STAGE_SKIPPED": "via CLI",
                 "INTENT_CREATED": "via CLI", "STAGE_STARTED": "via CLI"}
        rows = [l for l in pack.splitlines() if re.match(r"- \d{4}-\d{2}-\d{2}T", l)]
        self.assertTrue(rows)
        for row in rows:
            event, who, source = row.split(" · ")[1:4]
            self.assertEqual((who, source), ("dev@example.com (-)", label[event]), row)
        self.assertEqual(len(self.section(pack, "Human turns")), 3)
        self.assertIn("`human (prompt)` for what the prompt hook took from the human's own message", pack)


# ---------------------------------------------------------------- 11. the owner team; each team's own Next items
class OwnerTeam(Live):
    flags = ["--multi-team", "--team", "catalog"]

    def test_new_names_the_owner_team_and_the_other_team_is_told_who_releases(self):
        self.cfg(checks=["true"])
        p = self.ok("new", "refundable-flag")
        i = re.search(r"aidlc-docs/(\S+) \(", p.stdout).group(1)
        self.assertIn("Owner team: catalog (in the header of aidlc-state.md): this team reviews and releases the "
                      "intent.", p.stdout)
        head = self.state(i).split(BEGIN)[0]
        self.assertRegex(head, r"\nIntent: %s · Mode: multi-team · Created: \d{4}-\d{2}-\d{2}\nOwner team: catalog\n$"
                         % i)
        self.requirements(i, "small")
        for sid in ("reverse-engineering", "user-stories", "application-design"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.ok("stage", "start", "units")
        self.units(i, [("catalog", "catalog", "src/catalog/"), ("payments", "payments", "src/payments/")])
        self.ok("stage", "done", "units", "--note", "one unit per team")
        self.assertIn("update the Session notes before you stop", self.ok("request", "REQUIREMENTS").stdout)
        self.approve("REQUIREMENTS")
        self.skip_to_code("payments", team="payments")
        self.build_unit(i, "payments", team="payments")
        st = self.tool("status", team="payments").stdout
        self.assertIn("Next: wait for unit catalog (team catalog), which another team builds: its stage records come "
                      "with the ledger when you pull (skill aidlc-lean-multi-team); release is done by team catalog\n",
                      st)
        self.assertIn("- [-] Build and Test — verify PASS on partial code", st)
        self.assertIn("code generation not done yet: catalog\n", st)
        self.skip_to_code("catalog")
        self.build_unit(i, "catalog")
        self.assertIn("Next: review in a new chat or by a subagent that did not write the code, then %srelease`" % LEAN,
                      self.status())  # the owner team
        payments = ("Next: release is done by team catalog, the intent's owner team (`Owner team:` in aidlc-state.md), "
                    "in its clone: commit and push this team's work (skill aidlc-lean-multi-team)")
        self.assertIn(payments, self.tool("status", team="payments").stdout)
        path = self.ipath(i, "aidlc-state.md")  # people may hand the release to another team in the header
        self.put(path, self.read(path).replace("Owner team: catalog", "- **Owner team:** payments"))
        self.assertIn("Next: release is done by team payments, the intent's owner team", self.status())
        self.assertIn("Next: review in a new chat", self.tool("status", team="payments").stdout)
        self.put(path, self.read(path).replace("- **Owner team:** payments\n", ""))  # no line: who ran `new`
        self.assertIn(payments, self.tool("status", team="payments").stdout)

    def test_this_teams_next_subsection_comes_first_in_the_session_context(self):
        i = self.intent()
        path = self.ipath(i, "aidlc-state.md")
        self.put(path, "# AI-DLC State: refunds\nIntent: %s\n%s\n%s\n## Session notes\nStatus: construction\n"
                       "### Next (team payments)\n1. Ship the receipt field\n### Next (team catalog)\n"
                       "1. Build the flag against the stub\n2. Pull the payments contract\n### Next\n"
                       "1. Both teams: agree on the receipt contract\n### Open questions and blockers\n- none\n"
                 % (i, BEGIN, END))
        block = ("  From aidlc-state.md (Next, team catalog):\n    1. Build the flag against the stub\n    2. Pull the "
                 "payments contract\n  From aidlc-state.md (Next):\n    1. Both teams: agree on the receipt contract\n"
                 "  Stage progress:\n")
        out = self.hook("SessionStart", {}).stdout
        self.assertIn(block, out)
        self.assertNotIn("Ship the receipt field", out)
        turn = self.turn()
        turn["ts"], turn["sessions"] = "2026-01-01T00:00:00.000Z", {}
        self.put(".aidlc-lean/turn.json", json.dumps(turn))
        resumed = self.say("back again").stdout
        self.assertIn("Resumed after", resumed)
        self.assertIn(block, resumed)
        other = self.hook("SessionStart", {"session_id": "s2"}, team="payments").stdout
        self.assertIn("  From aidlc-state.md (Next, team payments):\n    1. Ship the receipt field\n  From "
                      "aidlc-state.md (Next):\n", other)
        self.assertNotIn("Build the flag against the stub", other)
        st = self.status()  # the CLI status shows them too, after the progress list
        self.assertIn("    - [ ] Release\n  From aidlc-state.md (Next, team catalog):\n", st)


# ---------------------------------------------------------------- 12. `init --team` in a configured clone
class InitTeam(Live):
    def test_init_team_in_a_configured_clone_only_confirms_the_team(self):
        self.cfg(checks=["true"], protected_paths=["tests/acceptance/**"], multi_team=True)
        cid = self.read(".aidlc-lean/clone-id").strip()
        p = self.ok("init", "--team", "payments")
        self.assertEqual(p.stdout, "This clone (%s) is now team payments.\n" % cid)
        p = self.ok("init", "--team", "catalog")
        self.assertEqual(p.stdout, "This clone (%s) is now team catalog (was payments).\n" % cid)
        self.assertEqual(json.loads(self.read(".aidlc-lean/local.json")), {"team": "catalog"})
        self.assertEqual(self.events("INIT")[-1]["data"]["team"], "catalog")
        self.cfg(protected_paths=[])  # advice only for what is not set
        p = self.ok("init", "--team", "catalog")
        self.assertEqual(p.stdout, "This clone (%s) is now team catalog. Edit aidlc-docs/lean.json: set "
                                   "`protected_paths`.\n" % cid)
        p = self.ok("init")
        self.assertEqual(p.stdout, "AI-DLC Lean ready (clone %s). Edit aidlc-docs/lean.json: set `protected_paths`.\n"
                         % cid)
        self.cfg(protected_paths=["tests/acceptance/**"])
        self.assertEqual(self.ok("init").stdout, "AI-DLC Lean ready (clone %s).\n" % cid)


# ---------------------------------------------------------------- 13. what a per-intent audit pack holds
class AuditWindow(Live):
    def test_a_pack_holds_its_intents_events_cr_events_and_the_sessions_of_its_window(self):
        self.cfg(checks=["true"])
        self.hook("SessionStart", {"session_id": "before"})  # before the intent
        self.ok("verify")  # a verify with no intent (the seed)
        i = self.ready()
        self.hook("SessionStart", {"session_id": "during"})
        self.dispatch("review the diff", session="during")
        self.hook("SessionStart", {"session_id": "during"})
        self.hook("UserPromptSubmit", {"session_id": "during", "prompt": "review the diff"})
        self.skip_to_code()
        self.build_unit(i)
        self.commit_all()
        self.ok("release")
        out, _ = self.approve("RELEASE")
        self.assertIn("Recorded: RELEASE approved", out.stdout)
        j = self.intent("other")  # another intent's events stay in its own pack
        self.ok("stage", "skip", "user-stories", "--reason", "only in the other intent")
        self.hook("SessionStart", {"session_id": "after"})  # after the RELEASE approval of the first intent
        self.dispatch("a later task", session="after")
        self.hook("SessionStart", {"session_id": "after"})
        self.ok("use", i)
        self.ok("audit", "pack", i)
        pack = self.read(self.ipath(i, "audit.md"))
        sessions = self.section(pack, "Sessions")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(self.events("SESSION_START")[1]["data"]["session"], "during")
        self.assertIn(self.events("SESSION_START")[1]["ts"], sessions[0])
        sub = self.section(pack, "Subagents and host prompts (not the human)")
        self.assertEqual([r.split(" · ")[1] for r in sub], ["SUBAGENT_START", "SUBAGENT_PROMPT"])
        self.assertIn("hook (subagent prompt) · 15 chars, sha256 %s · subagent semantic_reviewer (matched by sha256)"
                      % sha("review the diff")[:12], sub[1])
        verifies = self.section(pack, "Verification runs")
        self.assertEqual(len(verifies), 1)  # the seed verify had no intent
        self.assertNotIn("only in the other intent", pack)
        self.assertIn("## Intent switches (`use`) (1)", pack)
        self.assertIn("from %s to %s" % (j, i), pack)
        self.ok("audit", "pack", j)
        other = self.read(self.ipath(j, "audit.md"))
        self.assertIn("User Stories skipped — only in the other intent", other)
        self.assertEqual(len(self.section(other, "Sessions")), 1)  # "after": in its window (not released yet)
        self.assertEqual([r.split(" · ")[1] for r in self.section(other, "Subagents and host prompts (not the human)")],
                         ["SUBAGENT_START"])

    def test_events_tagged_with_a_released_intent_after_its_release_stay_out_of_its_pack(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.skip_to_code()
        self.build_unit(i)
        self.commit_all()
        self.ok("release")
        out, _ = self.approve("RELEASE")
        self.assertIn("Recorded: RELEASE approved", out.stdout)
        self.ok("audit", "pack", i)
        before = self.read(self.ipath(i, "audit.md"))
        self.hook("UserPromptSubmit", {"prompt": "thanks, all done"})  # still tagged with the released intent
        self.assertEqual(self.events("HUMAN_TURN")[-1].get("intent"), i)
        self.ok("audit", "pack", i)
        after = self.read(self.ipath(i, "audit.md"))
        self.assertEqual(len(self.section(after, "Human turns")), len(self.section(before, "Human turns")))
        self.assertIn("Release", after)  # the Release record written with the RELEASE approval is kept


# ---------------------------------------------------------------- 15. `request` and the Session notes template
class SessionNotesReminder(Live):
    def test_request_reminds_while_the_session_notes_are_still_the_template(self):
        i = self.intent()
        self.requirements(i)
        reminder = ("Reminder: the Session notes in aidlc-docs/%s/aidlc-state.md are still the template: update the "
                    "Session notes before you stop (Status, Next)." % i)
        p = self.ok("request", "REQUIREMENTS")
        self.assertIn(reminder, p.stdout)
        self.ok("stage", "skip", "user-stories", "--reason", "single persona")  # the generated region changes
        self.assertIn(reminder, self.ok("request", "REQUIREMENTS").stdout)
        path = self.ipath(i, "aidlc-state.md")
        self.put(path, self.read(path).replace("Status: Inception: starting", "Status: waiting for approve REQUIREMENTS"))
        self.assertNotIn("Reminder", self.ok("request", "REQUIREMENTS").stdout)


if __name__ == "__main__":
    unittest.main()
