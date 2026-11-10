"""Regression tests for the installer and the pstack pack (review findings KI-10, KI-11, KI-12 / GB-14.1, KI-14),
and for the move to the v0.2 layout: the config in <project>/aidlc-docs/lean.json (also in a monorepo subfolder),
no v0.1 skills, templates or names left behind, and a v0.1 config that is never silently dropped.

Run: python3 -m unittest discover -s tests -v

The vendor_pstack.py tests need the pstack checkout the pack was generated from
(~/.claude/plugins/cache/cursor-plugins/pstack/<version in the card footers>) and are skipped without it.
They run on copies in a temp folder and never touch the repo's kit-pstack/.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_aidlc_lean import REPO, Base

INSTALL = os.path.join(REPO, "install.sh")
PACK = os.path.join(REPO, "kit-pstack")
CACHE = os.path.expanduser("~/.claude/plugins/cache/cursor-plugins/pstack")
PACK_SKILLS = ["pstack-principle-prove-it-works", "pstack-principle-test-behavior-not-implementation",
               "pstack-principle-boundary-discipline", "pstack-principle-fix-root-causes",
               "pstack-principle-sequence-verifiable-units", "pstack-principle-model-the-domain",
               "pstack-blast-radius", "pstack-correct", "pstack-interrogate", "pstack-swarm"]
# v0.1 names that v0.2 replaced (aidlc/intents/<id>/SPEC.md and so on); the same list as RETIRED in vendor_pstack.py
V01_NAMES = ("aidlc/", "SPEC.md", "PLAN.md", "STATE.md", "REVIEW.md", "UNITS.md", "DECISIONS.md", "RELEASE.md",
             "AUDIT-PACK.md")
REVIEW_MD = "aidlc-docs/<intent>/construction/build-and-test/review.md"
# The one brief file the lead writes for its subagents; each subagent's prompt only names it.
REVIEW_BRIEF = "aidlc-docs/<intent>/construction/build-and-test/review-brief.md"
SWARM_BRIEF = "aidlc-docs/<intent>/construction/swarm/brief.md"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def pack_version():
    m = re.search(r"Adapted from pstack (\S+) \(", read(os.path.join(PACK, ".kiro/skills/pstack-swarm/SKILL.md")))
    return m.group(1) if m else ""


PSTACK_SRC = os.path.join(CACHE, pack_version())


def tree(root):
    """{relative path: bytes} of every file under root."""
    out = {}
    for d, _, files in os.walk(root):
        for fn in files:
            with open(os.path.join(d, fn), "rb") as f:
                out[os.path.relpath(os.path.join(d, fn), root)] = f.read()
    return out


def frontmatter(text):
    head = text.split("---\n")[1]
    return dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)


def run_install(target, *args):
    return subprocess.run(["bash", INSTALL, target] + list(args), capture_output=True, text=True)


def git_repo(path):
    for cmd in (["init", "-q"], ["config", "user.email", "dev@example.com"], ["config", "user.name", "Dev"]):
        subprocess.run(["git"] + cmd, cwd=path, check=True, capture_output=True)


class InstallerOptions(unittest.TestCase):
    """KI-11: options are checked before anything is written."""

    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix="lean-opt-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        subprocess.run(["git", "init", "-q"], cwd=self.dir, check=True)

    def install(self, *args):
        return subprocess.run(["bash", INSTALL] + list(args), capture_output=True, text=True)

    def assert_untouched(self):
        self.assertEqual(sorted(os.listdir(self.dir)), [".git"])

    def test_unknown_or_incomplete_options_are_rejected_before_any_change(self):
        for args, msg in [(["--regulate"], "unknown option: --regulate"),
                          (["--with-pstak"], "unknown option: --with-pstak"),
                          (["--regulated", "extra"], "unknown option: extra"),
                          (["--team"], "--team needs a team name"),
                          (["--team", "--with-pstack"], "--team needs a team name"),
                          (["--team", ""], "--team needs a team name")]:
            p = self.install(self.dir, *args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn(msg, p.stderr, args)
            self.assertIn("usage:", p.stderr, args)
            self.assert_untouched()

    def test_project_dir_must_come_first(self):
        p = self.install("--regulated", self.dir)
        self.assertEqual(p.returncode, 1)
        self.assertIn("put <project-dir> first", p.stderr)
        self.assert_untouched()

    def test_help(self):
        for args in (["--help"], [self.dir, "-h"]):
            p = self.install(*args)
            self.assertEqual(p.returncode, 0, args)
            self.assertIn("usage:", p.stdout)
        self.assert_untouched()


class ReinstallMixin:
    def reinstall(self, *flags):
        p = run_install(self.dir, *flags)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def mode(self):
        cfg = json.loads(self.read("aidlc-docs/lean.json"))
        return cfg["regulated"], cfg["multi_team"]


class StandardReinstall(ReinstallMixin, Base):
    def test_mode_flag_on_an_existing_config_is_reported_not_silently_dropped(self):
        p = self.reinstall("--regulated")
        self.assertIn("WARNING: aidlc-docs/lean.json already exists, so it was kept as it is "
                      "(regulated: false, multi_team: false): --regulated was NOT applied.", p.stderr)
        self.assertIn('edit "regulated" / "multi_team" in aidlc-docs/lean.json yourself', p.stderr)
        self.assertEqual(self.mode(), (False, False))  # the team's config is never flipped by a re-install
        p = self.reinstall("--multi-team", "--team", "payments")
        self.assertIn("--multi-team was NOT applied", p.stderr)
        self.assertIn("re-run this installer with --team NAME so it creates aidlc-docs/contracts/OWNERS.", p.stderr)
        self.assertEqual(self.mode(), (False, False))

    def test_next_steps_name_the_config_and_the_folders_to_commit(self):
        nxt = self.reinstall().stdout.split("\nNext:\n", 1)[1]
        self.assertIn('1. Edit aidlc-docs/lean.json: set "checks"', nxt)
        self.assertIn("2. Commit .kiro/, aidlc-docs/ and .gitignore (not .aidlc-lean/, which is per clone and gitignored).", nxt)
        self.assertNotIn("aidlc/", nxt)

    def test_mode_message_does_not_import_the_projects_python_files(self):
        self.put("json.py", "raise SystemExit('the project json.py was imported')\n")
        p = self.reinstall("--regulated")
        self.assertIn("--regulated was NOT applied", p.stderr)
        self.assertNotIn("was imported", p.stdout + p.stderr)

    def test_plain_reinstall_prints_no_mode_message(self):
        p = self.reinstall()
        self.assertNotIn("already exists", p.stdout + p.stderr)

    def test_no_pack_means_no_pstack_license(self):
        self.reinstall()
        self.assertFalse(os.path.exists(os.path.join(self.dir, ".kiro/aidlc-lean/LICENSE-pstack")))
        self.assertNotIn("MIT notice", self.reinstall().stdout)


class RegulatedReinstall(ReinstallMixin, Base):
    flags = ["--regulated"]

    def test_matching_mode_flag_only_notes_the_kept_config(self):
        p = self.reinstall("--regulated")
        self.assertNotIn("WARNING", p.stderr)
        self.assertIn("note: aidlc-docs/lean.json already exists and was kept as it is "
                      "(regulated: true, multi_team: false).", p.stderr)
        p = self.reinstall("--regulated", "--multi-team", "--team", "payments")
        self.assertIn("--multi-team was NOT applied", p.stderr)
        self.assertNotIn("--regulated was NOT applied", p.stderr)
        self.assertEqual(self.mode(), (True, False))


class SubfolderReinstall(ReinstallMixin, Base):
    """The project is the folder that gets .kiro/, also inside a bigger repository: the installer looks for the
    config in <project>/aidlc-docs/lean.json, where the kit keeps it, not under the git top level."""

    def setUp(self):  # instead of Base.setUp: the kit goes into services/api of a bigger repository
        self.top = os.path.realpath(tempfile.mkdtemp(prefix="lean-mono-"))
        self.addCleanup(shutil.rmtree, self.top, True)
        git_repo(self.top)
        self.dir = os.path.join(self.top, "services", "api")
        os.makedirs(self.dir)
        self.reinstall()

    def test_the_kept_config_message_works_in_a_subfolder(self):
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "aidlc-docs", "lean.json")))
        self.assertFalse(os.path.exists(os.path.join(self.top, "aidlc-docs")))
        p = self.reinstall("--regulated")
        self.assertIn("WARNING: aidlc-docs/lean.json already exists, so it was kept as it is "
                      "(regulated: false, multi_team: false): --regulated was NOT applied.", p.stderr)
        self.assertEqual(self.mode(), (False, False))
        # a config at the git top level is not this project's: the message still reports the subfolder's
        os.makedirs(os.path.join(self.top, "aidlc-docs"))
        with open(os.path.join(self.top, "aidlc-docs", "lean.json"), "w") as f:
            json.dump({"regulated": True, "multi_team": True}, f)
        p = self.reinstall("--regulated")
        self.assertIn("(regulated: false, multi_team: false): --regulated was NOT applied.", p.stderr)
        self.assertEqual(self.mode(), (False, False))


def kit_names(path):
    """The template names in a folder as the installer sees them: files only, no dotfiles (e.g. Finder's .DS_Store)."""
    return sorted(n for n in os.listdir(path) if not n.startswith(".") and os.path.isfile(os.path.join(path, n)))


# templates/lean.json exactly as v0.2.0 shipped it (git show 37ecb45:kit/.kiro/aidlc-lean/templates/lean.json)
V02_LEAN_JSON = (
    '{\n'
    '  "version": 1,\n'
    '  "regulated": false,\n'
    '  "multi_team": false,\n'
    '  "plan": "auto",\n'
    '  "checks": [],\n'
    '  "protected_paths": [],\n'
    '  "free_paths": ["*.md", "docs/**"],\n'
    '  "contracts_dir": "aidlc-docs/contracts",\n'
    '  "teams": [],\n'
    '  "approvers": {},\n'
    '  "_help": "This is aidlc-docs/lean.json: people edit it, the agent cannot. Everything AI-DLC Lean k'
    'eeps in git lives under aidlc-docs/: one folder per intent, the audit ledger (aidlc-docs/audit/) and'
    ' the contracts (contracts_dir). checks: commands that must all pass, e.g. [\\"pytest -q\\", \\"ruff che'
    'ck .\\"]; lean verify runs them and writes the intent\'s construction/build-and-test/build-and-test-su'
    'mmary.md. protected_paths: acceptance tests the agent may not change, e.g. [\\"tests/acceptance/**\\"]'
    ". plan: whether each unit's code-generation plan needs a PLAN approval before its code: auto (regula"
    'ted mode only) | always | never. approvers: optional allow-lists by git email per approval kind (REQ'
    'UIREMENTS, DESIGN, INCEPTION, PLAN, RELEASE, CR), e.g. {\\"RELEASE\\": [\\"lead@corp.com\\"]}. deny_comm'
    'ands and fingerprint_exclude can be overridden too (see aidlc_lean.py DEFAULT_CONFIG)."\n'
    '}\n'
)


# templates/lean.json of a v0.1 install. Design §4 says v0.2 kept it "unchanged from v0.1", but v0.1 lived under
# aidlc/ (README: its config says "contracts_dir": "aidlc/contracts"), so it is modelled with the v0.1 paths: not
# byte-equal to any version a later kit shipped.
V01_LEAN_JSON = ('{\n  "version": 1,\n  "regulated": false,\n  "multi_team": false,\n  "plan": "auto",\n  "checks": [],\n'
                 '  "protected_paths": [],\n  "free_paths": ["*.md", "docs/**"],\n  "contracts_dir": "aidlc/contracts",\n'
                 '  "teams": [],\n  "approvers": {},\n  "_help": "This is aidlc/lean.json: people edit it, the agent cannot."\n}\n')
V01_TEMPLATES = ("CR.md", "DECISIONS.md", "PLAN.md", "SPEC.md", "STATE.md", "UNITS.md")  # with lean.json


def as_v01_templates(t, names=V01_TEMPLATES):
    """Make the project's template folder look like a v0.1 install: the v0.1 names and lean.json, which later kits
    ship too, and no kit-templates.sha256. In a later install a file with a v0.1 name is the team's."""
    tdir = os.path.join(t.dir, ".kiro", "aidlc-lean", "templates")
    shutil.rmtree(tdir)
    os.makedirs(tdir)
    manifest = os.path.join(t.dir, ".kiro", "aidlc-lean", "kit-templates.sha256")
    if os.path.exists(manifest):
        os.remove(manifest)
    t.put(".kiro/aidlc-lean/templates/lean.json", V01_LEAN_JSON)
    for name in names:
        t.put(".kiro/aidlc-lean/templates/" + name, "# %s as v0.1 shipped it\n" % name)


def case_insensitive(path):
    probe = os.path.join(path, "CaseProbe")
    open(probe, "w").close()
    try:
        return os.path.exists(os.path.join(path, "caseprobe"))
    finally:
        os.remove(probe)


class UpgradeFromV01(ReinstallMixin, Base):
    """Re-installing over a v0.1 install: the retired kit skills and templates go, the team's own skills stay."""

    def test_reinstall_removes_the_v01_skills_and_templates_and_keeps_other_skills(self):
        as_v01_templates(self)
        for path in (".kiro/skills/aidlc-lean-spec/SKILL.md", ".kiro/skills/aidlc-lean-build/SKILL.md",
                     ".kiro/aidlc-lean/templates/SPEC.md", ".kiro/aidlc-lean/templates/PLAN.md",
                     ".kiro/aidlc-lean/templates/STATE.md", ".kiro/aidlc-lean/templates/UNITS.md"):
            self.put(path, "from v0.1\n")
        mine = "---\nname: team-checklist\ndescription: ours\n---\nx\n"
        self.put(".kiro/skills/team-checklist/SKILL.md", mine)
        p = self.reinstall()
        for old in ("aidlc-lean-spec", "aidlc-lean-build"):
            self.assertFalse(os.path.exists(os.path.join(self.dir, ".kiro/skills", old)), old)
            self.assertIn("Removed .kiro/skills/%s/ (a v0.1 skill; aidlc-lean-inception and aidlc-lean-construction "
                          "replace it)." % old, p.stdout)
        for new in ("aidlc-lean-inception", "aidlc-lean-construction"):  # what the message promises is there
            self.assertTrue(os.path.isfile(os.path.join(self.dir, ".kiro/skills", new, "SKILL.md")), new)
        kit = os.path.join(REPO, "kit", ".kiro")
        installed = os.listdir(os.path.join(self.dir, ".kiro/skills"))
        self.assertEqual(sorted(n for n in installed if n.startswith("aidlc-lean-")),
                         sorted(n for n in os.listdir(os.path.join(kit, "skills")) if n.startswith("aidlc-lean-")))
        self.assertEqual(kit_names(os.path.join(self.dir, ".kiro/aidlc-lean/templates")),
                         kit_names(os.path.join(kit, "aidlc-lean", "templates")))
        self.assertEqual(self.read(".kiro/skills/team-checklist/SKILL.md"), mine)  # not the kit's: kept
        self.assertNotIn("Removed", self.reinstall().stdout)  # nothing left to remove


class CaseOnlyRenames(ReinstallMixin, Base):
    """v0.1 shipped templates/CR.md and DECISIONS.md; v0.2 ships cr.md and decisions.md. On a case-insensitive file
    system (the macOS default) `git add -A` would keep recording the old names, so the installer drops every tracked
    kit path that is not on disk with exactly that name from the index. (On a case-sensitive one this passes too.)"""

    def tracked(self):
        return set(self.sh(["git", "ls-files", "--", ".kiro/aidlc-lean/"]).stdout.split())

    def test_reinstall_lets_git_add_record_the_new_names(self):
        tdir = ".kiro/aidlc-lean/templates/"
        as_v01_templates(self, ("CR.md", "DECISIONS.md", "SPEC.md"))  # a v0.1 kit as committed
        self.sh(["git", "add", "-A"])
        self.assertEqual(self.sh(["git", "commit", "-qm", "v0.1 kit"]).returncode, 0)
        old = {tdir + n for n in ("CR.md", "DECISIONS.md", "SPEC.md")}
        self.assertLessEqual(old, self.tracked())
        p = self.reinstall()
        self.assertIn("Dropped from the git index (old kit names; `git add -A` records the current ones): ", p.stdout)
        for name in sorted(old):
            self.assertIn(name, p.stdout)
        kit = kit_names(os.path.join(REPO, "kit", ".kiro", "aidlc-lean", "templates"))
        self.assertEqual(kit_names(os.path.join(self.dir, tdir)), kit)  # the files on disk are the kit's
        self.sh(["git", "add", "-A"])
        names = self.tracked()
        self.assertEqual(sorted(n[len(tdir):] for n in names if n.startswith(tdir)), kit)  # cr.md, decisions.md, ...
        self.assertFalse(old & names)
        self.assertIn(".kiro/aidlc-lean/aidlc_lean.py", names)  # the kit files that kept their names stay tracked
        self.assertNotIn("Dropped", self.reinstall().stdout)  # nothing left to drop

    def test_a_real_v01_install_is_recognised_although_lean_json_is_a_current_name(self):  # QA R2 F01
        tdir = ".kiro/aidlc-lean/templates/"
        as_v01_templates(self)  # the six v0.1 names and its lean.json, as committed
        self.sh(["git", "add", "-A"])
        self.assertEqual(self.sh(["git", "commit", "-qm", "v0.1 kit"]).returncode, 0)
        p = self.reinstall()
        self.assertNotIn("Kept", p.stdout)  # the v0.1 kit's files are not the team's
        self.assertNotIn(".kit-new", p.stdout)
        self.assertIn("Removed old kit templates (the kit no longer ships them): ", p.stdout)
        dropped = next(line for line in p.stdout.splitlines() if line.startswith("Dropped from the git index"))
        for name in V01_TEMPLATES:
            self.assertIn(tdir + name, dropped)
        self.assertNotIn("lean.json", dropped)
        kit = kit_names(os.path.join(REPO, "kit", ".kiro", "aidlc-lean", "templates"))
        self.assertEqual(kit_names(os.path.join(self.dir, tdir)), kit)  # cr.md, decisions.md, not CR.md, ...
        self.assertEqual(self.read(tdir + "lean.json"), read(os.path.join(REPO, "kit", ".kiro", "aidlc-lean",
                                                                          "templates", "lean.json")))
        for name in ("cr.md", "decisions.md"):
            self.assertEqual(self.read(tdir + name), read(os.path.join(REPO, "kit", ".kiro", "aidlc-lean",
                                                                       "templates", name)), name)
        self.sh(["git", "add", "-A"])
        names = self.tracked()
        self.assertEqual(sorted(n[len(tdir):] for n in names if n.startswith(tdir)), kit)
        p = self.reinstall()  # now a v0.3 install: nothing left to remove, drop or keep
        for word in ("Removed", "Dropped", "Kept"):
            self.assertNotIn(word, p.stdout)

    def test_a_case_only_variant_of_a_kit_template_is_never_written_through(self):  # QA R2 F01
        """A later install with the team's CR.md: on a case-insensitive file system it is the same file as the kit's
        cr.md, so writing cr.md would overwrite it. It is kept and the kit's version goes to cr.md.kit-new."""
        tdir = ".kiro/aidlc-lean/templates/"
        ours = "# Change request (our form)\n"
        os.remove(os.path.join(self.dir, tdir + "cr.md"))
        self.put(tdir + "CR.md", ours)
        self.sh(["git", "add", "-A"])
        self.assertEqual(self.sh(["git", "commit", "-qm", "our CR.md"]).returncode, 0)
        kit_cr = read(os.path.join(REPO, "kit", ".kiro", "aidlc-lean", "templates", "cr.md"))
        for _ in range(2):
            p = self.reinstall()
            listed = os.listdir(os.path.join(self.dir, tdir))
            self.assertIn("CR.md", listed)
            with open(os.path.join(self.dir, tdir, "CR.md"), encoding="utf-8") as f:
                self.assertEqual(f.read(), ours)  # never overwritten
            self.assertNotIn("Dropped", p.stdout)
            if case_insensitive(self.dir):
                self.assertNotIn("cr.md", listed)
                self.assertEqual(self.read(tdir + "cr.md.kit-new"), kit_cr)
                self.assertIn("Kept %sCR.md: " % tdir, p.stdout)
                self.assertIn("%scr.md.kit-new" % tdir, p.stdout)
            else:  # two files: the kit's cr.md, and the team's CR.md
                self.assertIn("cr.md", listed)
                self.assertEqual(self.read(tdir + "cr.md"), kit_cr)
                self.assertIn("Kept %sCR.md: the kit does not ship it" % tdir, p.stdout)


class V01Config(unittest.TestCase):
    """v0.2 does not read aidlc/lean.json. Installing over it would quietly drop the team's mode, checks and
    protected_paths, so the installer stops, changes nothing, and leaves the move to a person."""

    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix="lean-v01-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        git_repo(self.dir)
        self.v01 = {"version": 1, "regulated": True, "multi_team": False, "checks": ["pytest -q"],
                    "protected_paths": ["tests/acceptance/**"], "contracts_dir": "aidlc/contracts"}
        os.makedirs(os.path.join(self.dir, "aidlc"))
        with open(os.path.join(self.dir, "aidlc", "lean.json"), "w") as f:
            json.dump(self.v01, f)

    def test_a_v01_config_stops_the_install_until_a_person_moves_it(self):
        p = run_install(self.dir, "--with-pstack")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("install.sh: aidlc/lean.json is an AI-DLC Lean v0.1 config, and this version reads "
                      "aidlc-docs/lean.json.", p.stderr)
        self.assertIn("would drop its mode, checks and protected_paths, so nothing was changed.", p.stderr)
        self.assertEqual(sorted(os.listdir(self.dir)), [".git", "aidlc"])
        self.assertEqual(os.listdir(os.path.join(self.dir, "aidlc")), ["lean.json"])
        # Once a person has moved it, the install goes ahead and keeps it as it is, regulated mode included.
        os.makedirs(os.path.join(self.dir, "aidlc-docs"))
        os.rename(os.path.join(self.dir, "aidlc", "lean.json"), os.path.join(self.dir, "aidlc-docs", "lean.json"))
        p = run_install(self.dir, "--regulated")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("note: aidlc-docs/lean.json already exists and was kept as it is "
                      "(regulated: true, multi_team: false).", p.stderr)
        with open(os.path.join(self.dir, "aidlc-docs", "lean.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), self.v01)
        shutil.copy(os.path.join(self.dir, "aidlc-docs", "lean.json"), os.path.join(self.dir, "aidlc", "lean.json"))
        p = run_install(self.dir)  # a v0.1 copy left next to the moved config no longer stops anything
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


class PstackReinstall(ReinstallMixin, Base):
    flags = ["--with-pstack"]

    def agent(self, name):
        return os.path.join(self.dir, ".kiro/agents", name)

    def test_core_only_reinstall_keeps_the_pstack_mit_notice(self):  # KI-10
        p = self.reinstall()
        lic = os.path.join(self.dir, ".kiro/aidlc-lean/LICENSE-pstack")
        self.assertTrue(os.path.exists(lic))
        self.assertEqual(read(lic), read(os.path.join(PACK, "LICENSE-pstack")))
        self.assertIn("Kept the pstack MIT notice", p.stdout)
        for name in PACK_SKILLS:  # the pack stays installed, and every footer points at a file that exists
            self.assertIn("See `.kiro/aidlc-lean/LICENSE-pstack`", self.read(".kiro/skills/%s/SKILL.md" % name))

    def test_reinstall_keeps_a_changed_model_and_the_teams_own_agents(self):  # KI-11
        old_k3 = '---\nname: lean-reviewer-k3\ndescription: old\ntools: ["read", "shell"]\nmodel: claude-sonnet-5\n---\nold\n'
        self.put(".kiro/agents/lean-reviewer-k3.md", old_k3)
        mine = "---\nname: lean-architect\ndescription: mine\n---\nx\n"
        self.put(".kiro/agents/lean-architect.md", mine)
        self.put(".kiro/agents/lean-reviewer-gpt.md", "---\nname: lean-reviewer-gpt\nmodel: gpt-5.6-terra\n---\nx\n")
        with open(self.agent("lean-reviewer-opus.md"), "a") as f:
            f.write("a body edit, model unchanged\n")
        p = self.reinstall("--with-pstack")
        self.assertEqual(read(self.agent("lean-reviewer-k3.md")), old_k3)
        self.assertIn("Kept .kiro/agents/lean-reviewer-k3.md: its model (claude-sonnet-5) differs from the shipped one "
                      "(kimi-k3)", p.stdout)
        self.assertIn('Its tools line also differs from the shipped one (tools: ["read"])', p.stdout)
        self.assertEqual(read(self.agent("lean-architect.md")), mine)
        self.assertFalse(os.path.exists(self.agent("lean-reviewer-gpt.md")))
        self.assertIn("Removed .kiro/agents/lean-reviewer-gpt.md", p.stdout)
        for name in ("lean-reviewer-opus.md", "lean-worker.md"):  # unchanged model: the shipped file wins
            self.assertEqual(read(self.agent(name)), read(os.path.join(PACK, ".kiro/agents", name)), name)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, ".kiro/agents"))),
                         ["lean-architect.md", "lean-reviewer-k3.md", "lean-reviewer-opus.md", "lean-worker.md"])


class PackContent(Base):
    """KI-14 / GB-14.4: what the installed pack tells the agents."""
    flags = ["--with-pstack"]

    def test_reviewers_are_read_only_by_construction(self):
        for name, model in (("lean-reviewer-opus", "claude-opus-5.5"), ("lean-reviewer-k3", "kimi-k3")):
            text = self.read(".kiro/agents/%s.md" % name)
            fm = frontmatter(text)
            self.assertEqual(fm["name"], name)
            self.assertEqual(fm["tools"], '["read"]', name)
            self.assertEqual(fm["model"], model, name)
            self.assertIn("no shell", text)
            self.assertNotIn("Use the shell", text)
        worker = frontmatter(self.read(".kiro/agents/lean-worker.md"))
        self.assertEqual(worker["tools"], '["read", "write", "shell"]')
        self.assertNotIn("model", worker)
        for fn in os.listdir(os.path.join(self.dir, ".kiro/agents")):
            self.assertNotIn("gpt", self.read(".kiro/agents/" + fn).lower(), fn)

    def test_no_references_to_unshipped_skills_or_other_hosts_tools(self):
        files = [os.path.join(d, fn) for name in PACK_SKILLS
                 for d, _, fs in os.walk(os.path.join(self.dir, ".kiro/skills", name)) for fn in fs]
        files += [os.path.join(self.dir, ".kiro/steering/aidlc-lean-pstack.md")]
        self.assertEqual(len(files), 15)  # 10 cards, 4 interrogate references, the steering page
        for path in files:
            text = read(path)
            for bad in ("unslop", "/correct", "Read, Grep, Glob", "Claude Code", "`arena`", "`why`", "`how`"):
                self.assertNotIn(bad, text, (path, bad))
        rubric = self.read(".kiro/skills/pstack-interrogate/references/rubric.md")
        self.assertIn("Use the tools available to you (read_file, grep_search, file_search)", rubric)
        self.assertIn("Use when the human corrects the same kind of mistake twice.",
                      self.read(".kiro/skills/pstack-correct/SKILL.md"))
        self.assertIn("Write it plainly, without filler, cite real code",
                      self.read(".kiro/skills/pstack-blast-radius/SKILL.md"))

    def test_swarm_reviewers_reply_only_and_the_parallel_write_precondition_works_in_every_mode(self):
        swarm = self.read(".kiro/skills/pstack-swarm/SKILL.md")
        self.assertIn("Reviewers report only in their reply. A `lean-worker` may instead write its report to its own "
                      "file, `aidlc-docs/<intent>/construction/swarm/<worker>.md`.", swarm)
        self.assertEqual(swarm.count("swarm/<worker>.md"), 1)
        self.assertNotIn("Each worker gets its own writable output", swarm)
        self.assertIn("**Writing code in parallel** is for `lean-worker` only", swarm)
        self.assertIn("- `inception/application-design/unit-of-work.md` (if the intent has none, create it with "
                      "`lean stage start units` and finish that stage first) or the code-generation plan gives each "
                      "worker disjoint paths;", swarm)
        # Standard mode creates no unit-of-work.md. The card's route works: the tool creates it from its template,
        # then the agent fills it in and a worker writes its report file.
        i = self.intent()
        uow = "aidlc-docs/%s/inception/application-design/unit-of-work.md" % i
        self.assertFalse(os.path.exists(os.path.join(self.dir, uow)))
        p = self.tool("stage", "start", "units")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.dir, uow)))
        r = self.write(uow, self.read(uow) + "| api | payments | src/api/** | - | - | AC-1 | not started |\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.write("aidlc-docs/%s/construction/swarm/lean-worker-1.md" % i, "PASS\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_the_pack_uses_the_v02_layout_and_its_paths_are_open_to_the_agent(self):
        pack = [os.path.join(d, fn) for top in (".kiro/skills", ".kiro/agents", ".kiro/steering")
                for d, _, fs in os.walk(os.path.join(self.dir, top)) for fn in fs
                if fn.startswith("lean-") or fn == "aidlc-lean-pstack.md" or "/pstack-" in d]
        self.assertEqual(len(pack), 18)  # 10 cards, 4 interrogate references, 3 subagents, the steering page
        for path in pack:
            text = read(path)
            for old in V01_NAMES:
                self.assertNotIn(old, text, (path, old))
            self.assertNotRegex(text, r"\bSPEC\b", path)
        interrogate = self.read(".kiro/skills/pstack-interrogate/SKILL.md")
        self.assertIn("Write `%s` with these sections" % REVIEW_MD, interrogate)
        for doc in ("inception/requirements/requirements.md", "inception/application-design/application-design.md",
                    "construction/plans/<unit>-code-generation-plan.md"):
            self.assertIn("`%s`" % doc, interrogate)
        self.assertIn("the verdict goes to `%s`." % REVIEW_MD, self.read(".kiro/steering/aidlc-lean-pstack.md"))
        self.assertIn("the Session notes in aidlc-state.md", self.read(".kiro/skills/pstack-swarm/SKILL.md"))
        self.assertIn("keep it under `aidlc-docs/<intent>/construction/build-and-test/` and note it in the intent's "
                      "decisions.md", self.read(".kiro/skills/pstack-principle-prove-it-works/SKILL.md"))
        self.assertIn("You cannot edit `aidlc-docs/lean.json` or the hooks.",
                      self.read(".kiro/skills/pstack-correct/SKILL.md"))
        # What the cards tell the agent to write is not held by the gates; what they say it cannot edit is.
        i = self.intent()
        for path in (REVIEW_MD, REVIEW_BRIEF, SWARM_BRIEF,
                     "aidlc-docs/<intent>/construction/build-and-test/compare-output.txt",
                     "aidlc-docs/<intent>/construction/swarm/lean-worker-1.md"):
            r = self.write(path.replace("<intent>", i), "x\n")
            self.assertEqual(r.returncode, 0, (path, r.stderr))
        r = self.write("aidlc-docs/lean.json", "{}\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (records)", r.stderr)

    def test_interrogate_puts_the_diff_in_the_reviewers_brief(self):
        text = self.read(".kiro/skills/pstack-interrogate/SKILL.md")
        self.assertIn("`{DIFF_OR_FILES}`: the full diff plus the acceptance criteria table from requirements.md. The "
                      "reviewers have read tools only (no shell, no writes)", text)
        self.assertNotIn("Tell each reviewer the review is read-only", text)
        # reviewers cannot run probes any more, so the lead runs the ones they name
        self.assertIn("When a reviewer names a command or test that would confirm a finding, run it yourself", text)
        self.assertIn("When a reviewer names a command that would confirm a finding, run it yourself.",
                      self.read(".kiro/skills/pstack-swarm/SKILL.md"))
        self.assertIn("name the command in your reply for the lead to run", self.read(".kiro/agents/lean-reviewer-k3.md"))
        self.assertIn("with the same question and the diff", self.read(".kiro/skills/pstack-blast-radius/SKILL.md"))

    def test_the_brief_is_written_once_and_each_subagent_gets_a_short_prompt_naming_it(self):
        # Live (kiro-cli 3.1.0): two 37 KB prompts in one message started the second reviewer 69 s late, because
        # Kiro starts a subagent only once its call has been written out. One brief file fixes that and records it.
        text = self.read(".kiro/skills/pstack-interrogate/SKILL.md")
        self.assertIn("Write one brief for both reviewers to `%s`" % REVIEW_BRIEF, text)
        self.assertIn("Give both the same short prompt that names the brief", text)
        self.assertIn("Never paste the brief into the prompt.", text)
        self.assertIn("do not change it after the dispatch, and commit it with review.md", text)
        self.assertIn("Agreement map, Out-of-design changes.", text)
        self.assertLess(text.index("## Step 3, Write the brief once"), text.index("## Step 4, Dispatch the reviewers"))
        self.assertIn("the lead writes it once to `%s`" % REVIEW_BRIEF,
                      self.read(".kiro/skills/pstack-interrogate/references/reviewer-prompt.md"))
        swarm = self.read(".kiro/skills/pstack-swarm/SKILL.md")
        self.assertIn("Write the shared brief once to a file, `%s`" % SWARM_BRIEF, swarm)
        self.assertIn("each with a short prompt: the brief's path plus that worker's own slice or race arm", swarm)
        for name in ("lean-reviewer-opus", "lean-reviewer-k3", "lean-worker"):
            agent = self.read(".kiro/agents/%s.md" % name)
            self.assertIn("When your prompt names a brief file, read that file first and follow it.", agent, name)
        for name in ("lean-reviewer-opus", "lean-reviewer-k3"):  # models and read-only stay as they were
            self.assertIn("with a short prompt that names a brief file holding the diff",
                          frontmatter(self.read(".kiro/agents/%s.md" % name))["description"], name)

    def test_steering_says_read_only_and_stays_short(self):
        text = self.read(".kiro/steering/aidlc-lean-pstack.md")
        self.assertIn("`lean-reviewer-opus`, `lean-reviewer-k3` (read-only, no shell: put the diff in their brief).", text)
        self.assertLess(len(text.split()), 150)  # always loaded, so it stays about one page


@unittest.skipUnless(os.path.isdir(os.path.join(PSTACK_SRC, "skills")), "pstack %s checkout not found" % pack_version())
class VendorPstack(unittest.TestCase):
    """KI-12 / GB-14.1: tools/vendor_pstack.py, run on copies."""

    def setUp(self):
        self.w = os.path.realpath(tempfile.mkdtemp(prefix="lean-vendor-"))
        self.addCleanup(shutil.rmtree, self.w, True)
        self.repo = os.path.join(self.w, "repo")
        os.makedirs(os.path.join(self.repo, "tools"))
        shutil.copy(os.path.join(REPO, "tools", "vendor_pstack.py"), os.path.join(self.repo, "tools"))
        shutil.copytree(PACK, os.path.join(self.repo, "kit-pstack"))
        self.up = self.upstream(os.path.join(self.w, "up"))
        self.before = tree(os.path.join(self.repo, "kit-pstack"))

    def upstream(self, dest, version=None):
        os.makedirs(dest)
        for name in ("skills", "agents", ".claude-plugin"):
            if os.path.isdir(os.path.join(PSTACK_SRC, name)):
                shutil.copytree(os.path.join(PSTACK_SRC, name), os.path.join(dest, name))
        for name in ("LICENSE", "plugin.json"):
            if os.path.exists(os.path.join(PSTACK_SRC, name)):
                shutil.copy(os.path.join(PSTACK_SRC, name), dest)
        if version:
            self.set_version(dest, version)
        return dest

    def set_version(self, src, version, which=(".claude-plugin/plugin.json", "plugin.json")):
        for name in which:
            path = os.path.join(src, name)
            if os.path.exists(path):
                data = json.loads(read(path))
                data["version"] = version
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

    def edit(self, rel, old, new):
        path = os.path.join(self.up, rel)
        text = read(path)
        self.assertIn(old, text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new))

    def append(self, rel, text):
        with open(os.path.join(self.up, rel), "a", encoding="utf-8") as f:
            f.write(text)

    def vendor(self, *args, optimize=False, home=None):
        env = dict(os.environ)
        if home:
            env["HOME"] = home
        cmd = [sys.executable, "-I"] + (["-O"] if optimize else []) + [os.path.join(self.repo, "tools", "vendor_pstack.py")]
        return subprocess.run(cmd + list(args), cwd=self.repo, capture_output=True, text=True, env=env)

    def footers(self):
        out = tree(os.path.join(self.repo, "kit-pstack"))
        return sorted(set(re.findall(r"Adapted from pstack (\S+) \(", b"".join(out.values()).decode("utf-8"))))

    def assert_pack_unchanged(self):
        self.assertEqual(tree(os.path.join(self.repo, "kit-pstack")), self.before)
        self.assertEqual(sorted(os.listdir(self.repo)), ["kit-pstack", "tools"])  # no temp folders left behind

    def test_regenerates_the_shipped_pack_exactly(self):
        # Also proves the repo's kit-pstack/ is what tools/vendor_pstack.py produces (nobody edited it by hand).
        with open(os.path.join(self.repo, "kit-pstack", "STALE"), "w") as f:
            f.write("from an older run")
        p = self.vendor(self.up)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("(pstack %s, 19 files)" % pack_version(), p.stdout)
        self.assertEqual(tree(os.path.join(self.repo, "kit-pstack")), tree(PACK))

    def test_an_upstream_wording_change_fails_before_touching_the_pack_also_under_O(self):
        self.edit("skills/blast-radius/SKILL.md", "run it as an `arena`", "run it as an `arena` round")
        for optimize in (False, True):
            p = self.vendor(self.up, optimize=optimize)
            self.assertEqual(p.returncode, 1, (optimize, p.stdout))
            self.assertIn("blast-radius: the upstream text for an edit is gone", p.stderr)
            self.assert_pack_unchanged()

    def test_r1_120_every_upstream_text_that_is_gone_is_listed_at_once(self):
        self.edit("skills/blast-radius/SKILL.md", "run it as an `arena`", "run it as an `arena` round")
        self.edit("skills/correct/SKILL.md", "Use for /correct.", "Use it for /correct.")
        self.edit("skills/interrogate/references/rubric.md", "(Read, Grep, Glob)", "(Read, Grep and Glob)")
        p = self.vendor(self.up)
        self.assertEqual(p.returncode, 1, p.stdout)
        for label in ("blast-radius", "correct", "rubric.md"):
            self.assertIn("\n  %s: the upstream text for an edit is gone" % label, p.stderr)
        self.assertIn("update the edit tables in tools/vendor_pstack.py; kit-pstack/ was not changed", p.stderr)
        self.assert_pack_unchanged()

    def test_every_output_file_is_scanned_including_references(self):
        self.append("skills/interrogate/references/lead-judgment.md",
                    "\nAsk `arena` or **show-me-your-work**, then use (Read, Grep, Glob) as in Claude Code.\n")
        self.append("skills/principle-fix-root-causes/SKILL.md", "\nRun /tdd first, or see `pstack-arena`.\n")
        self.append("skills/principle-model-the-domain/SKILL.md", "\nRecord the model in aidlc/intents/<id>/SPEC.md.\n")
        for optimize in (False, True):
            p = self.vendor(self.up, optimize=optimize)
            self.assertEqual(p.returncode, 1, p.stdout)
            for msg in ("lead-judgment.md: contains 'Claude Code'", "lead-judgment.md: contains 'Read, Grep, Glob'",
                        "lead-judgment.md: refers to 'arena'", "lead-judgment.md: refers to 'show-me-your-work'",
                        "pstack-principle-fix-root-causes/SKILL.md: refers to 'tdd'",
                        "pstack-principle-fix-root-causes/SKILL.md: refers to 'pstack-arena'",
                        "pstack-principle-model-the-domain/SKILL.md: contains 'aidlc/', an AI-DLC Lean v0.1 name",
                        "pstack-principle-model-the-domain/SKILL.md: contains 'SPEC.md', an AI-DLC Lean v0.1 name",
                        "kit-pstack/ was not changed"):
                self.assertIn(msg, p.stderr)
            self.assert_pack_unchanged()

    def test_the_footer_version_comes_from_plugin_json(self):
        self.set_version(self.up, "0.16.0")
        p = self.vendor(self.up)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.footers(), ["0.16.0"])
        shutil.rmtree(os.path.join(self.up, ".claude-plugin"))  # a checkout with only the top-level plugin.json
        self.set_version(self.up, "0.16.1")
        p = self.vendor(self.up)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.footers(), ["0.16.1"])

    def test_missing_or_conflicting_versions_fail(self):
        self.set_version(self.up, "0.16.1", which=("plugin.json",))
        p = self.vendor(self.up)
        self.assertEqual(p.returncode, 1)
        self.assertIn("disagree on the version", p.stderr)
        self.assert_pack_unchanged()
        os.remove(os.path.join(self.up, "plugin.json"))
        os.remove(os.path.join(self.up, ".claude-plugin", "plugin.json"))
        p = self.vendor(self.up)
        self.assertEqual(p.returncode, 1)
        self.assertIn("the pstack version is unknown", p.stderr)
        self.assert_pack_unchanged()

    def test_default_source_is_the_newest_cached_version(self):
        home = os.path.join(self.w, "home")
        cache = os.path.join(home, ".claude/plugins/cache/cursor-plugins/pstack")
        self.upstream(os.path.join(cache, "0.9.1"), "0.9.1")
        self.upstream(os.path.join(cache, "0.16.0"), "0.16.0")  # newer than 0.9.1, although it sorts first as text
        os.makedirs(os.path.join(cache, "notes"))
        with open(os.path.join(cache, "0.99.0"), "w") as f:
            f.write("a file, not a version folder")
        p = self.vendor(home=home)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(os.path.join(cache, "0.16.0"), p.stdout)
        self.assertEqual(self.footers(), ["0.16.0"])
        p = self.vendor(home=os.path.join(self.w, "nohome"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("pass the pstack folder as an argument", p.stderr)

    def test_bad_arguments(self):
        for args in (["a", "b"], ["--force"]):
            p = self.vendor(*args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn("usage: python3 tools/vendor_pstack.py [PSTACK_DIR]", p.stderr)
        p = self.vendor(os.path.join(self.w, "nothing-here"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("pstack not found", p.stderr)
        self.assert_pack_unchanged()


if __name__ == "__main__":
    unittest.main()
