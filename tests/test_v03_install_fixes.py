"""Regression tests for QA finding D4 (v0.3): re-running install.sh wiped the team's templates.

It used to replace .kiro/aidlc-lean/ as a whole (`rm -rf`), so a template a person had changed was silently
overwritten, a template the team had added was deleted, and the git-index step then reported the added one as
"Dropped from the git index (old kit names ...)". Now the installer records the sha256 of each template it
installs (.kiro/aidlc-lean/kit-templates.sha256; for older installs it knows the v0.2.0 templates) and on a
re-install:
- replaces a template that is still the version the kit installed;
- keeps one a person changed, writes the kit's version next to it as <name>.kit-new and says so;
- keeps one the kit does not ship (the team's own) and says so;
- removes only the kit's own old templates, and drops only those from the git index.

QA round 2: a person who merged by hand and deleted <name>.kit-new is not offered the same kit version again (F02);
a manifest that is not UTF-8 does not stop the install halfway (F09); the tests ignore dotfiles in the kit (F08).

Run: python3 -m unittest discover -s tests -v
"""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from test_aidlc_lean import REPO, Base
from test_fixes_install import V02_LEAN_JSON, case_insensitive, kit_names

TDIR = ".kiro/aidlc-lean/templates/"
MANIFEST = ".kiro/aidlc-lean/kit-templates.sha256"
KIT_TEMPLATES = os.path.join(REPO, "kit", ".kiro", "aidlc-lean", "templates")


def kit_text(name, root=KIT_TEMPLATES):
    with open(os.path.join(root, name), encoding="utf-8") as f:
        return f.read()


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tree_hash(root):
    """sha256 over every folder, file (mode and content) and link under root, .git included."""
    h = hashlib.sha256()
    for d, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(dirs + files):
            p = os.path.join(d, name)
            st = os.lstat(p)
            if stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
                h.update(("D %s %o\n" % (os.path.relpath(p, root), st.st_mode)).encode())
                continue
            try:
                with open(p, "rb") as f:
                    digest = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                digest = "unreadable"
            h.update(("F %s %o %s\n" % (os.path.relpath(p, root), st.st_mode, digest)).encode())
    return h.hexdigest()


class TemplatesOnReinstall(Base):
    def reinstall(self, install=os.path.join(REPO, "install.sh")):
        p = subprocess.run(["bash", install, self.dir], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def manifest(self):
        """{name: sha256} of kit-templates.sha256; `<name>.kit-new` entries are the kit versions already offered."""
        lines = [line.split() for line in self.read(MANIFEST).splitlines() if line and not line.startswith("#")]
        return {n: d for d, n in lines}

    def commit(self):
        self.sh(["git", "add", "-A"])
        self.assertEqual(self.sh(["git", "commit", "-qm", "install"]).returncode, 0)

    def tracked(self):
        return set(self.sh(["git", "ls-files", "--", ".kiro/aidlc-lean/"]).stdout.split())

    def dropped_line(self, out):
        return next((line for line in out.splitlines() if line.startswith("Dropped from the git index")), "")

    def newer_kit(self, changed=("requirements.md", "stories.md")):
        """A copy of this checkout whose kit ships a changed requirements.md and stories.md (or the templates
        named) and no longer ships market-research.md: what the next release would look like to this project."""
        root = os.path.realpath(tempfile.mkdtemp(prefix="lean-newkit-"))
        self.addCleanup(shutil.rmtree, root, True)
        shutil.copy(os.path.join(REPO, "install.sh"), root)
        for d in ("kit", "kit-pstack"):
            shutil.copytree(os.path.join(REPO, d), os.path.join(root, d), ignore=shutil.ignore_patterns("__pycache__"))
        tpl = os.path.join(root, "kit", ".kiro", "aidlc-lean", "templates")
        for name in changed:
            with open(os.path.join(tpl, name), "a", encoding="utf-8") as f:
                f.write("\n<!-- a line the next kit version adds -->\n")
        os.remove(os.path.join(tpl, "market-research.md"))
        return os.path.join(root, "install.sh"), tpl

    def test_a_fresh_install_records_the_templates_it_installed(self):
        self.assertEqual(self.manifest(), {n: sha(kit_text(n)) for n in kit_names(KIT_TEMPLATES)})
        p = self.reinstall()  # nothing changed: nothing kept, nothing removed, nothing dropped
        for word in ("Kept", "Removed", "Dropped", ".kit-new"):
            self.assertNotIn(word, p.stdout + p.stderr)
        self.assertEqual(kit_names(os.path.join(self.dir, TDIR)), kit_names(KIT_TEMPLATES))

    def test_a_changed_template_is_kept_and_the_kits_version_is_written_next_to_it(self):
        ours = kit_text("requirements.md") + "\n## Security review\n- Threats: <!-- our team's section -->\n"
        self.put(TDIR + "requirements.md", ours)
        self.commit()
        for _ in range(2):  # also on the next re-install: the person's version is never overwritten
            p = self.reinstall()
            self.assertEqual(self.read(TDIR + "requirements.md"), ours)
            self.assertEqual(self.read(TDIR + "requirements.md.kit-new"), kit_text("requirements.md"))
            self.assertIn("Kept %srequirements.md: " % TDIR, p.stdout)
            self.assertIn("%srequirements.md.kit-new" % TDIR, p.stdout)
            self.assertEqual(self.dropped_line(p.stdout), "")
        for name in kit_names(KIT_TEMPLATES):  # the others are the kit's
            if name != "requirements.md":
                self.assertEqual(self.read(TDIR + name), kit_text(name), name)
        # The person takes the kit's version: the next re-install updates it again and removes the .kit-new copy.
        os.replace(os.path.join(self.dir, TDIR + "requirements.md.kit-new"), os.path.join(self.dir, TDIR + "requirements.md"))
        p = self.reinstall()
        self.assertNotIn("Kept", p.stdout)
        self.assertFalse(self.exists(TDIR + "requirements.md.kit-new"))

    def test_a_template_the_team_added_is_kept_and_never_called_an_old_kit_name(self):
        mine = "# Security review: {{TITLE}}\n\nIntent: {{INTENT}}\n"
        self.put(TDIR + "security-review.md", mine)
        self.commit()
        p = self.reinstall()
        self.assertEqual(self.read(TDIR + "security-review.md"), mine)
        self.assertIn(TDIR + "security-review.md", self.tracked())  # still in the git index
        self.assertIn("Kept %ssecurity-review.md: the kit does not ship it" % TDIR, p.stdout)
        self.assertNotIn("security-review.md", self.dropped_line(p.stdout))
        self.assertNotIn("Removed", p.stdout)
        self.assertFalse(self.exists(TDIR + "security-review.md.kit-new"))
        self.sh(["git", "add", "-A"])
        self.assertIn(TDIR + "security-review.md", self.tracked())

    def test_a_team_template_with_a_v01_kit_name_is_kept(self):
        """QA R2-1: REVIEW.md, PLAN.md, ... are v0.1 kit names; in a later install such a file is the team's."""
        mine = "# Review: {{TITLE}}\n\nteam\n"
        for n in ("REVIEW.md", "PLAN.md"):
            self.put(TDIR + n, mine)
        self.commit()
        for manifest in (True, False):  # a v0.3+ install, then a v0.2-style one (no manifest, v0.2 names present)
            if not manifest:
                os.remove(os.path.join(self.dir, MANIFEST))
            p = self.reinstall()
            for n in ("REVIEW.md", "PLAN.md"):
                self.assertEqual(self.read(TDIR + n), mine, n)
                self.assertIn("Kept %s%s: the kit does not ship it" % (TDIR, n), p.stdout)
                self.assertIn(TDIR + n, self.tracked())
                self.assertNotIn(n, self.dropped_line(p.stdout))
            self.assertNotIn("Removed", p.stdout)

    def test_the_next_kit_version_updates_unchanged_templates_and_keeps_the_teams(self):
        ours = kit_text("stories.md") + "| US-2 | our extra row |  |\n"
        self.put(TDIR + "stories.md", ours)
        mine = "# Our checklist\n"
        self.put(TDIR + "team-checklist.md", mine)
        self.commit()
        install, tpl = self.newer_kit()
        p = self.reinstall(install)
        out = p.stdout
        self.assertEqual(self.read(TDIR + "requirements.md"), kit_text("requirements.md", tpl))  # unchanged: updated
        self.assertEqual(self.read(TDIR + "stories.md"), ours)  # changed by a person: kept
        self.assertEqual(self.read(TDIR + "stories.md.kit-new"), kit_text("stories.md", tpl))
        self.assertIn("Kept %sstories.md: " % TDIR, out)
        self.assertEqual(self.read(TDIR + "team-checklist.md"), mine)
        self.assertFalse(self.exists(TDIR + "market-research.md"))  # the kit's own, unchanged, no longer shipped
        self.assertIn("Removed old kit templates (the kit no longer ships them): %smarket-research.md" % TDIR, out)
        self.assertEqual(self.dropped_line(out), "Dropped from the git index (old kit names; `git add -A` records "
                                                 "the current ones): %smarket-research.md" % TDIR)
        self.assertNotIn("Kept %srequirements.md" % TDIR, out)
        self.assertIn(TDIR + "team-checklist.md", self.tracked())
        recorded = self.manifest()
        self.assertEqual(recorded.pop("stories.md.kit-new"), sha(kit_text("stories.md", tpl)))  # offered once
        self.assertEqual(recorded, {n: sha(kit_text(n, tpl)) for n in kit_names(tpl)})

    def test_a_dropped_kit_template_a_person_changed_is_kept(self):
        ours = kit_text("market-research.md") + "- Our competitor list: <!-- ours -->\n"
        self.put(TDIR + "market-research.md", ours)
        self.commit()
        install, _ = self.newer_kit()
        p = self.reinstall(install)
        self.assertEqual(self.read(TDIR + "market-research.md"), ours)
        self.assertIn("Kept %smarket-research.md: the kit does not ship it" % TDIR, p.stdout)
        self.assertEqual(self.dropped_line(p.stdout), "")

    def test_an_install_from_v02_updates_its_unchanged_templates_and_keeps_changed_ones(self):
        # v0.2.0 wrote no kit-templates.sha256; of its 13 templates only lean.json changed in v0.3
        v02 = V02_LEAN_JSON
        os.remove(os.path.join(self.dir, MANIFEST))
        self.put(TDIR + "lean.json", v02)
        ours = kit_text("decisions.md") + "Our note.\n"
        self.put(TDIR + "decisions.md", ours)
        for name in kit_names(KIT_TEMPLATES):  # the v0.3 templates were not there yet
            if name not in ("lean.json", "decisions.md", "requirements.md", "stories.md", "cr.md", "aidlc-state.md",
                            "application-design.md", "architecture.md", "unit-of-work.md", "functional-design.md",
                            "nfr-design.md", "infrastructure-design.md", "code-generation-plan.md"):
                os.remove(os.path.join(self.dir, TDIR + name))
        self.commit()
        p = self.reinstall()
        self.assertEqual(self.read(TDIR + "lean.json"), kit_text("lean.json"))  # the v0.2.0 one: updated
        self.assertNotIn("Kept %slean.json" % TDIR, p.stdout)
        self.assertEqual(self.read(TDIR + "decisions.md"), ours)
        self.assertIn("Kept %sdecisions.md: " % TDIR, p.stdout)
        self.assertEqual(self.read(TDIR + "decisions.md.kit-new"), kit_text("decisions.md"))
        self.assertEqual([n for n in kit_names(os.path.join(self.dir, TDIR)) if not n.endswith(".kit-new")],
                         kit_names(KIT_TEMPLATES))
        self.assertEqual(self.dropped_line(p.stdout), "")

    def test_a_hand_merged_template_is_not_offered_the_same_kit_version_again(self):  # QA R2 F02
        req = os.path.join(self.dir, TDIR + "requirements.md")
        ours = kit_text("requirements.md") + "\n## Security review\n- Threats: <!-- our team's section -->\n"
        self.put(TDIR + "requirements.md", ours)
        self.commit()
        self.assertIn("Kept %srequirements.md: " % TDIR, self.reinstall().stdout)  # offered once, as documented
        os.remove(req + ".kit-new")  # the person compared, merged (kept their section) and deleted the copy
        self.commit()
        for _ in range(2):  # the same kit again: nothing to offer
            p = self.reinstall()
            self.assertFalse(os.path.exists(req + ".kit-new"))
            self.assertNotIn("Kept", p.stdout)
            self.assertEqual(self.read(TDIR + "requirements.md"), ours)
        install, tpl = self.newer_kit()  # a kit that changes requirements.md: offered again
        p = self.reinstall(install)
        self.assertEqual(self.read(TDIR + "requirements.md.kit-new"), kit_text("requirements.md", tpl))
        self.assertIn("Kept %srequirements.md: " % TDIR, p.stdout)
        os.remove(req + ".kit-new")
        self.assertNotIn("Kept", self.reinstall(install).stdout)
        self.assertEqual(self.read(TDIR + "requirements.md"), ours)

    def test_a_manifest_that_is_not_utf8_does_not_stop_the_install(self):  # QA R2 F09
        ours = kit_text("stories.md") + "| US-2 | ours |  |\n"
        self.put(TDIR + "stories.md", ours)
        self.commit()
        with open(os.path.join(self.dir, MANIFEST), "ab") as f:
            f.write("# 我们改过 requirements.md\n".encode("gbk"))
            f.write(b"not a record\n")
        p = self.reinstall()
        self.assertNotIn("Traceback", p.stderr)
        self.assertIn("Kept %sstories.md: " % TDIR, p.stdout)  # the records were still read
        self.assertNotIn("Kept %srequirements.md" % TDIR, p.stdout)
        self.assertIn("kit-templates.sha256", p.stdout + p.stderr)  # the ignored lines are mentioned
        self.assertEqual(self.manifest().get("requirements.md"), sha(kit_text("requirements.md")))
        with open(os.path.join(self.dir, MANIFEST), "rb") as f:
            f.read().decode("utf-8")  # rewritten

    def install(self, install=os.path.join(REPO, "install.sh")):
        return subprocess.run(["bash", install, self.dir], capture_output=True, text=True)

    def assert_refused_and_unchanged(self, *words):
        before = tree_hash(self.dir)
        p = self.install()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        for word in ("nothing was changed",) + words:
            self.assertIn(word, p.stderr)
        self.assertEqual(tree_hash(self.dir), before, "the tree changed although the installer said 'nothing was "
                                                      "changed':\n" + p.stdout + p.stderr)
        return p

    def locked(self, path, mode):
        os.chmod(os.path.join(self.dir, path), mode)
        self.addCleanup(os.chmod, os.path.join(self.dir, path), 0o755 if mode & 0o100 or not mode else 0o644)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads and writes any file")
    def test_a_file_it_cannot_read_stops_the_install_before_anything_changes(self):  # QA R2 F09, R3 item 5
        self.put(".kiro/steering/aidlc-lean.md", self.read(".kiro/steering/aidlc-lean.md") + "an old line\n")
        self.put(TDIR + "ours.md", "# ours\n")
        self.commit()
        self.locked(TDIR + "ours.md", 0)
        self.assert_refused_and_unchanged("cannot read %sours.md" % TDIR)
        shutil.rmtree(os.path.join(self.dir, ".kiro", "hooks"))  # mkdir -p .kiro/hooks must not run first
        self.assert_refused_and_unchanged()
        shutil.rmtree(os.path.join(self.dir, ".git"))  # nor git init: a copy of the project without its .git
        self.assert_refused_and_unchanged()

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads and writes any file")
    def test_a_file_it_cannot_write_stops_the_install_before_anything_changes(self):  # QA R3 item 5
        os.remove(os.path.join(self.dir, MANIFEST))  # a v0.2.0 install: its lean.json template must be replaced
        self.put(TDIR + "lean.json", V02_LEAN_JSON)
        self.commit()
        self.locked(TDIR + "lean.json", 0o444)
        self.assert_refused_and_unchanged("cannot write %slean.json" % TDIR)
        os.chmod(os.path.join(self.dir, TDIR + "lean.json"), 0o644)
        self.locked(".kiro/hooks/aidlc-lean-guard.json", 0o444)  # the hooks are copied after the templates
        self.assert_refused_and_unchanged("cannot write .kiro/hooks/aidlc-lean-guard.json")
        os.chmod(os.path.join(self.dir, ".kiro/hooks/aidlc-lean-guard.json"), 0o644)
        self.locked(".kiro/skills/aidlc-lean-inception", 0o555)  # the skill folders are replaced as a whole
        self.assert_refused_and_unchanged("cannot write .kiro/skills/aidlc-lean-inception")
        os.chmod(os.path.join(self.dir, ".kiro/skills/aidlc-lean-inception"), 0o755)
        config = self.read("aidlc-docs/lean.json")
        self.put("aidlc-docs/lean.json", "{not json")  # lean init would stop on it after the kit was replaced
        self.assert_refused_and_unchanged("aidlc-docs/lean.json is not valid JSON")
        self.put("aidlc-docs/lean.json", config)
        self.reinstall()  # once fixed, the same install goes through
        self.assertEqual(self.read(TDIR + "lean.json"), kit_text("lean.json"))

    def test_a_failure_after_the_check_says_the_install_stopped_part_way(self):  # QA R3 item 5
        install, _ = self.newer_kit(changed=())
        with open(os.path.join(os.path.dirname(install), "kit", ".kiro", "aidlc-lean", "aidlc_lean.py"), "w") as f:
            f.write("import sys\nprint('init failed', file=sys.stderr)\nsys.exit(3)\n")
        p = self.install(install)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("install.sh: stopped part way", p.stderr)
        self.assertIn("run this installer again", p.stderr)
        self.assertNotIn("nothing was changed", p.stderr)

    @unittest.skipUnless(case_insensitive(tempfile.gettempdir()), "needs a case-insensitive file system")
    def test_a_merged_case_only_variant_is_not_offered_the_same_kit_version_again(self):  # QA R3 item 7
        ours = "# Change request (our form)\n"
        os.remove(os.path.join(self.dir, TDIR + "cr.md"))
        self.put(TDIR + "CR.md", ours)
        self.commit()
        p = self.reinstall()
        self.assertIn("Kept %sCR.md: " % TDIR, p.stdout)  # offered once
        kit_new = os.path.join(self.dir, TDIR + "cr.md.kit-new")
        merged = ours + self.read(TDIR + "cr.md.kit-new")
        self.put(TDIR + "CR.md", merged)  # the person merges the kit's version into theirs
        os.remove(kit_new)  # ... and deletes the copy
        self.commit()
        for _ in range(2):  # the same kit: nothing to offer
            p = self.reinstall()
            self.assertFalse(os.path.exists(kit_new), p.stdout)
            self.assertNotIn("Kept", p.stdout)
            self.assertEqual(self.read(TDIR + "CR.md"), merged)
        install, tpl = self.newer_kit(changed=("cr.md",))  # a newer kit version of cr.md is offered again
        p = self.reinstall(install)
        self.assertIn("Kept %sCR.md: " % TDIR, p.stdout)
        self.assertEqual(self.read(TDIR + "cr.md.kit-new"), kit_text("cr.md", tpl))
        self.assertEqual(self.read(TDIR + "CR.md"), merged)


@unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root writes any file")
class FirstInstallPreCheck(unittest.TestCase):  # QA R4 N4
    """The read-only check also covers what does not exist yet: a file or folder to be created needs its nearest
    existing folder to be writable; and what `lean init` writes: .gitignore while it lacks `.aidlc-lean/`, and the
    contracts folders in multi-team mode."""

    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix="lean-first-"))
        self.addCleanup(self.unlock_and_remove)
        for cmd in (["init", "-q"], ["config", "user.email", "dev@example.com"], ["config", "user.name", "Dev"]):
            subprocess.run(["git"] + cmd, cwd=self.dir, check=True, capture_output=True)
        self.put("README.md", "# a project that does not use AI-DLC Lean yet\n")

    def unlock_and_remove(self):
        for d, dirs, files in os.walk(self.dir):
            for n in dirs + files:
                os.chmod(os.path.join(d, n), 0o755)
        shutil.rmtree(self.dir, True)

    def put(self, path, text):
        full = os.path.join(self.dir, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)

    def install(self, *flags):
        return subprocess.run(["bash", os.path.join(REPO, "install.sh"), self.dir] + list(flags),
                              capture_output=True, text=True)

    def assert_refused_and_unchanged(self, what, *flags):
        subprocess.run(["git", "add", "-A"], cwd=self.dir, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "before"], cwd=self.dir, capture_output=True)
        before = tree_hash(self.dir)
        p = self.install(*flags)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("cannot write %s" % what, p.stderr)
        self.assertIn("nothing was changed", p.stderr)
        self.assertNotIn("stopped part way", p.stderr)
        self.assertEqual(tree_hash(self.dir), before, p.stdout + p.stderr)

    def test_a_read_only_gitignore_that_lacks_the_local_state_line(self):
        self.put(".gitignore", "node_modules/\n")
        os.chmod(os.path.join(self.dir, ".gitignore"), 0o444)
        self.assert_refused_and_unchanged(".gitignore (permission denied)")
        os.chmod(os.path.join(self.dir, ".gitignore"), 0o644)
        self.put(".gitignore", "node_modules/\n.aidlc-lean/\n")  # nothing to append: read-only is fine
        os.chmod(os.path.join(self.dir, ".gitignore"), 0o444)
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_a_read_only_skills_folder_on_a_first_install(self):
        self.put(".kiro/skills/team-review/SKILL.md", "# our review skill\n")
        os.chmod(os.path.join(self.dir, ".kiro", "skills"), 0o555)
        self.assert_refused_and_unchanged(".kiro/skills (permission denied)")
        self.assert_refused_and_unchanged(".kiro/skills (permission denied)", "--with-pstack")

    def test_a_read_only_kiro_folder_on_a_first_install(self):  # hooks, steering, the kit folder: all created
        os.makedirs(os.path.join(self.dir, ".kiro"))
        self.put(".kiro/settings.json", "{}\n")
        os.chmod(os.path.join(self.dir, ".kiro"), 0o555)
        self.assert_refused_and_unchanged(".kiro (permission denied)")

    def test_a_read_only_contracts_parent_in_multi_team_mode(self):
        self.put("aidlc-docs/lean.json", json.dumps({"version": 1, "multi_team": True,
                                                    "contracts_dir": "shared/contracts"}))
        os.makedirs(os.path.join(self.dir, "shared"))
        self.put("shared/README.md", "shared\n")
        os.chmod(os.path.join(self.dir, "shared"), 0o555)
        self.assert_refused_and_unchanged("shared (permission denied)")


class DotfileInTheKit(unittest.TestCase):  # QA R2 F08
    """Finder writes .DS_Store into a folder someone opened; the installer skips dotfiles, and so must the tests
    that compare with the kit's templates. Runs the installer tests on a copy of this checkout that has one."""

    @unittest.skipIf(os.environ.get("LEAN_DOTFILE_COPY"), "already running on the copy")
    def test_the_install_tests_pass_with_a_dotfile_in_the_kits_templates(self):
        root = os.path.realpath(tempfile.mkdtemp(prefix="lean-dotfile-"))
        self.addCleanup(shutil.rmtree, root, True)
        shutil.copy(os.path.join(REPO, "install.sh"), root)
        for d in ("kit", "kit-pstack", "tests", "tools"):
            shutil.copytree(os.path.join(REPO, d), os.path.join(root, d), ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(root, "kit", ".kiro", "aidlc-lean", "templates", ".DS_Store"), "wb") as f:
            f.write(b"\x00\x00\x00\x01Bud1")
        p = subprocess.run([sys.executable, "-m", "unittest", "test_v03_install_fixes.TemplatesOnReinstall",
                            "test_fixes_install.UpgradeFromV01", "test_fixes_install.CaseOnlyRenames"],
                           cwd=os.path.join(root, "tests"), capture_output=True, text=True,
                           env=dict(os.environ, LEAN_DOTFILE_COPY="1"))
        self.assertEqual(p.returncode, 0, p.stderr[-3000:])


if __name__ == "__main__":
    unittest.main()
