"""Tests for AI-DLC Lean v0.3: the optional Ideation and Deployment/Operations phases (docs/design-v0.2.md §9).

Covers: the 15 new stages (ids, phases, files, order, required-when-used rules), `lean new` with and without
--ideation (the whole Ideation phase recorded as skipped, re-opened by `stage start` until the requirements are
approved), the IDEATION approval (hash over the existing Ideation pages in stage order, per-file shas, stale,
rejected, approvers, regulated hashes) and what depends on it (REQUIREMENTS/INCEPTION approvals, code writes,
release), `stage skip ideation|operations` (operations without ci-pipeline), Operations and ci-pipeline after
RELEASE, the one-line display of a phase skipped by one phase skip, the order of Stage progress, Next, the Stage
log and audit.md, and the kit texts the agent reads for the new phases.

The tests write the pages they need; stand-in templates are installed when the kit ships none (test_aidlc_lean).

Run: python3 -m unittest discover -s tests -v
"""
import hashlib
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_aidlc_lean import REPO, REQ, Base  # noqa: E402

LEAN = "`python3 .kiro/aidlc-lean/aidlc_lean.py "
BEGIN = "<!-- lean:begin progress -->"
END = "<!-- lean:end progress -->"
IDEATION = (("intent-capture", "Intent Capture", "ideation/intent-capture/intent-statement.md"),
            ("market-research", "Market Research", "ideation/market-research/market-research.md"),
            ("feasibility", "Feasibility", "ideation/feasibility/feasibility-assessment.md"),
            ("scope-definition", "Scope Definition", "ideation/scope-definition/scope-document.md"),
            ("team-formation", "Team Formation", "ideation/team-formation/team-assessment.md"),
            ("rough-mockups", "Rough Mockups", "ideation/rough-mockups/wireframes.md"),
            ("approval-handoff", "Approval Handoff", "ideation/approval-handoff/initiative-brief.md"))
CI = ("ci-pipeline", "CI Pipeline", "construction/ci-pipeline/ci-config.md")
OPERATIONS = (("deployment-pipeline", "Deployment Pipeline", "operations/deployment-pipeline/deployment-strategy.md"),
              ("environment-provisioning", "Environment Provisioning",
               "operations/environment-provisioning/environment-inventory.md"),
              ("deployment-execution", "Deployment Execution", "operations/deployment-execution/deployment-log.md"),
              ("observability-setup", "Observability Setup", "operations/observability-setup/observability.md"),
              ("incident-response", "Incident Response", "operations/incident-response/runbooks.md"),
              ("performance-validation", "Performance Validation",
               "operations/performance-validation/load-test-plan.md"),
              ("feedback-optimization", "Feedback Optimization", "operations/feedback-optimization/feedback-loop.md"))
TEMPLATES = {"intent-capture": "intent-statement.md", "market-research": "market-research.md",
             "feasibility": "feasibility-assessment.md", "scope-definition": "scope-document.md",
             "team-formation": "team-assessment.md", "rough-mockups": "wireframes.md",
             "approval-handoff": "initiative-brief.md", "ci-pipeline": "ci-config.md",
             "deployment-pipeline": "deployment-strategy.md", "environment-provisioning": "environment-inventory.md",
             "deployment-execution": "deployment-log.md", "observability-setup": "observability.md",
             "performance-validation": "load-test-plan.md", "incident-response": "runbooks.md",
             "feedback-optimization": "feedback-loop.md"}
REQUIRED = ("intent-capture", "scope-definition", "approval-handoff")
NOT_REQUESTED = "not requested (lean new without --ideation)"
SKIPPED_LINE = "- [S] Ideation — skipped: " + NOT_REQUESTED


def load_core():
    import importlib.util
    path = os.path.join(REPO, "kit", ".kiro", "aidlc-lean", "aidlc_lean.py")
    spec = importlib.util.spec_from_file_location("aidlc_lean_v03", path)
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


class V03(Base):
    def status(self, team=None):
        return self.tool("status", team=team).stdout

    def state(self, intent):
        return self.read(self.ipath(intent, "aidlc-state.md"))

    def progress(self, intent):
        """The Stage progress lines of aidlc-state.md (after `status` refreshed it)."""
        self.ok("status")
        region = self.state(intent).split("## Stage progress\n")[1].split("\n\n## Stage log")[0]
        return region.splitlines()

    def log(self, intent):
        return self.state(intent).split("## Stage log")[1].split(END)[0]

    def new_ideation(self, slug="idea", *extra):
        p = self.ok("new", slug, *extra, "--ideation")
        return re.search(r"aidlc-docs/(\S+) \(", p.stdout).group(1)

    def page(self, intent, sid, text=None):
        """Start an Ideation/CI/Operations stage and write its page (the agent's part)."""
        doc = dict((s, d) for s, _, d in IDEATION + (CI,) + OPERATIONS)[sid]
        self.ok("stage", "start", sid)
        self.put(self.ipath(intent, doc), text or "# %s\n\nwritten for %s by the agent\n" % (sid, intent))
        return self.ipath(intent, doc)

    def record(self, intent, sid, text=None):
        path = self.page(intent, sid, text)
        self.ok("stage", "done", sid, "--note", "%s written" % sid)
        return path

    def ideation_through_handoff(self, intent, optional="skip"):
        """intent-capture and scope-definition done, the optional stages skipped (or written), the brief done."""
        for sid, _, _ in IDEATION[:-1]:
            if sid in REQUIRED or optional == "write":
                self.record(intent, sid)
            else:
                self.ok("stage", "skip", sid, "--reason", "not needed for this idea")
        self.record(intent, "approval-handoff")

    def ideation_sha(self, intent):
        blobs = []
        for _, _, doc in IDEATION:
            path = os.path.join(self.dir, self.ipath(intent, doc))
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    blobs.append(f.read())
        return hashlib.sha256(b"\0".join(blobs)).hexdigest()

    def approve_ideation(self):
        out, h = self.approve("IDEATION")
        self.assertIn("Recorded: IDEATION approved (sha %s)" % h, out.stdout)
        return h

    def release(self, intent):
        """From approved requirements (design skipped as small) through verify, `release` and the RELEASE
        approval."""
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        out, h = self.approve("RELEASE")
        self.assertIn("Recorded: RELEASE approved", out.stdout)
        return h


# ---------------------------------------------------------------- 9.1 the stage table
class StageTable(V03):
    def test_the_new_stages_their_phases_files_templates_and_order(self):
        core = load_core()
        ids = [s.id for s in core.STAGES]
        self.assertEqual(ids, [s for s, _, _ in IDEATION] + [
            "reverse-engineering", "requirements", "user-stories", "application-design", "units", "functional-design",
            "nfr-design", "infrastructure-design", "code-generation", "build-and-test", "ci-pipeline", "release"]
            + [s for s, _, _ in OPERATIONS])
        for sid, name, doc in IDEATION + (CI,) + OPERATIONS:
            st = core.STAGE_BY_ID[sid]
            self.assertEqual((st.name, st.doc, st.template, st.per_unit), (name, doc, TEMPLATES[sid], False), sid)
            self.assertIn(TEMPLATES[sid], core.TEMPLATE_NAMES)
        self.assertEqual({s.phase for s in core.STAGES if s.id in dict((x, 1) for x, _, _ in IDEATION)}, {"ideation"})
        self.assertEqual({s.phase for s in core.STAGES if s.id in dict((x, 1) for x, _, _ in OPERATIONS)},
                         {"operations"})
        self.assertEqual(core.STAGE_BY_ID["ci-pipeline"].phase, "construction")
        self.assertEqual(core.IDEATION_REQUIRED, REQUIRED)
        self.assertEqual(sorted(core.AFTER_RELEASE_IDS), sorted(["ci-pipeline"] + [s for s, _, _ in OPERATIONS]))
        self.assertIn("IDEATION", core.APPROVAL_KINDS)
        self.assertEqual(core.VERSION, "0.3.1")
        m = core.APPROVE_RE.search("approve IDEATION 1a2b3c4d")
        self.assertEqual((m.group(2), m.group(3)), ("IDEATION", "1a2b3c4d"))

    def test_stage_progress_order_with_ideation_and_two_units(self):
        i = self.new_ideation()
        self.units(i, [("api", "shop", "services/api/"), ("web", "shop", "web/")])
        labels = [re.sub(r"^- \[.\] ([^—]+?)( — .*)?$", r"\1", l) for l in self.progress(i)]
        per_unit = ["Functional Design", "NFR Requirements + Design", "Infrastructure Design", "Code Generation"]
        self.assertEqual(labels, [n for _, n, _ in IDEATION] + [
            "Reverse Engineering", "Requirements Analysis", "User Stories", "Application Design", "Units Generation"]
            + ["%s (api)" % n for n in per_unit] + ["%s (web)" % n for n in per_unit]
            + ["Build and Test", "CI Pipeline", "Release"] + [n for _, n, _ in OPERATIONS])

    def test_usage_and_version(self):
        out = self.ok("--help").stdout
        for text in ("new <slug> [--title T] [--ideation]", 'stage skip ideation|operations --reason "<text>"',
                     "request IDEATION|REQUIREMENTS|DESIGN|INCEPTION|PLAN [--unit U]|RELEASE|CR-<team>-<n>",
                     "After RELEASE only the Operations stages and ci-pipeline take stage commands."):
            self.assertIn(text, out)
        for sid, _, doc in IDEATION + (CI,) + OPERATIONS:
            self.assertRegex(out, r"(?m)^  %s +%s " % (re.escape(sid), re.escape(doc)))
        self.assertEqual(self.ok("--version").stdout.strip(), "0.3.1")
        p = self.tool("stage", "bogus")
        self.assertIn("phases (stage skip only): ideation, operations", p.stdout)


# ---------------------------------------------------------------- 9.2 Ideation is opt-in per intent
class NewWithoutIdeation(V03):
    def test_new_records_the_whole_ideation_phase_as_skipped(self):
        p = self.ok("new", "refunds", "--title", "Refunds")
        i = re.search(r"aidlc-docs/(\S+) \(", p.stdout).group(1)
        self.assertIn("Created aidlc-docs/%s (aidlc-state.md, decisions.md, %s)" % (i, REQ), p.stdout)
        self.assertIn("Ideation is recorded as skipped (not requested)", p.stdout)
        skips = self.events("PHASE_SKIPPED")
        self.assertEqual([(e["intent"], e["data"]) for e in skips], [
            (i, {"phase": "ideation", "stages": [s for s, _, _ in IDEATION], "reason": NOT_REQUESTED})])
        self.assertEqual(self.events("STAGE_SKIPPED"), [])  # one phase-level record, not seven stage skips
        self.assertEqual(self.events("INTENT_CREATED")[-1]["data"], {"title": "Refunds", "ideation": False})
        self.assertFalse(self.exists(self.ipath(i, "ideation")))
        lines = self.progress(i)
        self.assertEqual(lines[:3], [SKIPPED_LINE, "- [ ] Reverse Engineering", "- [-] Requirements Analysis — in "
                                                                               "progress"])
        self.assertEqual([l for l in lines if "Intent Capture" in l or "Ideation" in l], [SKIPPED_LINE])
        self.assertRegex(self.log(i), r"\n### Ideation · \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC · by dev@example.com "
                                      r"\(team -\) · via CLI\n- Skipped: not requested \(lean new without "
                                      r"--ideation\)\n")
        self.assertNotIn("- Stages:", self.log(i))  # it covered the whole phase
        st = self.status()
        self.assertIn("Next: finish requirements.md and the application design", st)  # developers' flow as before
        self.assertIn("    " + SKIPPED_LINE + "\n    - [ ] Reverse Engineering\n", st)

    def test_ideation_is_not_needed_for_approvals_or_code(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.assertEqual(self.write("src/app.py").returncode, 0)
        r = self.tool("request", "IDEATION")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Cannot request IDEATION: %s does not use Ideation (Ideation skipped: %s)" % (i, NOT_REQUESTED),
                      r.stdout)
        self.ok("verify")
        self.commit_all()
        self.ok("release")

    def test_stage_start_reopens_ideation_until_the_requirements_are_approved(self):
        i = self.intent()
        self.requirements(i, "small")
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        self.request_hash("REQUIREMENTS")  # a request alone does not close Ideation
        p = self.ok("stage", "start", "market-research")
        self.assertIn("Created %s" % self.ipath(i, "ideation/market-research/market-research.md"), p.stdout)
        lines = self.progress(i)
        self.assertNotIn(SKIPPED_LINE, lines)  # the start supersedes the phase-level skip, for every Ideation stage
        self.assertEqual(lines[:7], ["- [ ] Intent Capture", "- [-] Market Research — in progress", "- [ ] Feasibility",
                                     "- [ ] Scope Definition", "- [ ] Team Formation", "- [ ] Rough Mockups",
                                     "- [ ] Approval Handoff"])
        self.assertIn("Next: Ideation: Intent Capture: %sstage start intent-capture` (skill aidlc-lean-ideation)" % LEAN,
                      self.status())
        # Ideation in use: the requirements wait for IDEATION
        r = self.tool("request", "REQUIREMENTS")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Cannot request REQUIREMENTS: Ideation is in use for %s and IDEATION is missing" % i, r.stdout)
        r = self.write("src/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (ideation): Ideation is in use for %s and IDEATION is missing" % i, r.stderr)
        # dropped again (nothing was requested yet): one line, the new reason
        self.ok("stage", "skip", "ideation", "--reason", "started by mistake")
        self.assertEqual(self.progress(i)[0], "- [S] Ideation — skipped: started by mistake")
        self.approve("REQUIREMENTS")
        for args in (["start", "intent-capture"], ["done", "market-research", "--note", "x"]):
            p = self.tool("stage", *args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn("Ideation is not in use for %s (Ideation skipped: started by mistake) and its requirements "
                          "are approved (REQUIREMENTS, " % i, p.stdout)
            self.assertIn("Start a new intent with %snew <slug> --ideation`." % LEAN, p.stdout)
        self.assertEqual(self.events("STAGE_STARTED")[-1]["data"]["stage"], "market-research")
        self.assertEqual(self.write("src/app.py").returncode, 0)

    def test_an_inception_approval_also_closes_the_reopening(self):
        i = self.intent()
        self.requirements(i, "large")
        self.design(i)
        self.approve("INCEPTION")
        p = self.tool("stage", "start", "intent-capture")
        self.assertEqual(p.returncode, 1)
        self.assertIn("its requirements are approved (INCEPTION, ", p.stdout)
        self.assertIn(SKIPPED_LINE, self.progress(i))


class NewWithIdeation(V03):
    def test_new_with_ideation_starts_with_intent_capture(self):
        p = self.ok("new", "refunds", "--ideation", "--title", "Refunds")
        i = re.search(r"aidlc-docs/(\S+) \(", p.stdout).group(1)
        self.assertIn("(aidlc-state.md, decisions.md, ideation/intent-capture/intent-statement.md)", p.stdout)
        self.assertIn("skill aidlc-lean-ideation", p.stdout)
        self.assertTrue(self.exists(self.ipath(i, "ideation/intent-capture/intent-statement.md")))
        self.assertFalse(self.exists(self.req_path(i)))  # Inception comes after the hand-off
        self.assertNotIn("{{", self.read(self.ipath(i, "ideation/intent-capture/intent-statement.md")))
        self.assertEqual(self.events("PHASE_SKIPPED"), [])
        self.assertEqual(self.events("INTENT_CREATED")[-1]["data"], {"title": "Refunds", "ideation": True})
        ev = self.events("STAGE_STARTED")[-1]
        self.assertEqual((ev["data"]["stage"], ev["data"]["created"]), ("intent-capture", True))
        lines = self.progress(i)
        self.assertEqual(lines[0], "- [-] Intent Capture — in progress")
        self.assertIn("- [ ] Requirements Analysis", lines)
        notes = self.read(self.ipath(i, "aidlc-state.md")).split("## Session notes", 1)[1]
        self.assertIn("Status: Ideation: starting", notes)  # not the template's Inception start
        self.assertIn("skill aidlc-lean-ideation", notes)
        self.assertNotIn("reverse-engineering", notes)
        self.assertIn("### Open questions and blockers", notes)  # the rest of the notes is kept
        self.assertIn("Next: Ideation: finish Intent Capture (ideation/intent-capture/intent-statement.md), then "
                      "%sstage done intent-capture --note ...`" % LEAN, self.status())
        p = self.tool("stage", "done", "intent-capture", "--note", "x")  # still the template
        self.assertEqual(p.returncode, 1)
        self.assertIn("still the template", p.stdout)
        j = self.new_ideation("other", "--title", "Other")  # --ideation may come anywhere after the slug
        self.assertEqual(intent_title(self, j), "Other")

    def test_required_stages_cannot_be_skipped_while_ideation_is_in_use(self):
        self.new_ideation()
        for sid in REQUIRED:
            p = self.tool("stage", "skip", sid, "--reason", "not needed")
            self.assertEqual(p.returncode, 1, sid)
            self.assertIn("cannot be skipped while Ideation is in use (intent-capture, scope-definition and "
                          "approval-handoff are required then)", p.stdout)
        for sid in ("market-research", "feasibility", "team-formation", "rough-mockups"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.assertEqual(len(self.events("STAGE_SKIPPED")), 4)

    def test_next_walks_the_ideation_stages_then_ideation_then_inception(self):
        i = self.new_ideation()
        self.put(self.ipath(i, IDEATION[0][2]), "# Intent\n\nrefunds for buyers\n")
        self.assertIn("Next: Ideation: finish Intent Capture", self.status())
        self.ok("stage", "done", "intent-capture", "--note", "problem, customer, metrics")
        self.assertIn("Next: Ideation: Market Research: %sstage start market-research` (skill aidlc-lean-ideation), fill "
                      "in the page, then `stage done market-research --note ...`; it is optional: `stage skip "
                      "market-research --reason ...` when it adds nothing" % LEAN, self.status())
        for sid in ("market-research", "feasibility"):
            self.ok("stage", "skip", sid, "--reason", "internal tool")
        st = self.status()
        self.assertIn("Next: Ideation: Scope Definition: %sstage start scope-definition`" % LEAN, st)
        self.assertNotIn("it is optional", st.split("Next:")[1].splitlines()[0])  # a required stage
        self.record(i, "scope-definition")
        for sid in ("team-formation", "rough-mockups"):
            self.ok("stage", "skip", sid, "--reason", "same team, no screens")
        self.assertIn("Next: Ideation: write the initiative brief: %sstage start approval-handoff`" % LEAN, self.status())
        self.page(i, "approval-handoff")
        self.assertIn("Next: Ideation: finish the initiative brief (ideation/approval-handoff/initiative-brief.md), "
                      "%sstage done approval-handoff --note ...`, then `request IDEATION`" % LEAN, self.status())
        p = self.ok("stage", "done", "approval-handoff", "--note", "go")
        self.assertIn("It needs the human's approval: %srequest IDEATION` (it covers every Ideation page)." % LEAN,
                      p.stdout)
        self.assertIn("- [-] Approval Handoff — done · ", self.status())
        self.assertIn("Next: %srequest IDEATION` (it covers every Ideation page) and wait for the human to approve; "
                      "Inception comes next" % LEAN, self.status())
        h = self.request_hash("IDEATION")
        self.assertIn("Next: wait for the human to type `approve IDEATION %s`" % h, self.status())
        self.assertIn("- [A] Approval Handoff — waiting for approval: approve IDEATION %s" % h, self.status())
        self.say("approve IDEATION %s" % h)
        st = self.status()
        self.assertIn("- [x] Approval Handoff — approved via IDEATION (sha %s) · " % h, st)
        self.assertIn("Next: write requirements.md: %sstage start requirements` (skill aidlc-lean-inception)" % LEAN, st)


class IdeationApproval(V03):
    def test_the_hash_covers_every_existing_ideation_page_in_stage_order(self):
        i = self.new_ideation()
        r = self.tool("request", "IDEATION")
        self.assertEqual(r.returncode, 1)
        self.assertIn("IDEATION needs the pages of Intent Capture, Scope Definition and Approval Handoff; %s has no "
                      "page yet for Scope Definition, Approval Handoff" % i, r.stdout)
        self.put(self.ipath(i, IDEATION[0][2]), "# intent\n")
        self.ok("stage", "done", "intent-capture", "--note", "x")
        for sid in ("market-research", "feasibility", "team-formation"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.record(i, "rough-mockups", "# flows\n")  # optional pages count when they exist
        self.record(i, "scope-definition", "# scope\n")
        self.record(i, "approval-handoff", "# brief\n")
        p = self.ok("request", "IDEATION")
        files = [self.ipath(i, d) for s, _, d in IDEATION if s in REQUIRED + ("rough-mockups",)]
        self.assertIn("Ask the human to read %s and, if they agree, type exactly:" % " and ".join(files), p.stdout)
        self.assertIn("Any later change to these pages, or a new Ideation page, voids the approval.", p.stdout)
        expect = hashlib.sha256(b"# intent\n\0# scope\n\0# flows\n\0# brief\n").hexdigest()
        self.assertEqual(expect, self.ideation_sha(i))
        self.assertIn("approve IDEATION %s" % expect[:8], p.stdout)
        req = self.events("APPROVAL_REQUESTED")[-1]["data"]
        self.assertEqual((req["kind"], req["paths"], req["sha256"]), ("IDEATION", files, expect))
        self.assertEqual(req["files"], {f: hashlib.sha256(self.read(f).encode()).hexdigest() for f in files})
        out = self.say("approve IDEATION %s" % expect[:8])
        self.assertIn("Recorded: IDEATION approved (sha %s) by dev@example.com: the Ideation pages (intent-statement.md, "
                      "scope-document.md, wireframes.md, initiative-brief.md)." % expect[:8], out.stdout)
        ev = self.events("APPROVED")[-1]["data"]
        self.assertEqual((ev["kind"], ev["sha256"], sorted(ev["files"])), ("IDEATION", expect, sorted(files)))
        self.assertRegex(self.log(i), r"### IDEATION approved \(sha %s\) · .* · human \(prompt\)\n- Covers: "
                                      r"ideation/approval-handoff/initiative-brief.md, " % expect[:8])
        # a new Ideation page voids it, as an edit does
        self.page(i, "market-research", "# market\n")
        self.assertIn("- [-] Approval Handoff — stale: an Ideation page changed since it was approved via IDEATION "
                      "(sha %s)" % expect[:8], self.status())
        self.assertIn("Next: Ideation: finish Market Research (", self.status())  # the next Ideation stage first
        self.ok("stage", "done", "market-research", "--note", "competitors after all")
        self.assertIn("Next: an Ideation page changed since IDEATION was approved: %srequest IDEATION` again" % LEAN,
                      self.status())
        out = self.say("approve IDEATION %s" % expect[:8])
        self.assertIn("Approval of IDEATION NOT recorded: the file changed since that request", out.stdout)
        self.assertEqual(self.events("APPROVAL_REFUSED")[-1]["data"]["check"], "hash")
        self.approve_ideation()

    def test_requirements_code_and_release_need_ideation_approved(self):
        self.cfg(checks=["true"])
        i = self.new_ideation()
        self.ideation_through_handoff(i)
        self.ok("stage", "start", "requirements")
        self.requirements(i, "small")
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        r = self.tool("request", "REQUIREMENTS")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Cannot request REQUIREMENTS: Ideation is in use for %s and IDEATION is draft: finish the "
                      "Ideation pages (skill aidlc-lean-ideation) and get the human's approval (%srequest IDEATION`); "
                      "the requirements are approved after the Ideation hand-off." % (i, LEAN), r.stdout)
        self.assertEqual(self.tool("request", "INCEPTION").returncode, 1)
        req_sha = hashlib.sha256(self.read(self.req_path(i)).encode()).hexdigest()
        out = self.say("approve REQUIREMENTS %s" % req_sha[:8])
        self.assertIn("Approval of REQUIREMENTS NOT recorded: Ideation is in use for %s and IDEATION is draft" % i,
                      out.stdout)
        refused = self.events("APPROVAL_REFUSED")[-1]["data"]
        self.assertEqual((refused["kind"], refused["check"]), ("REQUIREMENTS", "ideation"))
        r = self.write("src/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (ideation): Ideation is in use for %s and IDEATION is draft" % i, r.stderr)
        self.assertEqual(self.events("BLOCKED")[-1]["data"]["gate"], "ideation")
        h = self.request_hash("IDEATION")
        r = self.write("src/app.py")
        self.assertIn("the request is out: wait for the human to type `approve IDEATION %s` before writing code" % h,
                      r.stderr)
        self.say("approve IDEATION %s" % h)
        r = self.write("src/app.py")
        self.assertIn("blocked (requirements)", r.stderr)  # IDEATION done: the usual gates follow
        self.approve("REQUIREMENTS")
        self.assertEqual(self.write("src/app.py").returncode, 0)
        # standard mode: a stale IDEATION still lets code through (shown as stale); the release needs it current
        self.put(self.ipath(i, IDEATION[3][2]), self.read(self.ipath(i, IDEATION[3][2])) + "\n- one more item\n")
        self.assertEqual(self.write("src/app.py").returncode, 0)
        self.ok("verify")
        self.commit_all()
        p = self.tool("release")
        self.assertEqual(p.returncode, 1)
        self.assertIn("Not ready to release: IDEATION is stale", p.stdout)
        self.approve_ideation()
        self.ok("release")
        self.approve("RELEASE")
        rows = [l for l in self.read(self.ipath(i, "operations/release.md")).splitlines() if l.startswith("| IDEATION")]
        self.assertEqual([r.split(" | ")[0] for r in rows], ["| IDEATION (superseded)", "| IDEATION"])

    def test_rejection_and_approvers(self):
        i = self.new_ideation()
        self.ideation_through_handoff(i)
        self.request_hash("IDEATION")
        out = self.say("reject IDEATION: the scope is too wide")
        self.assertIn("Recorded: IDEATION rejected by the human.", out.stdout)
        st = self.status()
        self.assertIn("- [-] Approval Handoff — rejected · ", st)
        self.assertIn("Next: IDEATION was rejected: revise the Ideation pages as the human asked, then %srequest "
                      "IDEATION`" % LEAN, st)
        self.cfg(approvers={"IDEATION": ["pm@example.com"]})
        out, h = self.approve("IDEATION")
        self.assertIn("Approval of IDEATION NOT recorded: dev@example.com is not in approvers for IDEATION.", out.stdout)
        self.assertEqual(self.events("APPROVAL_REFUSED")[-1]["data"]["check"], "approvers")
        self.sh(["git", "config", "user.email", "pm@example.com"])
        out = self.say("approve IDEATION %s" % h)
        self.assertIn("Recorded: IDEATION approved (sha %s) by pm@example.com" % h, out.stdout)
        self.assertEqual(self.events("APPROVED")[-1]["actor"]["git_email"], "pm@example.com")

    def test_an_ideation_requested_or_decided_can_no_longer_be_dropped(self):
        i = self.new_ideation()
        self.ideation_through_handoff(i)
        self.record(i, "market-research")  # an optional stage written after its skip
        self.request_hash("IDEATION")
        p = self.tool("stage", "skip", "ideation", "--reason", "not needed after all")
        self.assertEqual(p.returncode, 1)
        self.assertIn("Ideation is in use for %s and IDEATION was requested (" % i, p.stdout)
        self.assertEqual(self.events("PHASE_SKIPPED"), [])


class IdeationRegulated(V03):
    flags = ["--regulated"]

    def test_regulated_mode_needs_the_hash_and_a_current_ideation(self):
        self.cfg(checks=["true"])
        i = self.new_ideation()
        self.ideation_through_handoff(i)
        out = self.say("approve IDEATION")
        self.assertIn("Approval of IDEATION NOT recorded: regulated mode needs the hash shown in the request, e.g. "
                      "`approve IDEATION %s`." % self.ideation_sha(i)[:8], out.stdout)
        self.approve_ideation()
        self.ok("stage", "start", "requirements")
        self.requirements(i, "small")
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        self.approve("REQUIREMENTS")
        self.ok("stage", "start", "code-generation")
        self.approve("PLAN")
        self.assertEqual(self.write("src/app.py").returncode, 0)
        self.put(self.ipath(i, IDEATION[0][2]), self.read(self.ipath(i, IDEATION[0][2])) + "\nedited\n")
        r = self.write("src/app.py")  # regulated: a stale IDEATION blocks
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (ideation): Ideation is in use for %s and IDEATION is stale: an Ideation page changed "
                      "(or was added or removed) since its approval" % i, r.stderr)
        out = self.say("approve REQUIREMENTS %s" % hashlib.sha256(self.read(self.req_path(i)).encode()).hexdigest()[:8])
        self.assertIn("Approval of REQUIREMENTS NOT recorded: Ideation is in use for %s and IDEATION is stale" % i,
                      out.stdout)


# ---------------------------------------------------------------- 9.2 phase skip
class PhaseSkip(V03):
    def test_skip_operations_covers_its_stages_but_not_ci_pipeline(self):
        i = self.intent()
        p = self.ok("stage", "skip", "operations", "--reason", "the platform team deploys and monitors")
        self.assertIn("Recorded: Operations skipped (the platform team deploys and monitors): Deployment Pipeline, "
                      "Environment Provisioning, Deployment Execution, Observability Setup, Incident Response, "
                      "Performance Validation, Feedback Optimization.", p.stdout)
        ev = self.events("PHASE_SKIPPED")[-1]["data"]
        self.assertEqual(ev, {"phase": "operations", "stages": [s for s, _, _ in OPERATIONS],
                              "reason": "the platform team deploys and monitors"})
        lines = self.progress(i)
        self.assertEqual(lines[-3:], ["- [ ] CI Pipeline", "- [ ] Release",
                                      "- [S] Operations — skipped: the platform team deploys and monitors"])
        self.assertEqual(len([l for l in lines if "Deployment" in l]), 0)
        self.assertIn("\n### Operations · ", self.log(i))
        p = self.ok("stage", "skip", "operations", "--reason", "again")
        self.assertIn("Every stage of Operations already has a record (done or skipped); nothing to skip.", p.stdout)
        self.assertEqual(len(self.events("PHASE_SKIPPED")), 2)  # new's Ideation skip and this one
        p = self.ok("stage", "skip", "ideation", "--reason", "x")  # new already skipped every Ideation stage
        self.assertIn("Every stage of Ideation already has a record", p.stdout)
        self.ok("stage", "skip", "ci-pipeline", "--reason", "existing CI is adequate")
        self.assertIn("- [S] CI Pipeline — skipped: existing CI is adequate", self.progress(i))

    def test_a_phase_skip_covers_only_the_stages_without_a_record(self):
        i = self.intent()
        self.record(i, "deployment-pipeline")
        self.ok("stage", "skip", "observability-setup", "--reason", "the platform has it")
        self.page(i, "incident-response")  # started, not done: no record yet
        p = self.ok("stage", "skip", "operations", "--reason", "nothing else changes")
        self.assertIn(": Environment Provisioning, Deployment Execution, Incident Response, Performance Validation, "
                      "Feedback Optimization.", p.stdout)
        lines = self.progress(i)
        self.assertNotIn("- [S] Operations", "\n".join(lines))  # not all skipped by one phase skip: one line each
        self.assertEqual(lines[-7:], [
            "- [x] Deployment Pipeline — done · %s" % self.events("STAGE_COMPLETED")[-1]["ts"][:10],
            "- [S] Environment Provisioning — skipped: nothing else changes",
            "- [S] Deployment Execution — skipped: nothing else changes",
            "- [S] Observability Setup — skipped: the platform has it",
            "- [S] Incident Response — skipped: nothing else changes",
            "- [S] Performance Validation — skipped: nothing else changes",
            "- [S] Feedback Optimization — skipped: nothing else changes"])
        self.assertIn("- Skipped: nothing else changes\n- Stages: Environment Provisioning, Deployment Execution, "
                      "Incident Response, Performance Validation, Feedback Optimization\n", self.log(i))
        self.ok("stage", "start", "deployment-execution")  # a stage's own record after the phase skip counts
        self.assertIn("- [-] Deployment Execution — in progress", self.progress(i))
        self.assertIn("- [S] Feedback Optimization — skipped: nothing else changes", self.progress(i))

    def test_phase_arguments(self):
        self.intent()
        for args, msg in ((["start", "operations"], "Operations is a phase: `stage skip operations --reason"),
                          (["done", "ideation", "--note", "x"], "Ideation is a phase"),
                          (["skip", "operations"], "`stage skip operations` needs --reason"),
                          (["skip", "operations", "--unit", "app", "--reason", "x"], "unexpected argument: --unit")):
            p = self.tool("stage", *args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn(msg, p.stdout)
        self.assertEqual(len(self.events("PHASE_SKIPPED")), 1)

    def test_dropping_an_ideation_in_use_that_nothing_requested(self):
        self.cfg(checks=["true"])
        i = self.new_ideation()
        self.record(i, "intent-capture")
        self.ok("stage", "skip", "ideation", "--reason", "a developer task after all")
        lines = self.progress(i)
        self.assertEqual(lines[:2], ["- [x] Intent Capture — done · %s" % self.events("STAGE_COMPLETED")[-1]["ts"][:10],
                                     "- [S] Market Research — skipped: a developer task after all"])
        self.assertIn("- [S] Approval Handoff — skipped: a developer task after all", lines)
        self.ok("stage", "start", "requirements")
        self.requirements(i, "small")
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        self.approve("REQUIREMENTS")  # Ideation is no longer in use: nothing waits for IDEATION
        self.assertEqual(self.write("src/app.py").returncode, 0)


# ---------------------------------------------------------------- 9.2 Operations after RELEASE
class AfterRelease(V03):
    def test_operations_and_ci_pipeline_take_stage_commands_after_release(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.record(i, "deployment-pipeline")  # before RELEASE: recorded, nothing is gated on it
        self.record(i, "ci-pipeline")
        h = self.release(i)
        body = self.read(self.ipath(i, "operations/release.md"))
        self.assertIn("\n- [S] Ideation — skipped: %s\n" % NOT_REQUESTED, body)  # release.md lists what exists then
        self.assertIn("\n- [x] Deployment Pipeline — done · ", body)
        self.assertIn("\n- [ ] Deployment Execution\n", body)
        st = self.status()
        self.assertIn("RELEASED: RELEASE is approved, so this intent is closed.", st)
        self.assertIn("Next: optional: record deployment and operations (skill aidlc-lean-operations) or %sstage skip "
                      "operations --reason ...`; the intent stays released. New work: %snew <slug>`; small edits need "
                      "no intent" % (LEAN, LEAN), st)
        self.assertNotIn("...\n", self.hook("SessionStart", {}).stdout.split("Next: ")[1].split("\n")[0] + "\n")
        self.assertIn("- [x] Release — released: approved (sha %s)" % h, st)
        log = self.record(i, "deployment-execution", "# Deployment log\n\n| when | version | env |\n|---|---|---|\n"
                                                      "| 2026-11-08 | v1 | prod |\n")
        self.assertTrue(self.exists(log))
        self.record(i, "ci-pipeline", "# CI\n\nchanged after the release\n")  # ci-pipeline too
        for args in (["start", "user-stories"], ["skip", "functional-design", "--reason", "late"],
                     ["start", "intent-capture"], ["skip", "ideation", "--reason", "late"]):
            p = self.tool("stage", *args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn("%s is released (RELEASE approved); its record is closed." % i, p.stdout)
            self.assertIn("(After RELEASE only the Operations stages and ci-pipeline take stage commands.)", p.stdout)
        self.ok("stage", "skip", "operations", "--reason", "the platform team runs the rest")
        st = self.status()
        self.assertIn("Next: nothing: this intent is released (RELEASE approved).", st)
        self.assertIn("RELEASED: RELEASE is approved", st)
        self.assertIn("- [x] Deployment Execution — done · ", st)
        self.assertIn("- [S] Feedback Optimization — skipped: the platform team runs the rest", st)
        self.assertEqual(self.write("src/app.py").returncode, 0)  # standard mode: as with no active intent
        self.ok("audit", "pack")  # the Operations records after RELEASE are part of this intent's trail
        pack = self.read(self.ipath(i, "audit.md"))
        self.assertIn("Deployment Execution done — deployment-execution written", pack)
        self.assertIn("Operations skipped — the platform team runs the rest (stages: ", pack)
        self.assertIn("Ideation skipped — %s" % NOT_REQUESTED, pack)
        self.assertEqual(len(re.findall(r"CI Pipeline done", pack)), 2)

    def test_an_intent_with_every_operations_stage_recorded_has_nothing_next(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.ok("stage", "skip", "operations", "--reason", "no deployment: a library")
        self.release(i)
        self.assertIn("Next: nothing: this intent is released (RELEASE approved). Start new work", self.status())


# ---------------------------------------------------------------- legacy intents and the context hooks
class Compatibility(V03):
    def test_an_intent_from_before_v03_shows_ideation_as_not_used(self):
        self.ok("new", "current")
        old = "261001-legacy"
        self.put(self.ipath(old, "aidlc-state.md"), "# AI-DLC State: legacy\nIntent: %s\n%s\n%s\n## Session notes\n"
                 "### Next\n1. go on\n" % (old, BEGIN, END))
        self.ok("use", old)
        lines = self.progress(old)
        self.assertEqual(lines[0], "- [S] Ideation — not used (no Ideation record: the intent was started before "
                                   "AI-DLC Lean 0.3)")
        self.assertEqual(len([l for l in lines if l.startswith("- [S] Ideation")]), 1)
        self.assertIn("Next: write requirements.md", self.status())

    def test_session_start_context_shows_the_one_line_skip(self):
        self.intent()
        out = self.hook("SessionStart", {}).stdout
        self.assertIn("  Stage progress:\n    %s\n    - [ ] Reverse Engineering\n" % SKIPPED_LINE, out)
        self.assertNotIn("truncated", out)


# ---------------------------------------------------------------- the real templates for the new stages
class RealTemplatesV03(Base):
    """Every new page comes from its shipped template (stand-ins only where the kit ships none) and `stage done`
    refuses it until it is edited."""

    def test_each_new_stage_page_is_refused_until_it_is_edited(self):
        p = self.ok("new", "refunds", "--title", "Refunds EU", "--ideation")
        i = re.search(r"aidlc-docs/(\S+) \(", p.stdout).group(1)
        for sid, _, doc in IDEATION + (CI,) + OPERATIONS:
            if sid != "intent-capture":
                self.assertIn("Created %s" % self.ipath(i, doc), self.ok("stage", "start", sid).stdout)
            text = self.read(self.ipath(i, doc))
            self.assertNotIn("{{", text, sid)
            self.assertIn("Refunds EU", text, sid)
            r = self.tool("stage", "done", sid, "--note", "nothing yet")
            self.assertEqual(r.returncode, 1, (sid, r.stdout))
            self.assertIn("is still the template", r.stdout, sid)
            self.put(self.ipath(i, doc), text + "\nWritten by the agent.\n")
            self.ok("stage", "done", sid, "--note", "filled in")


# ---------------------------------------------------------------- the kit texts for the new phases
class KitTextsV03(unittest.TestCase):
    """The texts the agent reads name the new stages, phases and the IDEATION approval as the tool has them."""

    @classmethod
    def setUpClass(cls):
        cls.core = load_core()
        kit = os.path.join(REPO, "kit", ".kiro")
        cls.kit = kit

        def read(*parts):
            with open(os.path.join(kit, *parts), encoding="utf-8") as f:
                return f.read()
        cls.read = staticmethod(read)

    def skill(self, name):
        path = os.path.join(self.kit, "skills", name, "SKILL.md")
        self.assertTrue(os.path.exists(path), path)
        return self.read("skills", name, "SKILL.md")

    def test_the_new_skills_and_the_steering_explain_the_optional_phases(self):
        ideation, operations = self.skill("aidlc-lean-ideation"), self.skill("aidlc-lean-operations")
        for word in ("IDEATION", "--ideation", "stage skip ideation", "stage start intent-capture"):
            self.assertIn(word, ideation)
        for word in ("stage skip operations", "stage skip ci-pipeline", "never deploy"):
            self.assertIn(word, operations)
        steering = self.read("steering", "aidlc-lean.md")
        for word in ("IDEATION", "--ideation", "aidlc-lean-ideation", "aidlc-lean-operations"):
            self.assertIn(word, steering)


def intent_title(test, intent):
    return re.search(r"(?m)^# AI-DLC State: (.+)$", test.read(test.ipath(intent, "aidlc-state.md"))).group(1)


if __name__ == "__main__":
    unittest.main()
