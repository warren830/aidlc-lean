"""Tests for the v0.2 stage record and approvals (docs/design-v0.2.md).

Covers: every `stage` command and its skip rules, units from unit-of-work.md, INCEPTION (one approval for
requirements.md and application-design.md, each file going stale on its own), PLAN per unit in regulated mode,
released intents, the generated region of aidlc-state.md (the Session notes stay as they are), verify's
build-and-test summary, audit.md, the files only the tool writes, units of two teams next to a contract change
request, and doctor's checks for the v0.2 layout.

Run: python3 -m unittest discover -s tests -v
"""
import hashlib
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_aidlc_lean import DESIGN, DOCS, REQ, SUMMARY, UNITS, Base  # noqa: E402

PLAN = "construction/plans/%s-code-generation-plan.md"
BEGIN = "<!-- lean:begin progress -->"
END = "<!-- lean:end progress -->"
PLACEHOLDERS = ("{{TITLE}}", "{{INTENT}}", "{{DATE}}", "{{UNIT}}", "{{STAGE}}")
STAGE_DOCS = (("reverse-engineering", "inception/reverse-engineering/architecture.md"),
              ("user-stories", "inception/user-stories/stories.md"),
              ("application-design", DESIGN),
              ("units", UNITS),
              ("functional-design", "construction/app/functional-design/functional-design.md"),
              ("nfr-design", "construction/app/nfr-design/nfr-design.md"),
              ("infrastructure-design", "construction/app/infrastructure-design/infrastructure-design.md"),
              ("code-generation", PLAN % "app"))


class V02(Base):
    def sha(self, path):
        with open(os.path.join(self.dir, path), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def status(self):
        return self.tool("status").stdout

    def state(self, intent):
        return self.read(self.ipath(intent, "aidlc-state.md"))

    def fill(self, path, extra="\nfilled in by the agent\n"):
        self.put(path, self.read(path) + extra)


class StageCommands(V02):
    def test_new_creates_the_three_documents_and_starts_requirements(self):
        p = self.ok("new", "Market Place!", "--title", "Market place")
        i = re.search(r"aidlc-docs/(\S+) \(", p.stdout).group(1)
        self.assertRegex(i, r"^\d{6}-market-place$")
        for doc in ("aidlc-state.md", "decisions.md", REQ):
            text = self.read(self.ipath(i, doc))
            for ph in PLACEHOLDERS:
                self.assertNotIn(ph, text, doc)
        state = self.state(i)
        self.assertEqual((state.count(BEGIN), state.count(END)), (1, 1))
        self.assertIn("- [-] Requirements Analysis — in progress", state)
        self.assertIn("Active intent: aidlc-docs/%s (Market place)" % i, self.status())
        ev = self.events("STAGE_STARTED")[-1]
        self.assertEqual((ev["intent"], ev["data"]["stage"], ev["data"]["path"]), (i, "requirements", self.req_path(i)))
        self.assertEqual(self.tool("new", "market-place").returncode, 1)  # the same slug on the same day
        self.assertEqual(self.tool("new", "???").returncode, 1)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, DOCS))), sorted(["audit", i, "lean.json"]))

    def test_start_creates_each_document_from_its_template_once(self):
        i = self.intent()
        for sid, doc in STAGE_DOCS:
            self.assertFalse(self.exists(self.ipath(i, doc)), sid)
            p = self.ok("stage", "start", sid)
            self.assertIn("Created %s" % self.ipath(i, doc), p.stdout)
            text = self.read(self.ipath(i, doc))
            for ph in PLACEHOLDERS:
                self.assertNotIn(ph, text, sid)
        started = [(e["data"]["stage"], e["data"]["unit"], e["data"]["created"]) for e in self.events("STAGE_STARTED")]
        self.assertIn(("functional-design", "app", True), started)
        self.assertIn(("units", None, True), started)
        self.put(self.ipath(i, DESIGN), "# mine\n")  # an existing document is never overwritten
        p = self.ok("stage", "start", "application-design")
        self.assertIn("Kept the existing", p.stdout)
        self.assertEqual(self.read(self.ipath(i, DESIGN)), "# mine\n")
        self.assertIn("- [-] Application Design — in progress", self.status())

    def test_done_needs_a_filled_in_document_and_a_note(self):
        i = self.intent()
        doc = self.ipath(i, "inception/user-stories/stories.md")
        p = self.tool("stage", "done", "user-stories", "--note", "x")
        self.assertEqual(p.returncode, 1)
        self.assertIn("does not exist", p.stdout)
        self.ok("stage", "start", "user-stories")
        p = self.tool("stage", "done", "user-stories", "--note", "two personas")
        self.assertEqual(p.returncode, 1)
        self.assertIn("still the template", p.stdout)
        self.fill(doc, "\n| US-1 | buyer | a refund | money back | AC-1 |\n")
        p = self.tool("stage", "done", "user-stories")
        self.assertEqual(p.returncode, 1)
        self.assertIn("needs --note", p.stdout)
        self.ok("stage", "done", "user-stories", "--note", "Inputs: requirements.md. Wrote US-1; token=abc123")
        ev = self.events("STAGE_COMPLETED")[-1]
        self.assertEqual((ev["data"]["stage"], ev["data"]["unit"]), ("user-stories", None))
        self.assertEqual(ev["data"]["outputs"], {doc: self.sha(doc)})
        self.assertEqual(ev["data"]["note"], "Inputs: requirements.md. Wrote US-1; token=***")  # masked
        state = self.state(i)
        self.assertIn("- [x] User Stories — done · ", state)
        self.assertRegex(state, r"### User Stories · \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC · by dev@example.com \(team -\)")
        self.assertIn("- Did: Inputs: requirements.md. Wrote US-1; token=***", state)
        self.assertIn("- Outputs: inception/user-stories/stories.md (sha %s)" % self.sha(doc)[:8], state)
        self.fill(doc)
        self.assertIn("- [x] User Stories — done · %s (edited since)" % ev["ts"][:10], self.status())
        p = self.tool("stage", "done", "requirements", "--note", "x")  # requirements.md from `new` is untouched
        self.assertEqual(p.returncode, 1)
        self.assertIn("still the template", p.stdout)

    def test_untouched_means_the_template_rendered_on_any_day(self):
        self.put(".kiro/aidlc-lean/templates/stories.md",
                 "# User Stories: {{TITLE}}\n\nIntent: {{INTENT}} · Created: {{DATE}}\n\n| ID | Story |\n|---|---|\n")
        i = self.intent()
        self.ok("stage", "start", "user-stories")
        doc = self.ipath(i, "inception/user-stories/stories.md")
        text = self.read(doc)
        self.assertRegex(text, r"Created: \d{4}-\d{2}-\d{2}")
        self.put(doc, re.sub(r"\d{4}-\d{2}-\d{2}", "2020-01-31", text) + "\n\n")  # rendered on another day
        p = self.tool("stage", "done", "user-stories", "--note", "x")
        self.assertEqual(p.returncode, 1)
        self.assertIn("still the template", p.stdout)
        self.put(doc, text + "| US-1 | refunds |\n")
        self.ok("stage", "done", "user-stories", "--note", "one story")

    def test_skip_rules(self):
        i = self.intent()
        for sid in ("requirements", "code-generation", "build-and-test", "release"):
            p = self.tool("stage", "skip", sid, "--reason", "not needed")
            self.assertEqual(p.returncode, 1, sid)
            self.assertIn("cannot be skipped", p.stdout)
        self.requirements(i, "large")
        p = self.tool("stage", "skip", "application-design", "--reason", "simple")
        self.assertEqual(p.returncode, 1)
        self.assertIn("only when %s says `Size: small`" % REQ, p.stdout)
        self.requirements(i, "small")
        p = self.tool("stage", "skip", "application-design")
        self.assertEqual(p.returncode, 1)
        self.assertIn("needs --reason", p.stdout)
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        for sid in ("reverse-engineering", "user-stories", "units", "functional-design", "nfr-design",
                    "infrastructure-design"):
            self.ok("stage", "skip", sid, "--reason", "not needed for %s" % sid)
        skipped = [(e["data"]["stage"], e["data"]["unit"], e["data"]["reason"]) for e in self.events("STAGE_SKIPPED")]
        self.assertIn(("application-design", None, "one endpoint"), skipped)
        self.assertIn(("nfr-design", "app", "not needed for nfr-design"), skipped)
        st = self.status()
        self.assertIn("- [S] Application Design — skipped: one endpoint", st)
        self.assertIn("- [S] Functional Design (app) — skipped: not needed for functional-design", st)
        self.assertIn("- Skipped: one endpoint", self.state(i))
        # the skip stops counting when the requirements grow to Size: large
        self.approve("REQUIREMENTS")
        self.assertEqual(self.write("src/app.py").returncode, 0)
        self.requirements(i, "large")
        self.approve("REQUIREMENTS")
        r = self.write("src/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (design)", r.stderr)
        self.assertIn("skipped, but requirements.md no longer says Size: small", self.status())

    def test_tool_stages_and_bad_arguments(self):
        self.intent()
        for sid, by in (("build-and-test", "verify"), ("release", "release")):
            for args in (["start"], ["done", "--note", "x"]):
                p = self.tool("stage", args[0], sid, *args[1:])
                self.assertEqual(p.returncode, 1, (sid, args))
                self.assertIn("is recorded by `python3 .kiro/aidlc-lean/aidlc_lean.py %s`" % by, p.stdout)
        for args, msg in ((["start", "design"], "unknown stage design"),
                          (["start", "requirements", "--unit", "api"], "not a per-unit stage"),
                          (["start", "functional-design", "--unit", "api"], "unknown unit api"),
                          (["start", "user-stories", "--note", "x"], "unexpected argument: --note"),
                          (["done", "user-stories", "--reason", "x"], "unexpected argument: --reason"),
                          (["skip", "user-stories", "--reason"], "--reason needs a value"),
                          (["finish", "requirements"], "usage: stage start <id>"), ([], "usage: stage start <id>")):
            p = self.tool("stage", *args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn(msg, p.stdout, args)
        self.ok("stage", "skip", "user-stories", "--reason=single persona")  # --name=value works too
        self.assertIn("- [S] User Stories — skipped: single persona", self.status())

    def test_request_kinds(self):
        i = self.intent()
        for args, msg in ((["SPEC"], "There is no SPEC any more"), (["DESIGN"], "does not exist yet"),
                          (["RELEASE"], "does not exist yet"), (["PLAN"], "no code-generation plan yet"),
                          (["REQUIREMENTS", "--unit", "app"], "--unit goes with PLAN only"),
                          (["CR-x-1"], "there is no CR-x-1 file"), (["BOGUS"], "unknown kind BOGUS")):
            p = self.tool("request", *args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn(msg, p.stdout, args)
        p = self.ok("request", "requirements")  # kinds are not case-sensitive
        self.assertIn("approve REQUIREMENTS %s" % self.sha(self.req_path(i))[:8], p.stdout)
        self.assertEqual(self.events("APPROVAL_REQUESTED")[-1]["data"],
                         {"kind": "REQUIREMENTS", "path": self.req_path(i), "sha256": self.sha(self.req_path(i))})


class Units(V02):
    def test_units_come_from_the_first_column_of_unit_of_work(self):
        i = self.intent()
        self.ok("stage", "start", "units")  # still the template: the only unit is app
        self.ok("stage", "start", "functional-design")
        self.assertTrue(self.exists(self.ipath(i, "construction/app/functional-design/functional-design.md")))
        self.units(i, [("api", "payments", "`src/api/**`"), ("**web**", "web", "src/web"),
                       ("Catalog Service", "x", "src/c"), ("plans", "x", "y"), ("<unit>", "", ""), ("", "", "")])
        p = self.tool("stage", "start", "nfr-design")
        self.assertEqual(p.returncode, 1)
        self.assertIn("nfr-design is per unit: add --unit with one of api, web.", p.stdout)
        self.assertIn("ignored names in unit-of-work.md: Catalog Service, plans", p.stdout)
        self.ok("stage", "start", "nfr-design", "--unit", "web")
        self.assertTrue(self.exists(self.ipath(i, "construction/web/nfr-design/nfr-design.md")))
        p = self.tool("stage", "start", "nfr-design", "--unit", "app")
        self.assertEqual(p.returncode, 1)
        self.assertIn("unknown unit app. Units: api, web (unit-of-work.md)", p.stdout)
        st = self.status()
        self.assertIn("unit-of-work.md: ignored unit names that cannot be folder names: Catalog Service, plans", st)
        self.assertIn("- [ ] NFR Requirements + Design (api)\n", st)
        self.assertIn("- [-] NFR Requirements + Design (web) — in progress", st)
        self.assertIn("- [ ] Code Generation (api)\n", st)
        self.assertNotIn("Functional Design (app)", st)
        p = self.ok("stage", "done", "units", "--note", "two units")
        self.assertIn("Units: api, web; ignored (not usable as folder names): Catalog Service, plans", p.stdout)
        self.assertNotIn("Multi-team", self.ok("new", "other").stdout)


class Inception(V02):
    def setUp(self):
        super().setUp()
        self.i = self.intent()
        self.requirements(self.i, "large")
        self.ok("stage", "start", "application-design")
        self.design(self.i)
        self.req, self.des = self.req_path(self.i), self.ipath(self.i, DESIGN)

    def combined(self, *paths):
        blobs = []
        for p in paths or (self.req, self.des):
            with open(os.path.join(self.dir, p), "rb") as f:
                blobs.append(f.read())
        return hashlib.sha256(b"\0".join(blobs)).hexdigest()

    def test_one_approval_covers_requirements_and_design(self):
        p = self.ok("request", "INCEPTION")
        h = self.combined()[:8]
        self.assertIn("approve INCEPTION %s" % h, p.stdout)
        self.assertIn("read %s and %s" % (self.req, self.des), p.stdout)
        st = self.status()
        self.assertIn("- [A] Requirements Analysis — waiting for approval: approve INCEPTION %s" % h, st)
        self.assertIn("- [A] Application Design — waiting for approval: approve INCEPTION %s" % h, st)
        out = self.say("approve INCEPTION %s" % h)
        self.assertIn("Recorded: INCEPTION approved (sha %s) by dev@example.com: %s and %s." % (h, REQ, DESIGN),
                      out.stdout)
        d = self.events("APPROVED")[-1]["data"]
        self.assertEqual(d["sha256"], self.combined())
        self.assertEqual(d["files"], {self.req: self.sha(self.req), self.des: self.sha(self.des)})
        self.assertEqual(d["paths"], [self.req, self.des])
        self.assertNotIn("path", d)
        self.assertIn("protected_baseline", d)
        st = self.status()
        self.assertIn("- [x] Requirements Analysis — approved via INCEPTION (sha %s)" % h, st)
        self.assertIn("- [x] Application Design — approved via INCEPTION (sha %s)" % h, st)
        self.assertIn("- [x] Application Design — approved via INCEPTION", self.state(self.i))  # hook regenerated it
        self.assertEqual(self.write("src/app.py").returncode, 0)

    def test_each_file_goes_stale_on_its_own(self):
        _, h = self.approve("INCEPTION")
        self.design(self.i, extra="\n## Data model\n- orders\n")
        st = self.status()
        self.assertIn("- [x] Requirements Analysis — approved via INCEPTION (sha %s)" % h, st)
        self.assertIn("- [-] Application Design — stale: changed since it was approved via INCEPTION (sha %s)" % h, st)
        self.assertEqual(self.write("src/app.py").returncode, 0)  # standard mode: a stale approval still counts
        self.cfg(regulated=True)
        r = self.write("src/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (design)", r.stderr)
        self.assertIn("is stale", r.stderr)
        out, h2 = self.approve("DESIGN")  # the design alone, with the hash regulated mode wants
        self.assertIn("Recorded: DESIGN approved (sha %s)" % h2, out.stdout)
        self.assertEqual(h2, self.sha(self.des)[:8])
        self.assertIn("- [x] Application Design — approved via DESIGN (sha %s)" % h2, self.status())
        r = self.write("src/app.py")  # requirements and design are fine now; regulated mode wants a plan next
        self.assertIn("blocked (plan)", r.stderr)
        self.put(self.req, self.read(self.req) + "\nscope grew\n")
        r = self.write("src/app.py")
        self.assertIn("blocked (requirements)", r.stderr)
        self.assertIn("is stale", r.stderr)

    def test_without_a_design_inception_covers_the_requirements_only(self):
        os.remove(os.path.join(self.dir, self.des))
        p = self.ok("request", "INCEPTION")
        h = self.combined(self.req)[:8]
        self.assertEqual(h, self.sha(self.req)[:8])
        self.assertIn("read %s and" % self.req, p.stdout + " and")
        self.assertNotIn(DESIGN, p.stdout)
        self.say("approve INCEPTION %s" % h)
        self.assertEqual(self.events("APPROVED")[-1]["data"]["files"], {self.req: self.sha(self.req)})
        st = self.status()
        self.assertIn("- [x] Requirements Analysis — approved via INCEPTION (sha %s)" % h, st)
        self.assertIn("- [-] Application Design — in progress", st)  # started, but its file is gone
        r = self.write("src/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (design)", r.stderr)

    def test_a_request_goes_out_of_date_when_either_file_changes(self):
        h = self.request_hash("INCEPTION")
        self.design(self.i, extra="\n## Key decisions\n- D-1\n")
        st = self.status()  # the printed line no longer matches, so neither file waits on it
        self.assertNotIn("[A]", st)
        self.assertIn("- [-] Requirements Analysis — in progress", st)
        out = self.say("approve INCEPTION %s" % h)
        self.assertIn("NOT recorded: the file changed since that request", out.stdout)
        self.assertEqual(self.events("APPROVED"), [])
        h2 = self.request_hash("INCEPTION")
        self.assertNotEqual(h2, h)
        self.assertIn("- [A] Requirements Analysis — waiting for approval: approve INCEPTION %s" % h2, self.status())

    def test_reject_inception_rejects_both_files(self):
        out = self.say("reject INCEPTION: the data model is missing")
        self.assertIn("Recorded: INCEPTION rejected", out.stdout)
        self.assertEqual(sorted(self.events("REJECTED")[-1]["data"]["files"]), sorted([self.req, self.des]))
        st = self.status()
        self.assertIn("- [-] Requirements Analysis — rejected", st)
        self.assertIn("- [-] Application Design — rejected", st)
        self.assertIn("the data model is missing", st)
        self.assertIn("blocked (requirements)", self.write("src/app.py").stderr)

    def test_inception_approvers_need_every_list_it_covers(self):
        self.cfg(approvers={"DESIGN": ["architect@example.com"]})
        out, _ = self.approve("INCEPTION")
        self.assertIn("not in approvers for DESIGN", out.stdout)
        out, _ = self.approve("REQUIREMENTS")  # the design's list does not restrict the requirements alone
        self.assertIn("Recorded: REQUIREMENTS approved", out.stdout)


class PlanPerUnit(V02):
    flags = ["--regulated"]

    def setUp(self):
        super().setUp()
        self.i = self.intent()
        self.requirements(self.i, "large")
        self.ok("stage", "start", "application-design")
        self.design(self.i)
        self.units(self.i, [("api", "core", "src/api/**"), ("web", "core", "src/web/")])
        self.approve("INCEPTION")

    def plans(self, *units):
        for u in units:
            self.ok("stage", "start", "code-generation", "--unit", u)
            self.fill(self.ipath(self.i, PLAN % u), "\n- [ ] 1. walking skeleton for %s\n" % u)

    def test_each_unit_needs_its_own_approved_plan(self):
        r = self.write("src/api/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (plan)", r.stderr)
        self.assertIn("the code-generation plan of unit api", r.stderr)
        p = self.tool("stage", "start", "code-generation")
        self.assertEqual(p.returncode, 1)
        self.assertIn("add --unit with one of api, web", p.stdout)
        self.plans("api", "web")
        p = self.tool("request", "PLAN")
        self.assertEqual(p.returncode, 1)
        self.assertIn("several code-generation plans (api, web): use `request PLAN --unit <unit>`", p.stdout)
        out = self.say("approve PLAN")
        self.assertIn("Approval of PLAN NOT recorded", out.stdout)
        self.assertIn("several code-generation plans (api, web)", out.stdout)
        h = self.request_hash("PLAN", "--unit", "api")
        self.assertEqual(h, self.sha(self.ipath(self.i, PLAN % "api"))[:8])
        out = self.say("approve PLAN %s" % h)
        self.assertIn("Recorded: PLAN approved (sha %s) by dev@example.com: the code-generation plan of unit api." % h,
                      out.stdout)
        d = self.events("APPROVED")[-1]["data"]
        self.assertEqual((d["unit"], d["path"]), ("api", self.ipath(self.i, PLAN % "api")))
        self.assertEqual(self.write("src/api/app.py").returncode, 0)
        r = self.write("src/web/app.js")
        self.assertEqual(r.returncode, 2)
        self.assertIn("plan of unit web", r.stderr)
        r = self.write("src/shared/util.py")  # in no unit's paths: every plan must be approved
        self.assertEqual(r.returncode, 2)
        self.assertIn("in no unit's paths", r.stderr)
        st = self.status()
        self.assertIn("- [-] Code Generation (api) — plan approved (sha %s)" % h, st)
        self.assertIn("- [-] Code Generation (web) — plan in progress; it needs approval: `request PLAN --unit web`", st)
        self.approve("PLAN", "--unit", "web")
        self.assertEqual(self.write("src/web/app.js").returncode, 0)
        self.assertEqual(self.write("src/shared/util.py").returncode, 0)
        self.fill(self.ipath(self.i, PLAN % "api"), "- [ ] 2. refunds\n")  # edited after its approval
        r = self.write("src/api/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("is stale", r.stderr)
        self.assertEqual(self.write("src/web/app.js").returncode, 0)
        out = self.say("approve PLAN deadbeef")
        self.assertIn("no code-generation plan of %s has the hash deadbeef" % self.i, out.stdout)

    def test_no_plan_blocks_and_release_needs_every_plan(self):
        r = self.write("src/x.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("has no code-generation plan yet", r.stderr)
        self.cfg(checks=["true"])
        self.plans("api")
        self.approve("PLAN", "--unit", "api")
        self.ok("verify")
        r = self.tool("release")  # every unit of unit-of-work.md needs its plan, not only the plans that exist
        self.assertEqual(r.returncode, 1)
        self.assertIn("Not ready to release: the plan of unit web is missing", r.stdout)
        self.plans("web")
        r = self.tool("release")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Not ready to release: the plan of unit web is draft", r.stdout)
        self.approve("PLAN", "--unit", "web")
        api = self.ipath(self.i, PLAN % "api")
        self.put(api, self.read(api).replace("- [ ]", "- [x]"))  # every step of the api plan done
        self.commit_all()
        self.ok("release")  # ticked steps keep the plan approved for the release too
        self.ok("stage", "done", "code-generation", "--unit", "api", "--note", "steps 1-2 done, AC-1 tested")
        self.assertIn("- [x] Code Generation (api) — done", self.status())

    def test_ticking_steps_keeps_the_approval_and_editing_a_step_voids_it(self):
        path = self.ipath(self.i, PLAN % "api")
        self.ok("stage", "start", "code-generation", "--unit", "api")
        plan = ("# Code Generation Plan: api\n\n## Steps\n- [ ] 1. skeleton · covers: AC-1\n  * [ ] 1a. health check\n"
                "- [ ] 2. refunds · covers: AC-2\n\n## Tests\n| AC-1 | tests/test_api.py::test_refund | api |\n")
        self.put(path, plan)
        p = self.ok("request", "PLAN", "--unit", "api")
        self.assertIn("Ticking its steps keeps the approval; any other change to the file voids it.", p.stdout)
        h = re.search(r"approve PLAN ([0-9a-f]{8})", p.stdout).group(1)
        self.assertEqual(h, self.sha(path)[:8])  # nothing ticked yet: the file's own sha256
        ticked = plan.replace("- [ ] 1.", "- [x] 1.").replace("* [ ] 1a.", "* [X] 1a.")
        self.put(path, ticked)  # a tick while the request is out: the request still stands
        self.assertIn("- [A] Code Generation (api) — plan waiting for approval: approve PLAN %s" % h, self.status())
        self.assertIn("Recorded: PLAN approved (sha %s)" % h, self.say("approve PLAN %s" % h).stdout)
        for text in (ticked, plan, ticked):  # ticked, unticked, ticked again
            self.put(path, text)
            self.assertEqual(self.write("src/api/app.py").returncode, 0)
        self.assertRegex(self.status(), r"- \[-\] Code Generation \(api\) — plan approved \(sha %s\) · "
                                        r"\d{4}-\d{2}-\d{2}; code in progress" % h)
        edited = ticked.replace("2. refunds", "2. refunds and partial refunds")  # a step's text
        for text in (edited, ticked + "- [ ] 3. a step added later\n", ticked.replace("test_refund", "test_x")):
            self.put(path, text)
            r = self.write("src/api/app.py")
            self.assertEqual(r.returncode, 2, text)
            self.assertIn("is stale. It changed after its approval (ticking steps does not count, editing a step's "
                          "text does)", r.stderr)
            self.assertIn("- [-] Code Generation (api) — plan stale: changed since it was approved", self.status())
        self.put(path, edited)
        h2 = self.request_hash("PLAN", "--unit", "api")  # the hash of the plan with its boxes unticked
        unticked = edited.replace("[x]", "[ ]").replace("[X]", "[ ]")
        self.assertEqual(h2, hashlib.sha256(unticked.encode()).hexdigest()[:8])
        out = self.say("approve PLAN %s" % h2)
        self.assertIn("Recorded: PLAN approved (sha %s)" % h2, out.stdout)
        self.assertEqual(self.events("APPROVED")[-1]["data"]["sha256"], hashlib.sha256(unticked.encode()).hexdigest())
        self.assertEqual(self.write("src/api/app.py").returncode, 0)
        out = self.say("reject PLAN %s: add a rollback step" % h2)  # the hash names the ticked plan
        self.assertIn("Recorded: PLAN rejected by the human: the code-generation plan of unit api", out.stdout)
        self.assertEqual(self.events("REJECTED")[-1]["data"]["unit"], "api")
        self.assertEqual(self.write("src/api/app.py").returncode, 2)

    def test_reject_names_the_plan_by_hash_or_the_last_request(self):
        self.plans("api", "web")
        h_web = self.request_hash("PLAN", "--unit", "web")
        p = self.tool("request", "PLAN", "--unit", "web")
        self.assertIn("or `reject PLAN %s <reason>`" % h_web, p.stdout)
        self.request_hash("PLAN", "--unit", "api")
        out = self.say("reject PLAN %s: it needs a rollback step" % h_web)
        self.assertIn("Recorded: PLAN rejected", out.stdout)
        self.assertEqual(self.events("REJECTED")[-1]["data"]["unit"], "web")
        out = self.say("reject PLAN: too big")  # no hash: the plan requested last
        self.assertIn("Recorded: PLAN rejected", out.stdout)
        self.assertEqual(self.events("REJECTED")[-1]["data"]["unit"], "api")
        st = self.status()
        self.assertIn("- [-] Code Generation (api) — plan rejected", st)
        self.assertIn("- [-] Code Generation (web) — plan rejected", st)


class PlanInStandardMode(V02):
    def test_plans_are_optional_and_an_approval_names_its_plan(self):
        i = self.ready()
        self.units(i, [("api", "core", "src/api/**"), ("web", "core", "src/web/**")])
        self.assertEqual(self.write("src/api/app.py").returncode, 0)  # no PLAN approval needed in standard mode
        self.ok("stage", "start", "code-generation", "--unit", "api")
        out = self.say("approve PLAN")  # one plan: no hash needed in standard mode
        self.assertIn("Recorded: PLAN approved", out.stdout)
        self.ok("stage", "start", "code-generation", "--unit", "web")
        out = self.say("approve PLAN")
        self.assertIn("NOT recorded", out.stdout)
        self.assertIn("several code-generation plans (api, web): type the approval line with the hash", out.stdout)
        h = self.request_hash("PLAN", "--unit", "web")
        self.assertIn("unit web", self.say("approve PLAN %s" % h).stdout)


RELEASED_LINE = ("  RELEASED: RELEASE is approved, so this intent is closed. New work needs a new intent: "
                 "`python3 .kiro/aidlc-lean/aidlc_lean.py new <slug>`.")


class ReleasedIntent(V02):
    def release(self):
        """A new intent taken through verify, `release` and the RELEASE approval: (intent, RELEASE hash)."""
        self.cfg(checks=["true"])
        i = self.ready()
        if self.flags == ["--regulated"]:
            self.ok("stage", "start", "code-generation")
            self.approve("PLAN")
        self.ok("verify")
        self.commit_all()
        self.ok("release")
        self.assertRegex(self.status(), r"- \[-\] Release — release\.md written · \d{4}-\d{2}-\d{2}; fill in Open items")
        self.assertEqual(self.events("STAGE_STARTED")[-1]["data"]["stage"], "release")
        self.assertEqual(self.write("src/app.py").returncode, 0)  # not released until the human approves
        out, h = self.approve("RELEASE")
        self.assertIn("Recorded: RELEASE approved", out.stdout)
        self.assertIn("- [x] Release — released: approved (sha %s)" % h, self.state(i))
        return i, h

    def assert_closed_record(self, i):
        """Status and the session context say so; the stage commands and `release` refuse the intent."""
        for text in (self.status(), self.hook("SessionStart", {}).stdout):
            self.assertIn("Active intent: aidlc-docs/%s (feature x)\n%s\n" % (i, RELEASED_LINE), text)
            # v0.3: Operations stages without a record are offered (guidance only; the intent stays released)
            self.assertIn("Next: optional: record deployment and operations (skill aidlc-lean-operations) or `python3 "
                          ".kiro/aidlc-lean/aidlc_lean.py stage skip operations --reason ...`; the intent stays released. "
                          "New work: `python3 .kiro/aidlc-lean/aidlc_lean.py new <slug>`; ", text)
        for args in (["start", "user-stories"], ["done", "code-generation", "--note", "more"],
                     ["skip", "user-stories", "--reason", "late"]):
            p = self.tool("stage", *args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn("%s is released (RELEASE approved); its record is closed." % i, p.stdout)
        p = self.tool("release")
        self.assertEqual(p.returncode, 1)
        self.assertIn("already released", p.stdout)


class Released(ReleasedIntent):
    def test_a_released_intent_closes_its_record_and_code_goes_as_with_no_intent(self):
        i, _ = self.release()
        counters = self.read(".aidlc-lean/counters.json")
        blocked = len(self.events("BLOCKED"))
        r = self.write("src/app.py")  # standard mode: small edits work as without an active intent
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.events("BLOCKED")), blocked)
        self.assertEqual(self.read(".aidlc-lean/counters.json"), counters)  # not counted for its aidlc-state.md
        self.assertIn("New work: `python3 .kiro/aidlc-lean/aidlc_lean.py new <slug>`; small edits need no intent\n",
                      self.status())
        self.assert_closed_record(i)
        summary = self.read(self.ipath(i, SUMMARY))
        verifies = len(self.events("VERIFY"))
        p = self.ok("verify")  # still logged for the commit gate, but not filed under the released intent
        self.assertIn("is released, so its build-and-test summary was left as it is", p.stdout)
        self.assertEqual(self.read(self.ipath(i, SUMMARY)), summary)
        self.assertEqual(len(self.events("VERIFY")), verifies + 1)
        self.assertIsNone(self.events("VERIFY")[-1]["intent"])
        self.fill(self.ipath(i, "operations/release.md"), "\n- follow-up: tax rules\n")  # does not reopen it
        self.assertIn(RELEASED_LINE, self.status())
        self.intent("follow-up")  # a new intent has its own gates
        r = self.write("src/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (requirements)", r.stderr)


class ReleasedRegulated(ReleasedIntent):
    flags = ["--regulated"]

    def test_a_released_intent_blocks_code_until_a_new_intent_is_active(self):
        i, _ = self.release()
        r = self.write("src/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (released): %s is released (RELEASE approved). Start follow-ups and fixes as a new "
                      "intent: `python3 .kiro/aidlc-lean/aidlc_lean.py new <slug>`." % i, r.stderr)
        self.assertEqual(self.events("BLOCKED")[-1]["data"]["gate"], "released")
        self.assertIn("New work: `python3 .kiro/aidlc-lean/aidlc_lean.py new <slug>`; regulated mode blocks code until "
                      "then\n", self.status())
        self.assert_closed_record(i)
        j = self.ready("follow-up")  # a new intent: its own gates, here the plan of its unit
        r = self.write("src/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (plan)", r.stderr)
        self.assertNotIn(RELEASED_LINE, self.status())
        self.assertIn("Active intent: aidlc-docs/%s" % j, self.status())


class StateDoc(V02):
    def test_only_the_generated_region_changes(self):
        i = self.intent()
        path = self.ipath(i, "aidlc-state.md")
        head = "# AI-DLC State: refunds\nIntent: %s · Mode: standard · Created: 2026-11-08\n" % i
        notes = ("## Session notes\nStatus: inception, waiting on tax rules\n### Next\n1. Ask finance about VAT\n"
                 "### Notes for the next session\n- keep <b>this</b> exactly as it is  \n")
        self.put(path, head + BEGIN + "\nold generated text\n" + END + "\n" + notes)
        self.ok("stage", "skip", "user-stories", "--reason", "single persona")
        text = self.read(path)
        self.assertTrue(text.startswith(head + BEGIN + "\n## Stage progress\n"), text)
        self.assertTrue(text.endswith(END + "\n" + notes), text)
        self.assertNotIn("old generated text", text)
        self.assertIn("- [S] User Stories — skipped: single persona", text)
        self.assertIn("\n## Stage log\n", text)
        self.assertIn("- Skipped: single persona", text)
        h = self.request_hash("REQUIREMENTS")  # a request shows as waiting for approval
        self.assertIn("- [A] Requirements Analysis — waiting for approval: approve REQUIREMENTS %s" % h, self.read(path))
        self.say("approve REQUIREMENTS %s" % h)  # an approval recorded by the hook regenerates it too
        text = self.read(path)
        self.assertIn("- [x] Requirements Analysis — approved via REQUIREMENTS (sha %s)" % h, text)
        self.assertTrue(text.endswith(END + "\n" + notes))
        notes2 = notes.replace("Ask finance about VAT", "Write the refund endpoint")  # the agent's own edit
        self.put(path, text.replace(notes, notes2))
        self.ok("stage", "skip", "reverse-engineering", "--reason", "greenfield")
        text = self.read(path)
        self.assertTrue(text.endswith(END + "\n" + notes2))
        self.assertIn("1. Write the refund endpoint", self.status())
        self.assertEqual((text.count(BEGIN), text.count(END)), (1, 1))

    def test_without_markers_the_region_goes_after_the_header(self):
        i = self.intent()
        path = self.ipath(i, "aidlc-state.md")
        head = "# AI-DLC State: refunds\nIntent: %s · Created: 2026-11-08\n" % i
        rest = "\n## Session notes\nStatus: x\n### Next\n1. y\n"
        self.put(path, head + rest)
        self.ok("stage", "skip", "user-stories", "--reason", "single persona")
        text = self.read(path)
        self.assertTrue(text.startswith(head + BEGIN + "\n## Stage progress\n"), text)
        self.assertTrue(text.endswith(END + "\n" + rest), text)
        self.ok("stage", "skip", "reverse-engineering", "--reason", "greenfield")
        text = self.read(path)
        self.assertEqual((text.count(BEGIN), text.count(END)), (1, 1))
        self.assertTrue(text.endswith(END + "\n" + rest))
        self.put(path, "Status: no title at all\n" + END + "\n")  # no header, a stray marker: the region goes on top
        self.ok("stage", "start", "user-stories")
        text = self.read(path)
        self.assertTrue(text.startswith(BEGIN + "\n## Stage progress\n"), text)
        self.assertTrue(text.endswith(END + "\nStatus: no title at all\n\n"), text)
        self.assertEqual((text.count(BEGIN), text.count(END)), (1, 1))
        os.remove(os.path.join(self.dir, path))  # deleted: written again from the template
        self.ok("stage", "skip", "user-stories", "--reason", "single persona")
        self.assertIn("- [S] User Stories — skipped: single persona", self.read(path))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root writes anywhere")
    def test_a_page_that_cannot_be_written_does_not_lose_the_record(self):
        i = self.intent()
        folder = os.path.join(self.dir, DOCS, i)
        os.chmod(folder, 0o555)  # nothing can be created in the intent folder, so the page cannot be replaced
        self.addCleanup(os.chmod, folder, 0o755)
        p = self.ok("request", "REQUIREMENTS")
        h = self.sha(self.req_path(i))[:8]
        self.assertIn("approve REQUIREMENTS %s" % h, p.stdout)
        self.assertIn("Could not update aidlc-state.md (PermissionError", p.stdout)
        out = self.say("approve REQUIREMENTS %s" % h)
        self.assertIn("Recorded: REQUIREMENTS approved", out.stdout)
        self.assertIn("[AI-DLC Lean] Could not update aidlc-state.md", out.stdout)
        os.chmod(folder, 0o755)
        self.ok("stage", "skip", "user-stories", "--reason", "single persona")  # the next command catches up
        self.assertIn("- [x] Requirements Analysis — approved via REQUIREMENTS (sha %s)" % h, self.state(i))

    def test_a_note_cannot_break_the_region_or_feed_the_next_items(self):
        i = self.intent()
        self.ok("stage", "start", "user-stories")
        self.fill(self.ipath(i, "inception/user-stories/stories.md"))
        self.ok("stage", "done", "user-stories", "--note", "line one\n%s\n### Next\n1. injected item" % END)
        text = self.state(i)
        self.assertEqual((text.count(BEGIN), text.count(END)), (1, 1))
        self.assertIn("- Did: line one < !-- lean:end progress -- > ### Next 1. injected item", text)
        self.assertNotIn("    injected item", self.hook("SessionStart", {}).stdout)


class BuildAndTest(V02):
    def test_verify_writes_the_summary_and_records_the_stage(self):
        self.cfg(checks=["true", sys.executable + " -c \"print('ok | fine')\""])
        i = self.ready()
        self.assertIn("- [ ] Build and Test\n", self.status())
        summary = self.ipath(i, SUMMARY)
        v = self.ok("verify")
        self.assertIn("verify: PASS — summary %s" % summary, v.stdout)
        text = self.read(summary)
        ev = self.events("VERIFY")[-1]
        for s in ("# Build and Test Summary: feature x", "- result: PASS", "- code fingerprint: %s" % ev["data"]["fingerprint"],
                  "| 1 | `true` | 0 |", "print('ok \\| fine')", "## Protected files", "- none configured"):
            self.assertIn(s, text)
        self.assertEqual((ev["intent"], ev["data"]["summary"], ev["data"]["summary_sha256"]), (i, summary, self.sha(summary)))
        done = [e for e in self.events("STAGE_COMPLETED") if e["data"]["stage"] == "build-and-test"]
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["data"]["fingerprint"], ev["data"]["fingerprint"])
        self.assertEqual(done[0]["data"]["outputs"], {summary: self.sha(summary)})
        # no unit's code generation is recorded yet: the PASS covers part of the code
        self.assertIn("- [-] Build and Test — verify PASS on partial code", self.status())
        self.ok("stage", "start", "code-generation")
        self.put(self.ipath(i, PLAN % "app"), "# Plan\n- [x] 1. skeleton\n")
        self.ok("stage", "done", "code-generation", "--note", "skeleton done")
        self.assertIn("- [x] Build and Test — verify PASS", self.status())
        self.assertIn("- Did: verify PASS: 2 checks on code fingerprint %s" % ev["data"]["fingerprint"][:8], self.state(i))
        self.put("src/app.py", "x = 2\n")
        self.assertIn("- [-] Build and Test — code changed since the last verify PASS", self.status())
        self.ok("verify")
        self.assertEqual(self.state(i).count("### Build and Test · "), 1)  # the log keeps only the latest run
        self.cfg(checks=["false"])
        self.assertEqual(self.tool("verify").returncode, 1)
        self.assertIn("- [-] Build and Test — last verify FAILED", self.status())
        self.assertIn("- result: FAIL", self.read(summary))
        self.assertEqual(len([e for e in self.events("STAGE_COMPLETED") if e["data"]["stage"] == "build-and-test"]), 2)

    def test_without_an_intent_verify_writes_no_summary(self):
        self.cfg(checks=["true"])
        v = self.ok("verify")
        self.assertEqual(v.stdout.strip().splitlines()[-1], "verify: PASS")
        self.assertIsNone(self.events("VERIFY")[-1]["data"].get("summary"))


class NextStep(V02):
    def test_next_walks_the_stage_sequence(self):
        lean = "`python3 .kiro/aidlc-lean/aidlc_lean.py "
        self.cfg(checks=["true"])
        i = self.intent()
        self.requirements(i, "large")
        self.assertIn("Next: finish requirements.md and the application design", self.status())
        self.assertIn("then %srequest INCEPTION`" % lean, self.status())
        self.requirements(i, "small")
        self.assertIn("Next: finish requirements.md, then %srequest REQUIREMENTS`" % lean, self.status())
        self.approve("REQUIREMENTS")
        self.assertIn("or skip it with %sstage skip application-design" % lean, self.status())
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        # Inception is finished first: its stages without a record come before Construction
        self.assertIn("Next: record the Inception stages that have no record yet: Reverse Engineering, User Stories, "
                      "Units Generation (%sstage done <id> --note ...` once the page is written, or `stage skip <id> "
                      "--reason ...`)" % lean, self.status())
        for sid in ("reverse-engineering", "user-stories", "units"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        # then Construction, unit by unit: the unit's design stages, its plan, its code
        self.assertIn("Next: unit app: record its design stages first: Functional Design, NFR Requirements + Design, "
                      "Infrastructure Design (%sstage start <id> --unit app`" % lean, self.status())
        self.ok("stage", "skip", "functional-design", "--reason", "simple logic")
        self.assertIn("record its design stages first: NFR Requirements + Design, Infrastructure Design (", self.status())
        for sid in ("nfr-design", "infrastructure-design"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.assertIn("Next: write the code-generation plan of unit app: %sstage start code-generation --unit app` "
                      "(skill aidlc-lean-construction), then build in small steps following it" % lean, self.status())
        self.ok("stage", "start", "code-generation")
        plan = self.ipath(i, PLAN % "app")
        self.put(plan, "# Plan\n\n## Steps\n- [ ] 1. skeleton · covers: AC-1\n- [ ] 2. refunds · covers: AC-2\n")
        self.assertIn("Next: continue the code-generation plan of unit app: step 1 of 2 (1. skeleton · covers: AC-1)",
                      self.status())
        self.ok("verify")  # a PASS mid-plan does not finish the unit
        self.assertIn("Next: continue the code-generation plan of unit app: step 1 of 2", self.status())
        self.put(plan, self.read(plan).replace("- [ ]", "- [x]"))
        self.assertIn("Next: record the stages that have no record yet (%sstage done <id> --note ...` or `stage skip "
                      "<id> --reason ...`): Code Generation (app); then review" % lean, self.status())
        self.ok("stage", "done", "code-generation", "--note", "steps 1-2 done; AC-1 -> tests/test_refund.py")
        self.assertIn("Next: review in a new chat or by a subagent that did not write the code, then %srelease`" % lean,
                      self.status())
        self.commit_all()
        self.ok("release")
        self.assertIn("Next: fill in Open items in operations/release.md, then %srequest RELEASE`" % lean, self.status())
        h = self.request_hash("RELEASE")  # a request that is out: wait, do not redo the work
        self.assertIn("Next: wait for the human to type `approve RELEASE %s`" % h, self.status())
        self.put("src/late.py", "x = 1\n")  # the code changed after `release`: verify, then release again
        self.assertIn("Next: run %sverify` and get it green" % lean, self.status())
        self.ok("verify")
        self.assertIn("Next: review in a new chat or by a subagent that did not write the code, then %srelease` again "
                      "(the code changed since it wrote release.md)" % lean, self.status())

    def test_next_waits_for_a_request_that_is_out_and_goes_unit_by_unit(self):
        lean = "`python3 .kiro/aidlc-lean/aidlc_lean.py "
        self.cfg(checks=["true"], regulated=True)
        i = self.intent()
        self.requirements(i, "large")
        self.design(i)
        h = self.request_hash("INCEPTION")
        self.assertIn("Next: wait for the human to type `approve INCEPTION %s`" % h, self.status())
        self.fill(self.ipath(i, DESIGN))  # an edit voids the request: finish and request again
        self.assertIn("Next: finish requirements.md and the application design, then %srequest INCEPTION`" % lean,
                      self.status())
        self.approve("INCEPTION")
        for sid in ("reverse-engineering", "user-stories"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.ok("stage", "start", "units")
        self.units(i, [("api", "shop", "services/api/"), ("web", "shop", "web/")])
        self.ok("stage", "done", "units", "--note", "api and web")
        self.assertIn("Next: unit api: record its design stages first", self.status())
        for sid in ("functional-design", "nfr-design", "infrastructure-design"):
            self.ok("stage", "skip", sid, "--unit", "api", "--reason", "not needed")
        self.assertIn("Next: write the code-generation plan of unit api: %sstage start code-generation --unit api` "
                      "(skill aidlc-lean-construction), then `request PLAN --unit api` and wait" % lean, self.status())
        self.ok("stage", "start", "code-generation", "--unit", "api")
        self.fill(self.ipath(i, PLAN % "api"))
        self.assertIn("Next: finish the code-generation plan of unit api, then %srequest PLAN --unit api`" % lean,
                      self.status())
        h = self.request_hash("PLAN", "--unit", "api")
        self.assertIn("Next: wait for the human to type `approve PLAN %s`" % h, self.status())
        r = self.write("services/api/x.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("The request is out: wait for the human to type `approve PLAN %s`, then write its code." % h,
                      r.stderr)
        self.say("approve PLAN %s" % h)
        self.assertIn("Next: continue the code-generation plan of unit api: step 1 of 2", self.status())
        self.fill(self.ipath(i, PLAN % "api"), "- [x] 3. a step added later\n")  # a new step is an edit
        r = self.write("services/api/x.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("is stale. It changed after its approval (ticking steps does not count, editing a step's text "
                      "does)", r.stderr)
        self.say("approve PLAN %s" % self.request_hash("PLAN", "--unit", "api"))
        api_plan = self.ipath(i, PLAN % "api")
        self.put(api_plan, self.read(api_plan).replace("- [ ]", "- [x]"))  # every step done (ticking keeps it)
        self.ok("stage", "done", "code-generation", "--unit", "api", "--note", "api built")
        self.assertIn("Next: unit web: record its design stages first", self.status())  # the next unit
        st = self.status()  # the per-unit stages come unit by unit, as in AI-DLC's per-unit loop
        order = [st.index("- [%s] %s (%s)" % (m, n, u)) for m, n, u in (
            ("S", "Functional Design", "api"), ("S", "Infrastructure Design", "api"), ("x", "Code Generation", "api"),
            (" ", "Functional Design", "web"), (" ", "Code Generation", "web"))]
        self.assertEqual(order, sorted(order))


class AuditPack(V02):
    def test_audit_md_holds_the_stage_record(self):
        self.cfg(checks=["true"])
        i = self.ready()
        self.ok("stage", "skip", "user-stories", "--reason", "single persona")
        self.ok("verify")
        p = self.ok("audit", "pack")
        self.assertIn("Wrote %s (ledger OK)." % self.ipath(i, "audit.md"), p.stdout)
        text = self.read(self.ipath(i, "audit.md"))
        self.assertTrue(text.startswith("# Audit trail: %s\n" % i))
        for s in ("## Ledger integrity", "## Stages (", "## Approvals and rejections (", "## Verification runs (1)",
                  "intent created: feature x", "Requirements Analysis started", "User Stories skipped — single persona",
                  "Application Design skipped — one endpoint", "Build and Test done — verify PASS",
                  "REQUIREMENTS %s" % self.req_path(i)):
            self.assertIn(s, text)
        self.intent("second")  # two intents and none active: the pack covers all of them
        os.remove(os.path.join(self.dir, ".aidlc-lean", "active.json"))
        p = self.ok("audit", "pack")
        self.assertIn("Wrote aidlc-docs/audit.md", p.stdout)
        self.assertTrue(self.read("aidlc-docs/audit.md").startswith("# Audit trail: all intents\n"))
        self.assertNotIn("audit.md", self.tool("use", "audit.md").stdout.replace("Pick one of", ""))


class ToolRecords(V02):
    def test_the_agent_cannot_write_what_the_tool_writes(self):
        self.cfg(checks=["true"], regulated=True)
        i = self.intent()
        self.ok("verify")
        self.ok("audit", "pack")
        summary = self.ipath(i, SUMMARY)
        evidence = os.listdir(os.path.join(self.dir, self.ipath(i, "construction/build-and-test/evidence")))[0]
        for p in (summary, self.ipath(i, "construction/build-and-test/evidence/" + evidence),
                  self.ipath(i, "construction/build-and-test/evidence/new.md"), self.ipath(i, "audit.md"),
                  "aidlc-docs/audit.md"):
            r = self.write(p)
            self.assertEqual(r.returncode, 2, p)
            self.assertIn("blocked (records)", r.stderr)
            self.assertIn("is written by the AI-DLC Lean tool", r.stderr)
        for c in ("echo PASS > %s" % summary, "sed -i '' s/FAIL/PASS/ %s" % summary,
                  "rm -rf aidlc-docs/%s/construction/build-and-test/evidence" % i, "cp /tmp/x aidlc-docs/%s/audit.md" % i,
                  "rm aidlc-docs/audit.md", "rm -r aidlc-docs/%s/construction/build-and-test" % i):
            r = self.bash(c)
            self.assertEqual(r.returncode, 2, c)
            self.assertIn("blocked (records)", r.stderr)
        for c in ("cat %s" % summary, "grep PASS aidlc-docs/%s/audit.md" % i, "cat aidlc-docs/audit.md", "git add -A",
                  "cp /tmp/x aidlc-docs/%s/audit.md.bak" % i,
                  "echo ok > aidlc-docs/%s/construction/build-and-test/review.md" % i):
            self.assertEqual(self.bash(c).returncode, 0, c)
        for p in ("operations/release.md", "construction/build-and-test/review.md",  # what the agent writes next to them
                  "construction/build-and-test/build-instructions.md", "aidlc-state.md", "construction/notes/audit.md"):
            self.assertEqual(self.write(self.ipath(i, p), "x\n").returncode, 0, p)
        self.assertIn("- result: PASS", self.read(summary))  # the tool still writes them


class NotesNamingRecords(V02):
    def test_a_note_may_name_record_paths_and_the_rest_of_the_command_is_still_checked(self):
        lean = "python3 .kiro/aidlc-lean/aidlc_lean.py"
        self.intent()
        for c in (lean + ' stage done requirements --note "checked aidlc-docs/lean.json and .aidlc-lean/ state"',
                  lean + " stage skip user-stories --reason 'the trail is in aidlc-docs/audit/; nothing else'",
                  lean + " stage done units --note=aidlc-docs/lean.json",
                  lean + ' stage done units --note="the aidlc_lean.py hook entry | cp x .kiro/hooks/" && git status',
                  lean + " stage done units --note 'rm -rf aidlc-docs/x/construction/build-and-test/evidence'",
                  lean + " cr new x --owner payments --paths aidlc-docs/contracts/payments/api.yaml "
                         "--title 'see aidlc-docs/lean.json'"):
            r = self.bash(c)
            self.assertEqual(r.returncode, 0, (c, r.stderr))
        for c in (lean + ' stage done requirements --note "aidlc-docs/lean.json" && echo x > aidlc-docs/lean.json',
                  lean + ' stage done requirements --note "x"; rm .kiro/hooks/aidlc-lean-guard.json',
                  lean + ' stage done requirements --note "x" > aidlc-docs/lean.json',
                  lean + " stage done requirements --note >> .aidlc-lean/turn.json",
                  lean + ' stage done requirements --note "$(cat aidlc-docs/lean.json)"',
                  lean + " cr new x --owner payments --paths aidlc-docs/lean.json",
                  lean + " stage done units --note aidlc-docs/lean.json",  # unquoted: only "..." '...' and --note=
                  lean + " new x --title 'aidlc-docs/lean.json'",  # only stage and cr
                  "echo " + lean + " stage done units --note 'x' > aidlc-docs/lean.json"):
            r = self.bash(c)
            self.assertEqual(r.returncode, 2, c)
            self.assertIn("blocked (records)", r.stderr, c)


class MultiTeamUnits(V02):
    flags = ["--multi-team", "--team", "catalog"]

    def test_units_of_two_teams_and_a_change_request(self):
        self.put("aidlc-docs/contracts/OWNERS", "aidlc-docs/contracts/payments/** payments\n")
        self.put("aidlc-docs/contracts/payments/api.yaml", "openapi: 3.0.0\n")
        self.cfg(regulated=True)
        i = self.intent()
        self.requirements(i, "large")
        self.ok("stage", "start", "application-design")
        self.design(i)
        self.ok("stage", "start", "units")
        # the payments contract is part of the payments unit: it is code (v0.3), listed in that unit's Paths
        self.units(i, [("catalog", "catalog", "src/catalog/**"),
                       ("payments", "payments", "src/payments/**, aidlc-docs/contracts/payments/**")])
        p = self.ok("stage", "done", "units", "--note", "two units; they meet at the payments contract")
        self.assertIn("Units: catalog, payments", p.stdout)
        self.approve("INCEPTION")
        for u in ("catalog", "payments"):
            self.ok("stage", "start", "code-generation", "--unit", u)
        self.approve("PLAN", "--unit", "catalog")
        self.assertEqual(self.write("src/catalog/app.py").returncode, 0)
        r = self.write("src/payments/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("plan of unit payments", r.stderr)
        r = self.write("aidlc-docs/contracts/payments/api.yaml")  # the contract still needs a change request
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (contract)", r.stderr)
        self.assertIn("CR-catalog-1", self.ok("cr", "new", "refund-reason", "--owner", "payments", "--paths",
                                              "aidlc-docs/contracts/payments/api.yaml").stdout)
        out, _ = self.approve("CR-catalog-1")
        self.assertIn("needs someone from team payments", out.stdout)
        self.assertIn("waiting for your team: CR-catalog-1", self.tool("status", team="payments").stdout)
        out, _ = self.approve("CR-catalog-1", team="payments")
        self.assertIn("Recorded: CR-catalog-1 approved", out.stdout)
        self.assertEqual(self.events("APPROVED")[-1]["data"]["owner_team"], "payments")
        r = self.write("aidlc-docs/contracts/payments/api.yaml")  # unlocked; regulated: its unit's plan rules it
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (plan): the code-generation plan of unit payments", r.stderr)
        out, _ = self.approve("PLAN", "--unit", "payments", team="payments")  # in the payments clone
        self.assertIn("unit payments", out.stdout)
        self.assertEqual(self.events("APPROVED")[-1]["actor"]["team"], "payments")
        self.assertEqual(self.write("aidlc-docs/contracts/payments/api.yaml").returncode, 0)
        self.assertEqual(self.write("src/payments/app.py").returncode, 0)
        st = self.status()
        self.assertIn("- [x] Units Generation — done", st)
        self.assertIn("- [-] Code Generation (catalog) — plan approved", st)
        self.assertIn("- [-] Code Generation (payments) — plan approved", st)
        self.assertIn("by dev@example.com (team catalog)", self.state(i))
        p = self.ok("new", "next-thing")
        self.assertIn("Multi-team: list the units, their owner teams and paths in %s" % UNITS, p.stdout)


class Doctor(V02):
    def test_doctor_reports_v01_leftovers_and_missing_templates(self):
        self.assertNotIn("0.1", self.tool("doctor").stdout)
        self.put("aidlc/lean.json", "{}\n")
        os.remove(os.path.join(self.dir, ".kiro/aidlc-lean/templates/stories.md"))
        d = self.tool("doctor")
        self.assertEqual(d.returncode, 1)
        self.assertIn("found aidlc/ from AI-DLC Lean 0.1", d.stdout)
        self.assertIn("missing templates in .kiro/aidlc-lean/templates/: stories.md", d.stdout)
        self.cfg(contracts_dir="aidlc/contracts")
        self.assertIn("contracts_dir in aidlc-docs/lean.json is the 0.1 path", self.tool("doctor").stdout)
        i = self.intent()  # a missing template still gives a page with a header
        self.ok("stage", "start", "user-stories")
        self.assertTrue(self.read(self.ipath(i, "inception/user-stories/stories.md")).startswith(
            "# User Stories: feature x\n"))


if __name__ == "__main__":
    unittest.main()
