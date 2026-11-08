"""Integration checks for AI-DLC Lean v0.2: the texts the agent reads match what the tool does.

KitTexts reads the shipped files only: word caps, and every command, stage id, approval kind, gate and stage
path named in the steering, skills, templates, hooks and pack is the one aidlc_lean.py has. The other classes
install the kit and use the real templates (no stand-ins): `stage done` refuses each page until it is edited,
the Release stage record, `request RELEASE` only for the code `lean release` checked, and `status` bringing
aidlc-state.md up to date.

Run: python3 -m unittest discover -s tests -v
"""
import glob
import hashlib
import importlib.util
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_aidlc_lean import REPO, REQ, UNITS, Base  # noqa: E402

KIT = os.path.join(REPO, "kit", ".kiro")
PACK = os.path.join(REPO, "kit-pstack", ".kiro")
BEGIN = "<!-- lean:begin progress -->"
END = "<!-- lean:end progress -->"
GATES = {"records", "protected", "contract", "intent", "released", "requirements", "design", "plan", "danger",
         "verify"}


def load_core():
    """The shipped aidlc_lean.py as a module (no __pycache__ is written into kit/)."""
    spec = importlib.util.spec_from_file_location("aidlc_lean_core", os.path.join(KIT, "aidlc-lean", "aidlc_lean.py"))
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def texts(*globs):
    return {p: read(p) for g in globs for p in sorted(glob.glob(g, recursive=True))}


class KitTexts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load_core()
        cls.steering = read(os.path.join(KIT, "steering", "aidlc-lean.md"))
        cls.skills = texts(os.path.join(KIT, "skills", "aidlc-lean-*", "SKILL.md"))
        cls.templates = texts(os.path.join(KIT, "aidlc-lean", "templates", "*"))
        cls.hooks = texts(os.path.join(KIT, "hooks", "*.json"))
        cls.pack = texts(os.path.join(PACK, "**", "*.md"))
        cls.agent_texts = dict(cls.skills, **cls.templates, **cls.pack)
        cls.agent_texts[os.path.join(KIT, "steering", "aidlc-lean.md")] = cls.steering

    def test_word_caps(self):
        self.assertLessEqual(len(self.steering.split()), 1000)
        self.assertEqual(len(self.skills), 6)
        for path, text in self.skills.items():
            self.assertLessEqual(len(text.split()), 600, path)

    def test_commands_stage_ids_and_kinds_exist(self):
        commands = set(self.core.COMMANDS) | {"hook"}
        ids = set(self.core.STAGE_BY_ID)
        for path, text in self.agent_texts.items():
            for cmd in re.findall(r"`lean ([a-z-]+)", text):
                self.assertIn(cmd, commands, path)
            for verb, sid in re.findall(r"\bstage (start|done|skip) ([a-z][a-z-]*)", text):
                self.assertIn(sid, ids, (path, verb))
            for kind in re.findall(r"\b(?:request|approve|reject) ([A-Z][A-Za-z-]*)", text):
                self.assertTrue(kind in self.core.APPROVAL_KINDS or kind.startswith("CR-"), (path, kind))
            for gate in re.findall(r"blocked \(([a-z]+)\)", text):
                self.assertIn(gate, GATES, path)
        src = read(os.path.join(KIT, "aidlc-lean", "aidlc_lean.py"))
        core_gates = set(re.findall(r'block\(pj, "([a-z]+)"', src)) | set(
            re.findall(r'(?:out\.append\(|return \[)\("([a-z]+)", ', src))  # gate_problems
        self.assertEqual(core_gates, GATES)
        construction = self.skills[os.path.join(KIT, "skills", "aidlc-lean-construction", "SKILL.md")]
        self.assertEqual(set(re.findall(r"blocked \(([a-z]+)\)", construction)), GATES)  # every gate explained

    def test_stage_table_matches_the_steering_skills_and_templates(self):
        inception = self.skills[os.path.join(KIT, "skills", "aidlc-lean-inception", "SKILL.md")]
        construction = self.skills[os.path.join(KIT, "skills", "aidlc-lean-construction", "SKILL.md")]
        for n, st in enumerate(self.core.STAGES, 1):
            self.assertIn("%d. `%s`" % (n, st.id), self.steering)  # the steering lists them in AI-DLC order
            if not st.template:
                continue
            doc = st.doc.replace("{unit}", "<unit>")
            self.assertIn("`%s`: `%s`" % (st.id, doc), self.steering)
            self.assertIn("(`%s`" % st.id, construction if st.per_unit else inception)
            tpl = self.templates[os.path.join(KIT, "aidlc-lean", "templates", st.template)]
            phase = "Construction" if st.per_unit else "Inception"
            self.assertIn("AI-DLC stage: %s · %s · " % (phase, st.name), tpl.splitlines()[2])
        self.assertEqual(sorted(os.path.basename(p) for p in self.templates), sorted(self.core.TEMPLATE_NAMES))

    def test_template_placeholders_and_markers(self):
        stage_vars = {"TITLE", "INTENT", "DATE", "UNIT", "STAGE", "MODE"}
        for path, text in self.templates.items():
            names = set(re.findall(r"\{\{([A-Z]+)\}\}", text))
            allowed = {"ID", "TITLE", "FROM", "OWNER", "PATHS", "DATE"} if path.endswith("cr.md") else stage_vars
            self.assertLessEqual(names, allowed, path)
            for hint in re.findall(r"(?s)<!--(.*?)-->", text):
                if hint.strip() in ("lean:begin progress", "lean:end progress"):
                    continue  # the markers of the generated region
                self.assertNotIn("<!--", hint, path)  # no nested comment, so the hint ends where it should
                self.assertNotIn("lean:", hint, path)
        state = self.templates[os.path.join(KIT, "aidlc-lean", "templates", "aidlc-state.md")]
        self.assertEqual((self.core.BEGIN_MARK, self.core.END_MARK), (BEGIN, END))
        self.assertEqual((state.count(BEGIN), state.count(END)), (1, 1))
        self.assertLess(state.index(BEGIN), state.index(END))
        self.assertLess(state.index(END), state.index("## Session notes"))
        self.assertIn("\n### Next\n", state.split(END)[1])
        req = self.templates[os.path.join(KIT, "aidlc-lean", "templates", "requirements.md")]
        self.assertIn("\nSize: <small|large>\n", req)  # a placeholder, not a default
        self.assertFalse(self.core.says_small(req))
        self.assertFalse(self.core.says_small(req + "\n- Size: small payloads\n"))  # the first Size line counts
        self.assertFalse(self.core.says_small(req.replace("<small|large>", "large")))
        for line in ("Size: small", "- **Size:** small", "**Size**: Small.", "Size：small"):
            self.assertTrue(self.core.says_small(req.replace("Size: <small|large>", line)), line)
        json.loads(self.templates[os.path.join(KIT, "aidlc-lean", "templates", "lean.json")])

    def test_hook_descriptions_use_the_v02_names(self):
        for path, raw in self.hooks.items():
            desc = json.loads(raw)["hooks"][0]["description"]
            for old in ("SPEC", "aidlc/", "PLAN.md", "STATE.md"):
                self.assertNotIn(old, desc, path)
        prompt = json.loads(self.hooks[os.path.join(KIT, "hooks", "aidlc-lean-prompt.json")])["hooks"][0]
        for kind in self.core.APPROVAL_KINDS:
            self.assertIn(kind, prompt["description"])


class RealTemplates(Base):
    """`stage done` refuses every stage page while it is still the shipped template, as rendered for this intent."""
    flags = []
    mode = "standard"
    title = "Refunds (v2) [EU] * 100% + $x"

    def test_every_stage_page_is_refused_until_it_is_edited(self):
        kit = os.path.join(KIT, "aidlc-lean", "templates")
        here = os.path.join(self.dir, ".kiro", "aidlc-lean", "templates")
        self.assertEqual(sorted(os.listdir(kit)), sorted(os.listdir(here)))
        for name in os.listdir(kit):  # the real templates, no stand-ins
            self.assertEqual(read(os.path.join(kit, name)), read(os.path.join(here, name)), name)
        p = self.ok("new", "refunds", "--title", self.title)
        i = re.search(r"aidlc-docs/(\S+) \(", p.stdout).group(1)
        self.assertNotIn("{{", self.read(self.ipath(i, "aidlc-state.md")))
        self.assertIn("· Mode: %s ·" % self.mode, self.read(self.ipath(i, "aidlc-state.md")))

        def check(sid, page, unit=None):
            extra = ["--unit", unit] if unit else []
            if sid != "requirements":
                self.assertIn("Created %s" % self.ipath(i, page), self.ok("stage", "start", sid, *extra).stdout)
            text = self.read(self.ipath(i, page))
            self.assertNotIn("{{", text, sid)
            self.assertIn(self.title, text, sid)
            r = self.tool("stage", "done", sid, *extra, "--note", "nothing yet")
            self.assertEqual(r.returncode, 1, (sid, r.stdout))
            self.assertIn("is still the template", r.stdout, sid)
            filled = text.replace("\n## ", "\nWritten by the agent.\n\n## ", 1) + "\n\n"
            if sid == "code-generation":  # a plan is done once every step is ticked
                filled = filled.replace("- [ ]", "- [x]")
            self.put(self.ipath(i, page), filled)
            self.ok("stage", "done", sid, *extra, "--note", "filled in")

        check("requirements", "inception/requirements/requirements.md")
        check("reverse-engineering", "inception/reverse-engineering/architecture.md")
        check("user-stories", "inception/user-stories/stories.md")
        check("application-design", "inception/application-design/application-design.md")
        self.ok("stage", "start", "units")
        r = self.tool("stage", "done", "units", "--note", "nothing yet")
        self.assertIn("is still the template", r.stdout)
        self.assertIn("app", self.ok("status").stdout)  # the untouched template lists no unit
        self.units(i, [("api", "shop", "services/api/"), ("web", "shop", "web/")])
        self.assertIn("Units: api, web", self.ok("stage", "done", "units", "--note", "two units").stdout)
        for unit in ("api", "web"):
            for sid, folder in (("functional-design", "functional-design"), ("nfr-design", "nfr-design"),
                                ("infrastructure-design", "infrastructure-design")):
                check(sid, "construction/%s/%s/%s.md" % (unit, folder, folder), unit)
            check("code-generation", "construction/plans/%s-code-generation-plan.md" % unit, unit)


class RealTemplatesRegulatedMultiTeam(RealTemplates):
    flags = ["--regulated", "--multi-team", "--team", "shop"]
    mode = "regulated, multi-team"



class ReleaseRecord(Base):
    def test_request_and_approval_need_the_release_md_lean_release_wrote_for_this_code(self):
        self.cfg(checks=["true"])
        i = self.ready()
        rel = self.ipath(i, "operations/release.md")
        self.put(rel, "# Release\n\nwritten by hand\n")  # not by `lean release`
        r = self.tool("request", "RELEASE")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Cannot request RELEASE: not ready to release: no passing verify on the current code", r.stdout)
        self.ok("verify")
        r = self.tool("request", "RELEASE")
        self.assertEqual(r.returncode, 1)
        self.assertIn("operations/release.md was not written by `python3 .kiro/aidlc-lean/aidlc_lean.py release` for "
                      "the current code", r.stdout)
        out = self.say("approve RELEASE %s" % hashlib.sha256(self.read(rel).encode()).hexdigest()[:8])
        self.assertIn("Approval of RELEASE NOT recorded: operations/release.md was not written by", out.stdout)
        self.commit_all()  # `release` names a commit, so the verified code is committed first
        self.ok("release")
        body = self.read(rel)
        self.assertIn("- [-] Release — this page; next: `request RELEASE` and the human's approval", body)
        h = self.request_hash("RELEASE")
        self.put("src/late.py", "x = 1\n")  # the code changes after `lean release`, the request is still out
        out = self.say("approve RELEASE %s" % h)
        self.assertIn("Approval of RELEASE NOT recorded", out.stdout)
        self.assertIn("- [-] Release — release.md is for older code", self.tool("status").stdout)
        os.remove(os.path.join(self.dir, "src", "late.py"))  # back to the code `lean release` checked
        out = self.say("approve RELEASE %s" % h)
        self.assertIn("Recorded: RELEASE approved (sha %s)" % h, out.stdout)
        ev = self.events("STAGE_COMPLETED")[-1]  # the approval completes the Release stage
        self.assertEqual((ev["data"]["stage"], ev["data"]["note"]), ("release", "RELEASE approved (sha %s)" % h))
        self.assertEqual(list(ev["data"]["outputs"]), [rel])
        state = self.read(self.ipath(i, "aidlc-state.md"))
        self.assertRegex(state, r"### Release · \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC · by dev@example.com \(team -\) · "
                                r"human \(prompt\)\n- Did: RELEASE approved \(sha %s\)\n"
                                r"- Outputs: operations/release.md \(sha %s\)" % (h, h))
        self.ok("audit", "pack")
        self.assertIn("Release done — RELEASE approved (sha %s)" % h, self.read(self.ipath(i, "audit.md")))
        r = self.tool("request", "RELEASE")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already released", r.stdout)


class StatusRefresh(Base):
    def test_status_brings_the_generated_region_up_to_date(self):
        i = self.intent()
        path = self.ipath(i, "aidlc-state.md")
        self.ok("stage", "skip", "user-stories", "--reason", "single persona")
        text = self.read(path)
        notes = text.split(END)[1]
        merged = text.replace("- [S] User Stories", "<<<<<<< HEAD\n- [S] User Stories\n=======\n- [ ] User Stories\n"
                              ">>>>>>> theirs", 1)  # a merge that conflicted inside the region
        self.put(path, merged)
        self.ok("status")
        text = self.read(path)
        self.assertNotIn("<<<<<<<", text)
        self.assertIn("- [S] User Stories — skipped: single persona", text)
        self.assertEqual(text.split(END)[1], notes)  # the Session notes stay as they are
        self.assertEqual((text.count(BEGIN), text.count(END)), (1, 1))


class SizePlaceholder(Base):
    def test_application_design_is_skipped_only_once_someone_writes_small(self):
        i = self.intent()
        req = self.req_path(i)
        self.assertIn("\nSize: <small|large>\n", self.read(req))  # what `lean new` writes from the real template
        p = self.tool("stage", "skip", "application-design", "--reason", "one endpoint")
        self.assertEqual(p.returncode, 1)
        self.assertIn("Application Design can be skipped only when %s says `Size: small`." % REQ, p.stdout)
        self.assertEqual(self.events("STAGE_SKIPPED"), [])
        self.assertIn("Next: finish requirements.md and the application design", self.ok("status").stdout)
        self.approve("REQUIREMENTS")
        r = self.write("src/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (design)", r.stderr)
        self.assertNotIn("stage skip application-design", r.stderr)  # not offered while the Size is not small
        self.put(req, self.read(req).replace("Size: <small|large>", "Size: small"))
        self.ok("stage", "skip", "application-design", "--reason", "one endpoint")
        self.approve("REQUIREMENTS")
        self.assertEqual(self.write("src/app.py").returncode, 0)


class ChangeRequestWording(Base):
    flags = ["--multi-team", "--team", "web"]

    def test_the_request_names_the_team_that_must_approve(self):
        self.put("aidlc-docs/contracts/OWNERS", "aidlc-docs/contracts/api/** api\n")
        self.put("aidlc-docs/contracts/api/coupons.yaml", "openapi: 3.0.0\n")
        self.intent()
        self.ok("cr", "new", "errors", "--owner", "api", "--paths", "aidlc-docs/contracts/api/coupons.yaml")
        p = self.ok("request", "CR-web-1")
        self.assertIn("Ask someone from team api to read aidlc-docs/contracts/changes/CR-web-1-errors.md", p.stdout)

    def test_next_works_on_this_teams_units_and_waits_for_the_others(self):
        self.cfg(checks=["true"])
        i = self.intent()
        self.requirements(i, "small")
        for sid in ("reverse-engineering", "user-stories", "application-design"):
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.ok("stage", "start", "units")
        self.units(i, [("api", "api", "services/api/"), ("web", "web", "web/")])
        self.ok("stage", "done", "units", "--note", "one unit per team")
        self.approve("REQUIREMENTS")
        self.assertIn("Next: unit web: record its design stages first", self.ok("status").stdout)  # not api's
        for sid in ("functional-design", "nfr-design", "infrastructure-design"):
            self.ok("stage", "skip", sid, "--unit", "web", "--reason", "not needed")
        self.ok("stage", "start", "code-generation", "--unit", "web")
        self.ok("verify")
        self.assertIn("Next: continue the code-generation plan of unit web: step 1 of 2 (", self.ok("status").stdout)
        plan = self.ipath(i, "construction/plans/web-code-generation-plan.md")
        self.put(plan, self.read(plan).replace("- [ ]", "- [x]") + "\nAll steps done.\n")
        self.assertIn("Next: `python3 .kiro/aidlc-lean/aidlc_lean.py stage done code-generation --unit web --note ...`, "
                      "then wait for unit api (team api), which another team builds", self.ok("status").stdout)
        self.ok("stage", "done", "code-generation", "--unit", "web", "--note", "web done")
        self.assertIn("Next: wait for unit api (team api), which another team builds", self.ok("status").stdout)
        self.assertIn("Next: unit api: record its design stages first", self.tool("status", team="api").stdout)


if __name__ == "__main__":
    unittest.main()
