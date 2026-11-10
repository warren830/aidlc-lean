"""Regression tests for the logic findings of the v0.3 QA session (2026-11-09), one class per finding.

L1 the RELEASE approval line is refused when `lean release` would not pass now (stale or rejected IDEATION, stale
   requirements), as `request RELEASE` is (§8.1, §9.2); Stage progress does not offer that line meanwhile
L2 a unit named `ci-pipeline` (fine in v0.2) stays a unit in v0.3: its rows, `--unit ci-pipeline` and, in
   regulated mode, its PLAN gate (also after upgrading a v0.2 install)
L3 the stages Ideation needs stay required once Ideation is re-opened: an earlier skip no longer counts, and IDEATION
   is requested and approved only with Intent Capture, Scope Definition and Approval Handoff done
L4 `stage skip ideation` leaves a done Approval Handoff alone (decided from the records, not the display mark)
L5 after the IDEATION approval, Next no longer points to the optional Ideation stages (a new page voids IDEATION)
L6 a REQUIREMENTS request the hook would refuse (Ideation re-opened) is not shown as `[A] ... approve ...`
L7 the Session-notes reminder (§8.24) also fires for an intent made with `new --ideation`
L8 release.md: a newer IDEATION approval supersedes an older one as a whole
D9 `new --ideation <slug>`: the flag may come before the slug
D10 doctor speaks of the current version, not "0.2 reads only ..."
D11 a stale IDEATION with unrecorded optional stages: Next says to request IDEATION again
R2 round 2 of the QA review: R2-F03 a pending IDEATION request whose line the hook refuses (a required stage
    started again) is not offered; R2-F04 Next after re-opening the brief of a rejected or stale IDEATION asks for
    its `stage done` first; R2-F05 a started optional Ideation stage stays in Next after the request; R2-F06 the
    committed Release row is the same in every clone; R2-F07 approvals recorded after `lean release` void that
    release.md (the old RELEASE request does not come back)
R4 round 4: contracts_dir as configured (`..` allowed) plus its resolved target, its configured name reserved and
    matched by commands (N1, N2, N6); the Approvals table parsed (N3); the page counts a fingerprint that is the
    working tree's or the commit's (N5); the `lean release` run chosen by content (N7)
R3 round 3: R3-F07 release.md is current while its Approvals table lists every approval `lean release` would list
    (this intent's and every CR approval, matched by sha, approver and time, not by clocks or intent tags); R3-F06 the
    committed rows compare with the committed code, not with this clone's untracked or uncommitted files; R3-L10
    contracts_dir is normalised (./, //, slashes, symlinks, letter case) and doctor fails on a value it rewrote
L10 contracts are code in every mode (they already were for the fingerprint and the commit gate): after the
    ownership/CR check, a contract write goes through the code-write gates (IDEATION when used, requirements, design,
    regulated: an intent and the unit's plan)

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
from test_aidlc_lean import REPO, TOOL  # noqa: E402
from test_v03_phases import IDEATION, LEAN, REQUIRED, V03  # noqa: E402

V02_COMMIT = "37ecb45"  # AI-DLC Lean 0.2.0, the release v0.3 upgrades from
UNITS_TABLE = ("# Units of Work\n\n| Unit | Owner team | Paths | Depends on | Status |\n|---|---|---|---|---|\n"
               "| api | shop | services/api/ | - | in progress |\n"
               "| ci-pipeline | shop | ci/ | - | in progress |\n")


class Fix(V03):
    def plan_and_code(self, unit="app"):
        """A one-step plan, ticked, its code on disk, `stage done code-generation`."""
        i = self.intent_now()
        self.ok("stage", "start", "code-generation")
        self.put(self.ipath(i, "construction/plans/%s-code-generation-plan.md" % unit),
                 "# Code Generation Plan\n\n- [x] 1. walking skeleton\n")
        self.put("src/app.py", "x = 1\n")
        self.ok("stage", "done", "code-generation", "--note", "skeleton")

    def intent_now(self):
        return re.search(r"Active intent: aidlc-docs/(\S+) ", self.status()).group(1)

    def ideation_approved_intent(self):
        """A --ideation intent: required stages done, optional ones skipped, IDEATION approved."""
        i = self.new_ideation()
        self.ideation_through_handoff(i)
        self.approve_ideation()
        return i

    def to_release_request(self, intent):
        """From an approved IDEATION: requirements (small, design skipped) approved, plan and code, verify, commit,
        `lean release`, `lean request RELEASE`; returns the RELEASE hash."""
        self.ok("stage", "start", "requirements")
        self.requirements(intent, "small")
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        out, _ = self.approve("REQUIREMENTS")
        self.assertIn("Recorded: REQUIREMENTS approved", out.stdout)
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        return self.request_hash("RELEASE")

    def next_line(self):
        return [l for l in self.status().splitlines() if l.startswith("  Next: ")][0]


# ---------------------------------------------------------------- L1
class ReleaseApprovalPreconditions(Fix):
    def setUp(self):
        super().setUp()
        self.cfg(checks=["true"])

    def assert_refused(self, h, reason):
        out = self.say("approve RELEASE %s" % h)
        self.assertIn("Approval of RELEASE NOT recorded: not ready to release: %s" % reason, out.stdout)
        refused = self.events("APPROVAL_REFUSED")[-1]["data"]
        self.assertEqual((refused["kind"], refused["check"], refused["given"]), ("RELEASE", "release", h))
        self.assertIn(reason, refused["reason"])
        self.assertNotEqual(self.events("APPROVED")[-1]["data"]["kind"], "RELEASE")
        st = self.status()
        self.assertNotIn("RELEASED:", st)
        self.assertIn("- [-] Release — RELEASE requested; the approval waits: not ready to release: %s" % reason, st)
        self.assertNotIn("approve RELEASE %s" % h, st)  # the line the hook refuses is not offered

    def test_a_stale_ideation_after_the_release_request(self):
        i = self.ideation_approved_intent()
        h = self.to_release_request(i)
        self.assertIn("- [A] Release — waiting for approval: approve RELEASE %s" % h, self.status())
        scope = self.ipath(i, IDEATION[3][2])
        self.put(scope, self.read(scope) + "\n- one more backlog item\n")  # IDEATION is stale now
        self.assertIn("IDEATION is stale", self.tool("request", "RELEASE").stdout)
        self.assert_refused(h, "IDEATION is stale")
        self.approve_ideation()  # current again: the release goes through as usual
        self.ok("release")
        out, _ = self.approve("RELEASE")
        self.assertIn("Recorded: RELEASE approved", out.stdout)
        self.assertIn("RELEASED:", self.status())

    def test_a_rejected_ideation_after_the_release_request(self):
        i = self.ideation_approved_intent()
        h = self.to_release_request(i)
        self.assertIn("Recorded: IDEATION rejected", self.say("reject IDEATION: the PM withdraws the scope").stdout)
        self.assert_refused(h, "IDEATION is rejected")

    def test_stale_requirements_after_the_release_request(self):
        """Also without Ideation (the gap was there in v0.2)."""
        i = self.ready()
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        h = self.request_hash("RELEASE")
        self.requirements(i, "small", extra="\n| AC-2 | refund day 20 | 400 |\n")  # requirements.md is stale
        self.assert_refused(h, "requirements.md is stale")


# ---------------------------------------------------------------- L2
class CiPipelineUnit(Fix):
    def test_a_unit_named_ci_pipeline_is_a_unit_beside_the_ci_pipeline_stage(self):
        i = self.intent("platform")
        self.requirements(i, "large")
        self.design(i)
        self.put(self.ipath(i, "inception/application-design/unit-of-work.md"), UNITS_TABLE)
        self.ok("stage", "done", "units", "--note", "api and the CI unit")
        self.approve("INCEPTION")
        self.ok("stage", "start", "functional-design", "--unit", "ci-pipeline")
        self.put(self.ipath(i, "construction/ci-pipeline/functional-design/functional-design.md"),
                 "# Functional Design: ci-pipeline\n\n- BR-1: every merge request runs the checks\n")
        self.ok("stage", "done", "functional-design", "--unit", "ci-pipeline", "--note", "BR-1")
        self.record(i, "ci-pipeline", "# CI\n\nstages: lint, test\n")  # the CI Pipeline stage, same folder
        st = self.status()
        self.assertNotIn("ignored unit names", st)
        self.assertIn("- [x] Functional Design (ci-pipeline) — done", st)
        self.assertIn("- [ ] Code Generation (ci-pipeline)\n", st)
        self.assertIn("- [x] CI Pipeline — done", st)
        self.ok("stage", "start", "nfr-design", "--unit", "ci-pipeline")
        self.assertTrue(self.exists(self.ipath(i, "construction/ci-pipeline/nfr-design/nfr-design.md")))
        self.assertTrue(self.exists(self.ipath(i, "construction/ci-pipeline/ci-config.md")))


class CiPipelineUnitRegulated(Fix):
    flags = ["--regulated"]

    def test_the_plan_gate_covers_the_paths_of_a_unit_named_ci_pipeline(self):
        i = self.intent("platform")
        self.requirements(i, "large")
        self.design(i)
        self.put(self.ipath(i, "inception/application-design/unit-of-work.md"), UNITS_TABLE)
        self.approve("INCEPTION")
        self.ok("stage", "start", "code-generation", "--unit", "api")
        self.put(self.ipath(i, "construction/plans/api-code-generation-plan.md"), "# Plan: api\n\n- [ ] 1. skeleton\n")
        self.approve("PLAN", "--unit", "api")
        self.assertEqual(self.write("services/api/app.py").returncode, 0)
        r = self.write("ci/build.sh")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (plan): the code-generation plan of unit ci-pipeline", r.stderr)


def v02_commit_available():
    return subprocess.run(["git", "-C", REPO, "cat-file", "-e", V02_COMMIT + "^{commit}"],
                          capture_output=True).returncode == 0


@unittest.skipUnless(v02_commit_available(), "needs the v0.2.0 commit %s in this checkout" % V02_COMMIT)
class CiPipelineUnitAfterUpgrade(Fix):
    """A project installed with the v0.2.0 installer (from git), then upgraded with this checkout's install.sh."""

    @classmethod
    def setUpClass(cls):
        cls.v02 = tempfile.mkdtemp(prefix="lean-v02kit-")
        arch = subprocess.run(["git", "-C", REPO, "archive", V02_COMMIT], capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", cls.v02], input=arch.stdout, check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.v02, True)

    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix="lean-up-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "dev@example.com"],
                    ["git", "config", "user.name", "Dev"]):
            self.sh(cmd)
        self.install(self.v02, "0.2.0")

    def install(self, kit, version):
        p = subprocess.run(["bash", os.path.join(kit, "install.sh"), self.dir], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.ok("--version").stdout.strip(), version)

    def test_a_v02_unit_named_ci_pipeline_survives_the_upgrade(self):
        self.cfg(regulated=True)
        i = self.intent("platform")
        self.requirements(i, "large")
        self.design(i)
        self.put(self.ipath(i, "inception/application-design/unit-of-work.md"), UNITS_TABLE)
        self.approve("INCEPTION")
        self.ok("stage", "start", "functional-design", "--unit", "ci-pipeline")
        self.put(self.ipath(i, "construction/ci-pipeline/functional-design/functional-design.md"),
                 "# Functional Design: ci-pipeline\n\n- BR-1: every merge request runs the checks\n")
        self.ok("stage", "done", "functional-design", "--unit", "ci-pipeline", "--note", "BR-1")
        self.ok("stage", "start", "code-generation", "--unit", "api")
        self.put(self.ipath(i, "construction/plans/api-code-generation-plan.md"), "# Plan: api\n\n- [ ] 1. skeleton\n")
        self.approve("PLAN", "--unit", "api")
        self.assertIn("blocked (plan): the code-generation plan of unit ci-pipeline", self.write("ci/build.sh").stderr)
        self.commit_all("v0.2 work")
        self.install(REPO, "0.3.1")  # the kit in this checkout
        st = self.status()
        self.assertNotIn("ignored unit names", st)
        self.assertIn("- [x] Functional Design (ci-pipeline) — done", st)
        self.ok("stage", "start", "nfr-design", "--unit", "ci-pipeline")
        r = self.write("ci/build.sh")  # still needs the ci-pipeline unit's own plan
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (plan): the code-generation plan of unit ci-pipeline", r.stderr)


# ---------------------------------------------------------------- L3
class RequiredIdeationStages(Fix):
    def test_a_skip_from_before_ideation_was_used_no_longer_counts(self):
        i = self.intent()  # Ideation recorded as skipped by `new`
        self.ok("stage", "skip", "intent-capture", "--reason", "no PM on this one")
        self.ok("stage", "skip", "scope-definition", "--reason", "no PM on this one")
        p = self.ok("stage", "start", "approval-handoff")  # re-opens Ideation
        self.assertIn("Ideation is in use again: Intent Capture, Scope Definition were skipped before and are required "
                      "now (those skips no longer count).", p.stdout)
        self.put(self.ipath(i, IDEATION[6][2]), "# Initiative brief\n\nbuild refunds\n")
        for sid in ("intent-capture", "scope-definition"):  # written directly (aidlc-docs/ pages are free paths)
            self.put(self.ipath(i, dict((s, d) for s, _, d in IDEATION)[sid]), "# %s\n\nwritten directly\n" % sid)
        self.ok("stage", "done", "approval-handoff", "--note", "brief")
        lines = self.progress(i)
        self.assertEqual([l for l in lines if l.startswith("- [S] Intent Capture") or
                          l.startswith("- [S] Scope Definition")], [])
        self.assertIn("- [-] Intent Capture — required now that Ideation is in use (its skip from before no longer "
                      "counts)", lines)
        self.assertIn("- [-] Approval Handoff — done · %s; IDEATION also needs Intent Capture, Scope Definition done"
                      % self.events("STAGE_COMPLETED")[-1]["ts"][:10], lines)
        self.assertIn("Next: Ideation: finish Intent Capture (", self.status())
        r = self.tool("request", "IDEATION")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Cannot request IDEATION: IDEATION needs Intent Capture, Scope Definition and Approval Handoff "
                      "done while Ideation is in use (they cannot be skipped then); not done yet: Intent Capture, "
                      "Scope Definition", r.stdout)
        out = self.say("approve IDEATION %s" % self.ideation_sha(i)[:8])
        self.assertIn("Approval of IDEATION NOT recorded: IDEATION needs Intent Capture, Scope Definition and "
                      "Approval Handoff done", out.stdout)
        self.assertEqual(self.events("APPROVAL_REFUSED")[-1]["data"]["check"], "target")
        self.assertEqual([e for e in self.events("APPROVED") if e["data"]["kind"] == "IDEATION"], [])
        for sid in ("intent-capture", "scope-definition"):
            self.ok("stage", "done", sid, "--note", "%s with the PM" % sid)
        self.approve_ideation()

    def test_ideation_needs_the_three_stages_done_not_just_their_pages(self):
        i = self.new_ideation()
        for sid, _, doc in IDEATION:
            if sid in REQUIRED:
                self.put(self.ipath(i, doc), "# %s\n\nwritten\n" % sid)
        r = self.tool("request", "IDEATION")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not done yet: Intent Capture, Scope Definition, Approval Handoff", r.stdout)
        for sid in REQUIRED:
            self.ok("stage", "done", sid, "--note", "done")
        self.approve_ideation()


# ---------------------------------------------------------------- L4
class PhaseSkipKeepsDoneStages(Fix):
    def test_a_done_approval_handoff_is_not_covered_by_the_phase_skip(self):
        i = self.new_ideation()
        for sid in REQUIRED:
            self.record(i, sid)  # Approval Handoff done; IDEATION not requested yet, so the phase may be dropped
        self.assertIn("- [-] Approval Handoff — done · ", "\n".join(self.progress(i)))
        p = self.ok("stage", "skip", "ideation", "--reason", "a developer task after all")
        self.assertIn(": Market Research, Feasibility, Team Formation, Rough Mockups.", p.stdout)
        self.assertNotIn("approval-handoff", self.events("PHASE_SKIPPED")[-1]["data"]["stages"])
        lines = self.progress(i)
        self.assertEqual([l for l in lines if l.startswith("- [S] Approval Handoff")], [])
        self.assertIn("- [x] Approval Handoff — done · %s" % self.events("STAGE_COMPLETED")[-1]["ts"][:10], lines)


# ---------------------------------------------------------------- L5
class NextAfterTheIdeationApproval(Fix):
    def test_next_does_not_send_the_agent_back_to_the_optional_ideation_stages(self):
        self.cfg(checks=["true"])
        i = self.new_ideation()
        for sid in REQUIRED:
            self.record(i, sid)  # the optional stages: no record
        self.approve_ideation()
        self.ok("stage", "start", "requirements")
        self.requirements(i, "small")
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        self.approve("REQUIREMENTS")
        for sid in ("reverse-engineering", "user-stories", "units"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        nxt = self.next_line()
        for _, name, _ in IDEATION:
            self.assertNotIn(name, nxt)
        self.assertIn("review in a new chat or by a subagent that did not write the code, then %srelease`" % LEAN, nxt)
        self.assertIn("- [ ] Market Research", self.progress(i))  # still shown, just not pointed to


# ---------------------------------------------------------------- L6
class PendingRequestsTheHookRefuses(Fix):
    def test_a_requirements_request_waits_for_ideation_after_the_reopening(self):
        i = self.intent()
        self.requirements(i, "small")
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        h = self.request_hash("REQUIREMENTS")
        self.assertIn("- [A] Requirements Analysis — waiting for approval: approve REQUIREMENTS %s" % h,
                      self.progress(i))
        self.ok("stage", "start", "intent-capture")  # re-opens Ideation (no approval yet: allowed)
        lines = self.progress(i)
        self.assertEqual([l for l in lines if l.startswith("- [A] Requirements Analysis")], [])
        self.assertIn("- [-] Requirements Analysis — REQUIREMENTS requested; the approval waits: Ideation is in use "
                      "and IDEATION is missing (the requirements are approved after it)", lines)
        self.assertNotIn("approve REQUIREMENTS %s" % h, self.status())
        self.assertIn("Approval of REQUIREMENTS NOT recorded: Ideation is in use", self.say(
            "approve REQUIREMENTS %s" % h).stdout)
        self.ideation_through_handoff(i)
        self.approve_ideation()  # the old request (requirements.md unchanged) counts again
        self.assertIn("- [A] Requirements Analysis — waiting for approval: approve REQUIREMENTS %s" % h,
                      self.progress(i))
        self.assertIn("Recorded: REQUIREMENTS approved", self.say("approve REQUIREMENTS %s" % h).stdout)


# ---------------------------------------------------------------- L7
class SessionNotesReminderForIdeation(Fix):
    REMINDER = "Reminder: the Session notes in aidlc-docs/%s/aidlc-state.md are still the template"

    def test_an_ideation_intent_with_untouched_notes_gets_the_reminder(self):
        i = self.new_ideation()
        self.ideation_through_handoff(i)
        self.assertIn("Status: Ideation: starting", self.state(i).split("## Session notes", 1)[1])
        self.assertIn(self.REMINDER % i, self.ok("request", "IDEATION").stdout)
        self.put(self.ipath(i, "aidlc-state.md"), self.state(i).replace("Status: Ideation: starting",
                                                                        "Status: brief written, IDEATION requested"))
        self.assertNotIn(self.REMINDER % i, self.ok("request", "IDEATION").stdout)

    def test_a_plain_intent_still_gets_it(self):
        i = self.intent()
        self.requirements(i, "small")
        self.assertIn(self.REMINDER % i, self.ok("request", "REQUIREMENTS").stdout)


# ---------------------------------------------------------------- L8
class SupersededIdeation(Fix):
    def test_an_older_ideation_approval_is_wholly_superseded(self):
        self.cfg(checks=["true"])
        i = self.new_ideation()
        self.ideation_through_handoff(i)
        self.record(i, "market-research", "# Market\n\ntwo competitors\n")
        self.approve_ideation()
        os.remove(os.path.join(self.dir, self.ipath(i, IDEATION[1][2])))
        self.approve_ideation()  # the PM approves the three pages left
        self.to_release_request(i)
        rows = [l.split(" | ")[0] for l in self.read(self.ipath(i, "operations/release.md")).splitlines()
                if l.startswith("| IDEATION")]
        self.assertEqual(rows, ["| IDEATION (superseded)", "| IDEATION"])


# ---------------------------------------------------------------- L10
class ContractsAreCode(Fix):
    """One team: contracts_dir (aidlc-docs/contracts) holds code although it is under aidlc-docs/."""
    contract = "aidlc-docs/contracts/api.yaml"

    def test_a_contract_waits_for_the_requirements_and_the_design(self):
        self.assertEqual(self.write(self.contract, "openapi: 3.1.0\n").returncode, 0)  # standard mode, no intent
        i = self.intent()
        for path in (self.contract, "aidlc-docs/contracts/notes.md"):  # a .md under contracts_dir is code too
            r = self.write(path)
            self.assertEqual(r.returncode, 2, path)
            self.assertIn("blocked (requirements)", r.stderr)
        self.requirements(i, "large")
        self.design(i)
        self.approve("REQUIREMENTS")
        r = self.write(self.contract)
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (design)", r.stderr)
        self.approve("DESIGN")
        self.assertEqual(self.write(self.contract).returncode, 0)
        self.assertEqual(self.write("aidlc-docs/contracts/notes.md", "# notes\n").returncode, 0)
        self.assertEqual(self.write(self.ipath(i, "inception/application-design/application-design.md"),
                                    "# design\n").returncode, 0)  # the intent's pages stay free

    def test_regulated_mode_needs_an_intent_for_a_contract(self):
        self.cfg(regulated=True)
        r = self.write(self.contract, "openapi: 3.1.0\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (intent)", r.stderr)


class ContractsAreCodeMultiTeam(Fix):
    flags = ["--multi-team", "--team", "shop"]
    own = "aidlc-docs/contracts/shop/api.yaml"
    theirs = "aidlc-docs/contracts/payments/api.yaml"

    def setUp(self):
        super().setUp()
        self.put("aidlc-docs/contracts/OWNERS", "aidlc-docs/contracts/shop/** shop\n"
                                                "aidlc-docs/contracts/payments/** payments\n")
        self.put(self.theirs, "openapi: 3.1.0\n")

    def blocked(self, path, gate, team=None):
        r = self.write(path, "openapi: 3.1.0\n", team=team)
        self.assertEqual(r.returncode, 2, (path, gate, r.stderr))
        self.assertIn("blocked (%s)" % gate, r.stderr)

    def test_the_teams_own_contract_waits_for_ideation_the_requirements_and_the_design(self):
        i = self.new_ideation()
        self.blocked(self.own, "ideation")
        self.ideation_through_handoff(i)
        self.approve_ideation()
        self.blocked(self.own, "requirements")
        self.ok("stage", "start", "requirements")
        self.requirements(i, "large")
        self.design(i)
        self.approve("REQUIREMENTS")
        self.blocked(self.own, "design")
        self.approve("DESIGN")
        self.assertEqual(self.write(self.own).returncode, 0)

    def test_a_contract_a_cr_unlocks_waits_for_the_requirements(self):
        i = self.intent()
        self.blocked(self.theirs, "contract")  # the ownership check comes first
        p = self.ok("cr", "new", "refund-reason", "--owner", "payments", "--paths", self.theirs)
        cr = re.search(r"Created (\S+\.md)\.", p.stdout).group(1)
        self.assertEqual(self.write(cr, "# CR-shop-1\n\n- Owner team: payments\n- Requested by team: shop\n- Paths: %s\n"
                                    % self.theirs).returncode, 0)  # a change request is a record, not code
        out, _ = self.approve("CR-shop-1", team="payments")
        self.assertIn("Recorded: CR-shop-1 approved", out.stdout)
        self.blocked(self.theirs, "requirements")  # unlocked for team shop, and still code
        self.blocked(self.theirs, "contract", team="web")
        self.requirements(i, "small")
        self.ok("stage", "skip", "application-design", "--reason", "one field")
        self.approve("REQUIREMENTS")
        self.assertEqual(self.write(self.theirs).returncode, 0)
        self.assertEqual(self.write(self.theirs, team="payments").returncode, 0)  # the owners need no CR


class ContractsAreCodeRegulated(Fix):
    flags = ["--regulated", "--multi-team", "--team", "shop"]

    def test_regulated_mode_needs_an_intent_for_the_teams_own_contract(self):
        self.put("aidlc-docs/contracts/OWNERS", "aidlc-docs/contracts/shop/** shop\n")
        r = self.write("aidlc-docs/contracts/shop/api.yaml", "openapi: 3.1.0\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (intent)", r.stderr)
        self.intent()
        r = self.write("aidlc-docs/contracts/shop/api.yaml", "openapi: 3.1.0\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (requirements)", r.stderr)


# ---------------------------------------------------------------- D9, D10
class CommandLine(Fix):
    def test_new_takes_ideation_before_the_slug(self):
        p = self.ok("new", "--ideation", "refunds", "--title", "Refunds")
        i = re.search(r"aidlc-docs/(\S+) \(", p.stdout).group(1)
        self.assertTrue(i.endswith("-refunds"), i)
        self.assertEqual(self.events("INTENT_CREATED")[-1]["data"], {"title": "Refunds", "ideation": True})
        self.assertTrue(self.exists(self.ipath(i, IDEATION[0][2])))

    def test_doctor_names_the_current_version(self):
        version = self.ok("--version").stdout.strip()
        self.put("aidlc/lean.json", "{}\n")
        self.cfg(contracts_dir="aidlc/contracts")
        out = self.tool("doctor").stdout
        self.assertIn("found aidlc/ from AI-DLC Lean 0.1: AI-DLC Lean %s reads only aidlc-docs/" % version, out)
        self.assertIn("is the 0.1 path aidlc/contracts; AI-DLC Lean %s uses aidlc-docs/contracts" % version, out)
        self.assertNotIn("0.2 reads", out)
        self.assertNotIn("0.2 uses", out)


# ---------------------------------------------------------------- D11
class NextForAStaleOrRejectedIdeation(Fix):
    flags = ["--regulated"]

    def setUp(self):
        super().setUp()
        self.i = self.new_ideation()
        for sid in REQUIRED:
            self.record(self.i, sid)  # the optional stages: no record
        self.approve_ideation()

    def test_a_stale_ideation_is_requested_again(self):
        scope = self.ipath(self.i, IDEATION[3][2])
        self.put(scope, self.read(scope) + "\n- one more item\n")
        nxt = self.next_line()
        self.assertNotIn("market-research", nxt)
        self.assertIn("Next: an Ideation page changed since IDEATION was approved: %srequest IDEATION` again" % LEAN,
                      nxt)

    def test_a_rejected_ideation_is_revised_and_requested_again(self):
        self.say("reject IDEATION: narrow the scope")
        nxt = self.next_line()
        self.assertNotIn("market-research", nxt)
        self.assertIn("Next: IDEATION was rejected: revise the Ideation pages as the human asked", nxt)

    def test_an_optional_page_started_after_the_approval_is_still_finished_first(self):
        self.page(self.i, "market-research", "# market\n")
        self.assertIn("Next: Ideation: finish Market Research (", self.next_line())



# ---------------------------------------------------------------- round 2 of the QA review
class R2PendingIdeationRefused(Fix):
    def test_a_required_stage_started_after_the_request_holds_the_line_back(self):
        i = self.new_ideation()
        self.ideation_through_handoff(i)
        h = self.request_hash("IDEATION")
        self.assertIn("- [A] Approval Handoff — waiting for approval: approve IDEATION %s" % h, self.progress(i))
        self.ok("stage", "start", "scope-definition")  # page kept: the request is not voided, but not done any more
        lines = self.progress(i)
        self.assertEqual([l for l in lines if "approve IDEATION" in l], [])
        self.assertIn("- [-] Approval Handoff — done · %s; IDEATION also needs Scope Definition done"
                      % self.events("STAGE_COMPLETED")[-1]["ts"][:10], lines)
        nxt = self.next_line()
        self.assertNotIn("approve IDEATION", nxt)
        self.assertIn("Next: Ideation: finish Scope Definition (", nxt)
        self.assertIn("Approval of IDEATION NOT recorded", self.say("approve IDEATION %s" % h).stdout)
        self.ok("stage", "done", "scope-definition", "--note", "unchanged")
        self.assertIn("Next: wait for the human to type `approve IDEATION %s`" % h, self.status())  # back again
        self.assertIn("Recorded: IDEATION approved (sha %s)" % h, self.say("approve IDEATION %s" % h).stdout)


class R2NextAfterReopeningTheBrief(Fix):
    def reopen(self, i):
        self.ok("stage", "start", "approval-handoff")
        self.put(self.ipath(i, IDEATION[6][2]), "# Initiative brief\n\nnarrower scope, as the PM asked\n")
        nxt = self.next_line()
        self.assertNotIn("request IDEATION", nxt)
        self.assertIn("record the initiative brief done again (%sstage done approval-handoff --note ...`" % LEAN, nxt)
        self.assertEqual(self.tool("request", "IDEATION").returncode, 1)
        self.ok("stage", "done", "approval-handoff", "--note", "narrower")
        self.assertIn("%srequest IDEATION`" % LEAN, self.next_line())
        self.approve_ideation()

    def test_rejected(self):
        i = self.new_ideation()
        self.ideation_through_handoff(i)
        self.request_hash("IDEATION")
        self.say("reject IDEATION: narrow the scope")
        self.reopen(i)

    def test_stale(self):
        i = self.new_ideation()
        self.ideation_through_handoff(i)
        self.approve_ideation()
        self.reopen(i)


class R2StartedOptionalStage(Fix):
    def test_a_started_optional_stage_is_still_to_be_finished_after_the_approval(self):
        self.cfg(checks=["true"])
        i = self.new_ideation()
        self.record(i, "intent-capture")
        self.page(i, "market-research", "# Market research\n\ntwo competitors so far\n")  # started, not done
        self.record(i, "scope-definition")
        self.record(i, "approval-handoff")
        self.approve_ideation()  # covers the market-research page
        self.ok("stage", "start", "requirements")
        self.requirements(i, "small")
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        self.approve("REQUIREMENTS")
        for sid in ("reverse-engineering", "user-stories", "units"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        nxt = self.next_line()
        self.assertIn("Market Research", nxt)
        self.assertNotIn("Feasibility", nxt)  # never started: still left out
        self.ok("stage", "done", "market-research", "--note", "two competitors")  # the page is unchanged
        self.assertIn("- [x] Approval Handoff — approved via IDEATION", self.status())
        self.assertNotIn("Market Research", self.next_line())


class R2ReleaseRowAcrossClones(Fix):
    def test_every_clone_renders_the_same_release_row(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        h = self.request_hash("RELEASE")
        self.commit_all("release requested")
        other = os.path.realpath(tempfile.mkdtemp(prefix="lean-clone-"))
        self.addCleanup(shutil.rmtree, other, True)
        self.assertEqual(subprocess.run(["git", "clone", "-q", self.dir, other], capture_output=True).returncode, 0)
        for cmd in (["git", "config", "user.email", "lead@example.com"], ["git", "config", "user.name", "Lead"]):
            subprocess.run(cmd, cwd=other, capture_output=True)

        def row(root):
            p = subprocess.run(TOOL + ["status"], cwd=root, capture_output=True, text=True, env=self.env())
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            with open(os.path.join(root, self.ipath(i, "aidlc-state.md")), encoding="utf-8") as f:
                return [l for l in f.read().splitlines() if l.startswith("- [") and " Release" in l], p.stdout
        (here, _), (there, status) = row(self.dir), row(other)
        self.assertEqual(here, ["- [A] Release — waiting for approval: approve RELEASE %s" % h])
        self.assertEqual(there, here)
        self.assertIn("Next: run %sverify` and get it green on the current code" % LEAN, status)  # clone-local
        out = subprocess.run(TOOL + ["hook", "UserPromptSubmit"], cwd=other, capture_output=True, text=True,
                             env=self.env(), input='{"session_id": "s", "hook_event_name": "UserPromptSubmit", '
                                                   '"cwd": "%s", "prompt": "approve RELEASE %s"}' % (other, h)).stdout
        self.assertIn("not ready to release: no passing verify on the current code", out)  # §8.1, in that clone


class R2DecisionsAfterTheRelease(Fix):
    def setUp(self):
        super().setUp()
        self.cfg(checks=["true"])

    def check(self, i, old, kind, new):
        """After the fix the old RELEASE request does not come back; a new `lean release` lists the new approval."""
        lines = [l for l in self.progress(i) if " Release" in l]
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^- \[-\] Release — release.md \(written \d{4}-\d{2}-\d{2}\) does not list %s "
                                   r"approved: run `release` again$" % kind)
        nxt = self.next_line()
        self.assertNotIn("approve RELEASE %s" % old, nxt)
        self.assertIn("then %srelease` again (its Approvals table lacks newer approvals)" % LEAN, nxt)
        r = self.tool("request", "RELEASE")
        self.assertEqual(r.returncode, 1)
        self.assertIn("operations/release.md does not list %s approved (run %srelease` again)" % (kind, LEAN),
                      r.stdout)
        out = self.say("approve RELEASE %s" % old).stdout
        self.assertIn("Approval of RELEASE NOT recorded: operations/release.md does not list %s approved: its "
                      "Approvals table is out of date." % kind, out)
        self.assertEqual(self.events("APPROVAL_REFUSED")[-1]["data"]["check"], "release")
        self.ok("release")
        rows = [l for l in self.read(self.ipath(i, "operations/release.md")).splitlines()
                if l.startswith("| " + kind)]
        self.assertTrue(rows[-1].startswith("| %s | " % kind) and "| %s" % new in rows[-1], rows)
        out, _ = self.approve("RELEASE")
        self.assertIn("Recorded: RELEASE approved", out.stdout)

    def test_requirements_approved_again(self):
        i = self.ready()
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        old = self.request_hash("RELEASE")
        self.requirements(i, "small", extra="\n| AC-2 | refund day 20 | 400 |\n")
        self.assertIn("not ready to release: requirements.md is stale", self.say("approve RELEASE %s" % old).stdout)
        _, new = self.approve("REQUIREMENTS")
        self.check(i, old, "REQUIREMENTS", new)

    def test_ideation_approved_again(self):
        i = self.ideation_approved_intent()
        old = self.to_release_request(i)
        scope = self.ipath(i, IDEATION[3][2])
        self.put(scope, self.read(scope) + "\n- out of scope now: partial refunds\n")
        self.assertIn("not ready to release: IDEATION is stale", self.say("approve RELEASE %s" % old).stdout)
        new = self.approve_ideation()
        self.check(i, old, "IDEATION", new)

    def test_a_rejected_release_may_be_requested_again_without_a_new_release(self):
        i = self.ready()
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        self.request_hash("RELEASE")
        self.say("reject RELEASE: fill in the Open items")
        rel = self.ipath(i, "operations/release.md")
        self.put(rel, self.read(rel) + "- none known\n")
        out, _ = self.approve("RELEASE")  # a RELEASE decision does not void release.md
        self.assertIn("Recorded: RELEASE approved", out.stdout)



# ---------------------------------------------------------------- round 3 of the QA review
PAYMENTS = "aidlc-docs/contracts/payments/api.yaml"
SKEWED = """import importlib.util, os, sys
from datetime import datetime, timedelta, timezone
hours = float(sys.argv[1])
spec = importlib.util.spec_from_file_location("aidlc_lean", os.path.join(os.getcwd(), ".kiro", "aidlc-lean",
                                              "aidlc_lean.py"))
mod = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(mod)
mod.now = lambda: (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(
    timespec="milliseconds").replace("+00:00", "Z")
sys.exit(mod.main(sys.argv[2:]))
"""


class R3ReleaseListsEveryApproval(Fix):
    """release.md is current while its Approvals table lists every approval `lean release` would list: this
    intent's and every CR approval, whatever intent the approving clone had active and whatever its clock said."""
    flags = ["--multi-team", "--team", "shop"]

    def setUp(self):
        super().setUp()
        self.cfg(checks=["true"])
        self.put("aidlc-docs/contracts/OWNERS", "aidlc-docs/contracts/payments/** payments\n")
        self.put(PAYMENTS, "openapi: 3.1.0\n")
        self.commit_all("owners")
        self.x = self.ready("feature-x")
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        self.h = self.request_hash("RELEASE")

    def void_until_released_again(self):
        r = self.tool("request", "RELEASE")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("operations/release.md does not list CR-shop-1 approved (run %srelease` again)" % LEAN, r.stdout)
        out = self.say("approve RELEASE %s" % self.h).stdout
        self.assertIn("Approval of RELEASE NOT recorded: operations/release.md does not list CR-shop-1 approved", out)
        self.assertNotIn("approve RELEASE %s" % self.h, self.status())
        self.ok("release")
        self.assertIn("| CR-shop-1 |", self.read(self.ipath(self.x, "operations/release.md")))
        out, _ = self.approve("RELEASE")
        self.assertIn("Recorded: RELEASE approved", out.stdout)

    def test_a_cr_approved_while_another_intent_is_active(self):
        self.intent("other-work")  # this clone works on another intent now: the CR approval is tagged with it
        self.ok("cr", "new", "refund-reason", "--owner", "payments", "--paths", PAYMENTS)
        out, _ = self.approve("CR-shop-1", team="payments")
        self.assertIn("Recorded: CR-shop-1 approved", out.stdout)
        self.assertNotEqual(self.events("APPROVED")[-1]["intent"], self.x)
        self.ok("use", self.x)
        self.void_until_released_again()

    def skewed_cr_approval(self, hours):
        """Team payments approves CR-shop-1 in a clone of its own (its own ledger file) whose clock is off by hours."""
        self.ok("cr", "new", "refund-reason", "--owner", "payments", "--paths", PAYMENTS)
        script = os.path.join(self.dir, ".aidlc-lean", "skewed.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(SKEWED)
        cid = os.path.join(self.dir, ".aidlc-lean", "clone-id")
        with open(cid, encoding="utf-8") as f:
            mine = f.read()
        with open(cid, "w", encoding="utf-8") as f:
            f.write("payments-clone\n")
        env = dict(self.env(), AIDLC_LEAN_TEAM="payments")
        try:
            out = subprocess.run([sys.executable, script, str(hours), "request", "CR-shop-1"], cwd=self.dir,
                                 capture_output=True, text=True, env=env).stdout
            h = re.search(r"approve CR-shop-1 ([0-9a-f]{8})", out).group(1)
            payload = '{"session_id": "pay", "hook_event_name": "UserPromptSubmit", "cwd": "%s", ' \
                      '"prompt": "approve CR-shop-1 %s"}' % (self.dir, h)
            out = subprocess.run([sys.executable, script, str(hours), "hook", "UserPromptSubmit"], cwd=self.dir,
                                 capture_output=True, text=True, env=env, input=payload).stdout
            self.assertIn("Recorded: CR-shop-1 approved", out)
        finally:
            with open(cid, "w", encoding="utf-8") as f:
                f.write(mine)
        self.assertTrue(self.exists("aidlc-docs/audit/payments-clone.jsonl"))

    def test_a_cr_approved_on_a_clock_24_hours_ahead(self):
        self.skewed_cr_approval(24)
        self.void_until_released_again()  # the fresh release.md lists it: requestable at once, not in 24 h

    def test_a_cr_approved_on_a_clock_24_hours_behind(self):
        self.skewed_cr_approval(-24)  # sorts before the release write, but release.md does not list it
        self.void_until_released_again()


class R3CommittedPageIgnoresTheWorkingTree(Fix):
    def test_an_untracked_file_in_a_teammates_clone_changes_no_row(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        h = self.request_hash("RELEASE")
        self.commit_all("release requested")
        other = os.path.realpath(tempfile.mkdtemp(prefix="lean-clone-"))
        self.addCleanup(shutil.rmtree, other, True)
        self.assertEqual(subprocess.run(["git", "clone", "-q", self.dir, other], capture_output=True).returncode, 0)
        with open(os.path.join(other, ".DS_Store"), "wb") as f:  # Finder's file; this repo does not ignore it
            f.write(b"\x00\x00\x00\x01Bud1")
        (here, _), (there, status) = page_rows(self, self.dir, i), page_rows(self, other, i)
        self.assertEqual(there, here)
        self.assertIn("- [x] Build and Test — verify PASS · ", "\n".join(there))
        self.assertIn("- [A] Release — waiting for approval: approve RELEASE %s" % h, there)
        self.assertIn("Working tree: 1 uncommitted product change (.DS_Store): verify, the commit gate and the "
                      "RELEASE approval check the working tree", status)

    def test_verify_then_commit_commits_a_page_that_says_verified(self):
        """R4-N5: `lean verify` writes the page before the commit exists; the commit of the verified code must not
        carry a page that says its code was not verified."""
        self.cfg(checks=["true"])
        self.commit_all("start")
        i = self.ready()
        self.plan_and_code()
        self.ok("verify")
        self.assertIn("Working tree: ", self.status())  # src/app.py is not committed yet
        self.commit_all("refunds: first slice")
        page = subprocess.run(["git", "show", "HEAD:" + self.ipath(i, "aidlc-state.md")], cwd=self.dir,
                              capture_output=True, text=True).stdout
        rows = [l for l in page.splitlines() if l.startswith("- [") and " Build and Test — " in l]
        self.assertEqual(len(rows), 1, page)
        self.assertTrue(rows[0].startswith("- [x] Build and Test — verify PASS · "), rows[0])
        self.put("src/app.py", "x = 2\n")  # a change no verify has seen: the committed code is still the verified one
        st = self.status()
        self.assertIn("- [x] Build and Test — verify PASS · ", st)
        self.assertIn("Last verify: PASS at ", st)
        self.assertIn("(code changed since)", st)  # this clone's status says so, outside the committed page
        self.commit_all("unverified change")  # now neither the working tree nor the commit is the verified code
        self.assertIn("- [-] Build and Test — code changed since the last verify PASS", self.status())


def page_rows(test, root, intent):
    """`lean status` in root: (the Stage progress rows of the generated region it writes, its output)."""
    p = subprocess.run(TOOL + ["status"], cwd=root, capture_output=True, text=True, env=test.env())
    test.assertEqual(p.returncode, 0, p.stdout + p.stderr)
    with open(os.path.join(root, test.ipath(intent, "aidlc-state.md")), encoding="utf-8") as f:
        text = f.read()
    region = text.split("<!-- lean:begin progress -->")[1].split("<!-- lean:end progress -->")[0]
    return [l for l in region.splitlines() if l.startswith("- [")], p.stdout


class R3ContractsDirNormalised(Fix):
    flags = ["--multi-team", "--team", "shop"]
    OWNERS = "aidlc-docs/contracts/OWNERS"

    def setUp(self):
        super().setUp()
        self.put(self.OWNERS, "aidlc-docs/contracts/shop/** shop\naidlc-docs/contracts/payments/** payments\n")
        self.put(PAYMENTS, "openapi: 3.1.0\n")

    def blocked(self, path, gate):
        r = self.write(path, "openapi: 3.1.0\n")
        self.assertEqual(r.returncode, 2, (path, gate, r.stderr))
        self.assertIn("blocked (%s)" % gate, r.stderr)

    def shell_blocked(self, command):
        r = self.bash(command)
        self.assertEqual(r.returncode, 2, command)
        self.assertIn("blocked (records)", r.stderr)

    def gates_hold(self):
        self.blocked(PAYMENTS, "contract")
        self.blocked("aidlc-docs/contracts/shop/api.yaml", "requirements")
        self.blocked(self.OWNERS, "records")
        self.shell_blocked("echo 'aidlc-docs/contracts/** shop' >> %s" % self.OWNERS)
        self.shell_blocked("sed -i '' 's/ payments$/ shop/' %s" % self.OWNERS)

    def doctor(self):
        return self.tool("doctor").stdout

    def test_spellings_of_the_same_folder(self):
        self.intent()  # requirements not approved
        for value in ("./aidlc-docs/contracts", "aidlc-docs//contracts/", "aidlc-docs/contracts/.",
                      "aidlc-docs/contracts/"):
            self.cfg(contracts_dir=value)
            self.assertNotIn("contracts_dir", self.doctor(), value)  # nothing ambiguous: read as written
            self.gates_hold()
        self.cfg(contracts_dir="/aidlc-docs/contracts")  # an absolute path to no folder: ambiguous
        self.assertIn("contracts_dir '/aidlc-docs/contracts' in aidlc-docs/lean.json is an absolute path to no "
                      "folder: AI-DLC Lean reads it as 'aidlc-docs/contracts' in the project folder", self.doctor())
        self.gates_hold()
        self.cfg(checks=["true"], contracts_dir="./aidlc-docs/contracts")  # code for the commit gate too
        self.ok("verify")
        self.commit_all("verified")
        self.put(PAYMENTS, "openapi: 3.1.0\ninfo: {title: changed}\n")
        r = self.bash("git commit -qam 'contract change'")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (verify)", r.stderr)

    def test_empty_and_the_project_folder_are_named_for_what_they_are(self):
        self.intent()
        self.cfg(contracts_dir="")
        self.assertIn("contracts_dir in aidlc-docs/lean.json is empty: AI-DLC Lean uses aidlc-docs/contracts",
                      self.doctor())
        self.gates_hold()
        self.cfg(contracts_dir=".")
        self.assertIn("contracts_dir '.' in aidlc-docs/lean.json is the project folder itself: AI-DLC Lean uses "
                      "aidlc-docs/contracts", self.doctor())
        self.gates_hold()

    def test_a_symlinked_contracts_folder(self):
        """R4-N6: commands name OWNERS as lean.json does, not by the symlink's target."""
        os.rename(os.path.join(self.dir, "aidlc-docs", "contracts"), os.path.join(self.dir, "shared-contracts"))
        os.symlink(os.path.join("..", "shared-contracts"), os.path.join(self.dir, "aidlc-docs", "contracts"))
        self.assertNotIn("contracts_dir", self.doctor())  # the value is right as written
        self.intent()
        self.gates_hold()
        self.shell_blocked("echo 'x shop' >> shared-contracts/OWNERS")  # and by the target's name
        self.blocked("shared-contracts/payments/api.yaml", "contract")

    def test_the_letter_case_on_a_case_insensitive_file_system(self):
        if not os.path.exists(os.path.join(self.dir, "AIDLC-DOCS")):
            self.skipTest("the file system here is case-sensitive")
        self.intent()
        self.blocked("aidlc-docs/Contracts/payments/api.yaml", "contract")
        self.blocked("aidlc-docs/CONTRACTS/OWNERS", "records")
        self.blocked("AIDLC-DOCS/LEAN.JSON", "records")
        self.cfg(contracts_dir="aidlc-docs/Contracts")
        self.gates_hold()


class R4ContractsOutsideTheProject(Fix):
    """R4-N1: a monorepo project whose contracts live next to it (`../../shared-contracts`, valid in v0.2)."""
    flags = ["--multi-team", "--team", "shop"]

    def setUp(self):
        self.top = os.path.realpath(tempfile.mkdtemp(prefix="lean-mono-"))
        self.addCleanup(shutil.rmtree, self.top, True)
        for cmd in (["init", "-q"], ["config", "user.email", "dev@example.com"], ["config", "user.name", "Dev"]):
            subprocess.run(["git"] + cmd, cwd=self.top, capture_output=True, check=True)
        self.dir = os.path.join(self.top, "services", "shop")
        os.makedirs(self.dir)
        p = subprocess.run(["bash", os.path.join(REPO, "install.sh"), self.dir] + self.flags,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.ensure_templates()
        self.cfg(contracts_dir="../../shared-contracts")
        shared = os.path.join(self.top, "shared-contracts")
        os.makedirs(os.path.join(shared, "payments"))
        with open(os.path.join(shared, "OWNERS"), "w") as f:
            f.write("../../shared-contracts/payments/** payments\n../../shared-contracts/shop/** shop\n")
        with open(os.path.join(shared, "payments", "api.yaml"), "w") as f:
            f.write("openapi: 3.1.0\n")

    def write_top(self, path):
        return self.hook("PreToolUse", {"tool_name": "fs_write", "tool_input": {
            "path": os.path.join(self.top, path), "text": "openapi: 3.1.0\n"}})

    def test_the_shared_contracts_keep_their_gates(self):
        self.assertNotIn("contracts_dir", self.tool("doctor").stdout)
        self.intent()
        r = self.write_top("shared-contracts/shop/api.yaml")  # its own contract: code, waits for the requirements
        self.assertIn("blocked (requirements)", r.stderr)
        self.ready("feature-y")
        for path, gate in (("shared-contracts/payments/api.yaml", "contract"), ("shared-contracts/OWNERS", "records")):
            r = self.write_top(path)
            self.assertEqual(r.returncode, 2, path)
            self.assertIn("blocked (%s)" % gate, r.stderr)
        self.assertEqual(self.write_top("shared-contracts/shop/api.yaml").returncode, 0)
        r = self.bash("echo 'x shop' >> ../../shared-contracts/OWNERS")
        self.assertIn("blocked (records)", r.stderr)


class R4SymlinkedContractsDirNotAnIntent(Fix):
    def test_a_fresh_clone_still_has_its_only_intent_active(self):
        """R4-N2: a symlink aidlc-docs/api-contracts -> ../shared-contracts is the contracts folder, not an intent."""
        self.cfg(contracts_dir="aidlc-docs/api-contracts")
        self.put("shared-contracts/api.yaml", "openapi: 3.1.0\n")
        os.symlink(os.path.join("..", "shared-contracts"), os.path.join(self.dir, "aidlc-docs", "api-contracts"))
        self.assertNotIn("contracts_dir", self.tool("doctor").stdout)
        i = self.intent()
        self.commit_all("intent started")
        clone = os.path.realpath(tempfile.mkdtemp(prefix="lean-clone-"))
        self.addCleanup(shutil.rmtree, clone, True)
        self.assertEqual(subprocess.run(["git", "clone", "-q", self.dir, clone], capture_output=True).returncode, 0)
        payload = '{"session_id": "s", "hook_event_name": "PreToolUse", "cwd": "%s", "tool_name": "fs_write", ' \
                  '"tool_input": {"path": "%s/src/app.py", "text": "x = 1\\n"}}' % (clone, clone)
        r = subprocess.run(TOOL + ["hook", "PreToolUse"], cwd=clone, input=payload, capture_output=True, text=True,
                           env=self.env())
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("blocked (requirements)", r.stderr)
        st = subprocess.run(TOOL + ["status"], cwd=clone, capture_output=True, text=True, env=self.env()).stdout
        self.assertIn("Active intent: aidlc-docs/%s " % i, st)


class R4ApprovalsTableRows(Fix):
    """R4-N3: release.md lists an approval when a row of its Approvals table has that approval's cells, whitespace
    collapsed; cells anywhere else (an HTML comment, Open items) do not count."""
    flags = ["--multi-team", "--team", "shop"]

    def setUp(self):
        super().setUp()
        self.cfg(checks=["true"])
        self.put("aidlc-docs/contracts/OWNERS", "aidlc-docs/contracts/payments/** payments\n")
        self.put(PAYMENTS, "openapi: 3.1.0\n")
        self.commit_all("owners")
        self.x = self.ready("feature-x")
        self.ok("cr", "new", "refund-reason", "--owner", "payments", "--paths", PAYMENTS)
        self.approve("CR-shop-1", team="payments")
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        self.rel = self.ipath(self.x, "operations/release.md")

    def test_padded_columns_still_list_every_approval(self):
        lines = []
        for line in self.read(self.rel).splitlines():  # a formatter pads every cell
            if line.startswith("| ") and not line.startswith("|---"):
                line = "| " + " | ".join(c.strip().ljust(40) for c in line.strip().strip("|").split("|")) + " |"
            lines.append(line.replace("(copy unresolved questions", "- none known (copy unresolved questions"))
        self.put(self.rel, "\n".join(lines) + "\n")
        r = self.tool("request", "RELEASE")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Recorded: RELEASE approved", self.say("approve RELEASE %s" % re.search(
            r"approve RELEASE ([0-9a-f]{8})", r.stdout).group(1)).stdout)

    def test_cells_outside_the_table_do_not_count(self):
        self.ok("cr", "new", "tax-field", "--owner", "payments", "--paths", PAYMENTS)
        self.approve("CR-shop-2", team="payments")
        e = self.events("APPROVED")[-1]
        cells = "| %s | %s (%s) | %s |" % (e["data"]["sha256"][:12], e["actor"]["git_email"], e["actor"]["team"],
                                           e["ts"])
        text = self.read(self.rel)
        self.put(self.rel, text.replace("## Approvals\n", "## Approvals\n<!-- %s -->\n" % cells)
                 + "\n| CR-shop-2 | %s %s\n" % (PAYMENTS, cells))  # in a comment, and in a table under Open items
        r = self.tool("request", "RELEASE")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("does not list CR-shop-2 approved", r.stdout)


class R4ReleaseWriteChosenByContent(Fix):
    """R4-N7: which `lean release` run wrote release.md is read from the file, not from the clones' clocks."""

    def test_a_fresh_release_md_from_a_clone_whose_clock_is_behind(self):
        self.cfg(checks=["true"])
        x = self.ready()
        self.plan_and_code()
        self.ok("verify")
        self.commit_all()
        self.ok("release")  # the first clone (clock right)
        script = os.path.join(self.dir, ".aidlc-lean", "skewed.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(SKEWED)
        cid = os.path.join(self.dir, ".aidlc-lean", "clone-id")
        with open(cid, encoding="utf-8") as f:
            mine = f.read()
        with open(cid, "w", encoding="utf-8") as f:
            f.write("teammate-clone\n")  # a second clone of the team, its clock 24 h behind

        def lean(*args):
            return subprocess.run([sys.executable, script, "-24"] + list(args), cwd=self.dir, capture_output=True,
                                  text=True, env=self.env())
        try:
            self.put("src/app.py", "x = 2  # the fix the human asked for\n")
            self.assertEqual(lean("verify").returncode, 0)
            self.commit_all("fix")
            self.assertIn("Wrote aidlc-docs/%s/operations/release.md" % x, lean("release").stdout)
            rel = self.ipath(x, "operations/release.md")
            self.put(rel, self.read(rel).replace("(copy unresolved", "- none (copy unresolved"))  # Open items
            req = lean("request", "RELEASE")
            self.assertEqual(req.returncode, 0, req.stdout)
            self.assertIn("- [A] Release — waiting for approval: approve RELEASE", lean("status").stdout)
        finally:
            with open(cid, "w", encoding="utf-8") as f:
                f.write(mine)


if __name__ == "__main__":
    unittest.main()
