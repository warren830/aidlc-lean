"""Regression tests for the script fixes in kit/.kiro/aidlc-lean/aidlc_lean.py.

Covers: parallel hook processes (KI-8 / GB-8), the project root in a monorepo subfolder (KI-5), the
git-index fingerprint (KI-7), capped hook context (KI-13), doctor counting only this clone (KI-4),
per-session resume (GB-14.9), `audit pack <name>` (GB-14.3), release without checks, the released
status, `audit verify` without ledgers, INTENT_SWITCHED, creating the code-generation plan from its
template (GB-14.2, `stage start code-generation` since v0.2), secret masking and the evidence hash (GB-10),
and the guard hook's description. All on the v0.2 layout (aidlc-docs/).

Run: python3 -m unittest discover -s tests -v
"""
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_aidlc_lean import DOCS, REPO, TOOL, Base  # noqa: E402

KIT_SCRIPT = os.path.join(REPO, "kit", ".kiro", "aidlc-lean", "aidlc_lean.py")
FINGERPRINT = ("import sys; sys.path.insert(0, '.kiro/aidlc-lean'); import aidlc_lean as L; "
               "print(L.Project(L.find_root()).fingerprint())")
PLAN = "construction/plans/app-code-generation-plan.md"


def load_kit_module():
    spec = importlib.util.spec_from_file_location("aidlc_lean_under_test", KIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no __pycache__ in the repo
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


def umask():
    m = os.umask(0)
    os.umask(m)
    return m


class Helpers:
    def fp(self, cwd=None):
        """The fingerprint as a fresh process computes it."""
        p = subprocess.run([sys.executable, "-B", "-c", FINGERPRINT], cwd=cwd or self.dir, capture_output=True,
                           text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def parallel_hooks(self, event, payloads):
        """Start one hook process per payload, let them all wait on stdin, then release them together."""
        procs = []
        for extra in payloads:
            payload = dict({"session_id": "sess_par", "hook_event_name": event, "cwd": self.dir}, **extra)
            out, err = tempfile.TemporaryFile("w+"), tempfile.TemporaryFile("w+")
            proc = subprocess.Popen(TOOL + ["hook", event], cwd=self.dir, stdin=subprocess.PIPE, stdout=out,
                                    stderr=err, text=True, env=self.env())
            procs.append((proc, json.dumps(payload), out, err))
        for proc, data, _, _ in procs:
            proc.stdin.write(data)
            proc.stdin.close()
        results = []
        for proc, _, out, err in procs:
            proc.wait(timeout=180)
            out.seek(0)
            err.seek(0)
            results.append((proc.returncode, out.read(), err.read()))
            out.close()
            err.close()
        return results

    def ledgers(self):
        d = os.path.join(self.dir, DOCS, "audit")
        return {f: [json.loads(l) for l in self.read(os.path.join(DOCS, "audit", f)).splitlines() if l.strip()]
                for f in os.listdir(d) if f.endswith(".jsonl")}

    def commit_all(self, msg="human commit"):
        self.sh(["git", "add", "-A"])
        p = self.sh(["git", "commit", "-qm", msg])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


# ---------------------------------------------------------------- KI-8 / GB-8: parallel hooks
class ParallelHooks(Helpers, Base):
    flags = ["--regulated"]

    def test_parallel_approved_writes_all_pass_and_the_ledger_chain_verifies(self):
        self.cfg(protected_paths=["tests/acceptance/**"])
        i = self.ready()
        self.ok("stage", "start", "code-generation")
        self.approve("PLAN")
        self.say("allow test change")  # protected writes append PROTECTED_CHANGE: parallel ledger appends too
        n = 12
        for rnd in range(3):
            payloads = []
            for k in range(n):
                for path in ("src/w%d_%d.py" % (rnd, k), "tests/acceptance/t%d_%d.py" % (rnd, k)):
                    payloads.append({"tool_name": "fs_write",
                                     "tool_input": {"path": os.path.join(self.dir, path), "text": "x"}})
            for code, _, err in self.parallel_hooks("PreToolUse", payloads):  # 24 at once
                self.assertEqual(code, 0, err)
                self.assertNotIn("hook error", err)
        counters = json.loads(self.read(".aidlc-lean/counters.json"))
        self.assertEqual(counters["writes_since_state"], 3 * n)  # serialized read-modify-write: nothing lost
        self.assertEqual(len(self.events("PROTECTED_CHANGE")), 3 * n)
        v = self.tool("audit", "verify")
        self.assertEqual(v.returncode, 0, v.stdout)
        local = os.path.join(self.dir, ".aidlc-lean")
        self.assertEqual([f for f in os.listdir(local) if f.endswith(".tmp")], [])
        # unique temp files (mkstemp) still give the usual permissions
        normal = 0o666 & ~umask()
        for path in (".aidlc-lean/counters.json", "aidlc-docs/lean.json", self.req_path(i),
                     self.ipath(i, "aidlc-state.md")):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.dir, path)).st_mode), normal, path)

    def test_parallel_hooks_agree_on_one_new_clone_id(self):
        shutil.rmtree(os.path.join(self.dir, ".aidlc-lean"))  # e.g. a fresh clone: no clone-id yet
        before = set(self.ledgers())
        results = self.parallel_hooks("UserPromptSubmit", [{"prompt": "hello %d" % k} for k in range(20)])
        for code, _, err in results:
            self.assertEqual(code, 0, err)
        cid = self.read(".aidlc-lean/clone-id").strip()
        self.assertEqual(set(self.ledgers()) - before, {cid + ".jsonl"})
        recs = self.ledgers()[cid + ".jsonl"]
        self.assertEqual([r["seq"] for r in recs], list(range(1, 21)))
        self.assertEqual(sorted(r["data"]["turn"] for r in recs), list(range(1, 21)))  # turn.json under the lock
        self.assertEqual(self.tool("audit", "verify").returncode, 0)


# ---------------------------------------------------------------- KI-5: monorepo subfolder
class MonorepoSubfolder(Helpers, Base):
    def setUp(self):  # the kit goes into services/api of a bigger repository
        self.top = os.path.realpath(tempfile.mkdtemp(prefix="lean-mono-"))
        self.addCleanup(shutil.rmtree, self.top, True)
        for cmd in (["init", "-q"], ["config", "user.email", "dev@example.com"], ["config", "user.name", "Dev"]):
            subprocess.run(["git"] + cmd, cwd=self.top, capture_output=True)
        os.makedirs(os.path.join(self.top, "web"))
        for path, text in (("README.md", "monorepo\n"), ("web/app.js", "console.log(1)\n")):
            with open(os.path.join(self.top, path), "w") as f:
                f.write(text)
        subprocess.run(["git", "add", "-A"], cwd=self.top, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "root"], cwd=self.top, capture_output=True)
        self.dir = os.path.join(self.top, "services", "api")
        os.makedirs(self.dir)
        p = subprocess.run(["bash", os.path.join(REPO, "install.sh"), self.dir], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.ensure_templates()

    def top_status(self):
        return subprocess.run(["git", "status", "--porcelain"], cwd=self.top, capture_output=True, text=True).stdout

    def test_aidlc_docs_live_next_to_the_kit_and_status_new_verify_work(self):
        self.assertTrue(os.path.exists(os.path.join(self.dir, DOCS, "lean.json")))
        self.assertFalse(os.path.exists(os.path.join(self.top, DOCS)))
        self.assertTrue(os.listdir(os.path.join(self.dir, DOCS, "audit")))
        self.assertIn(".aidlc-lean/", self.read(".gitignore"))
        self.assertNotIn(".aidlc-lean", self.top_status())
        self.assertIn("mode: standard", self.tool("status").stdout)
        self.cfg(checks=["true"])
        i = self.intent()
        self.assertTrue(os.path.isdir(os.path.join(self.dir, DOCS, i)))
        self.assertEqual(self.write("src/app.py").returncode, 2)
        self.requirements(i)
        self.ok("stage", "skip", "application-design", "--reason", "small")
        out, _ = self.approve("REQUIREMENTS")
        self.assertIn("Recorded: REQUIREMENTS approved", out.stdout)
        self.assertEqual(self.write("src/app.py").returncode, 0)
        for p in (".kiro/hooks/aidlc-lean-guard.json", ".kiro/aidlc-lean/aidlc_lean.py", ".kiro/steering/aidlc-lean.md"):
            r = self.write(p)  # the kit's own files stay off-limits in the subfolder
            self.assertEqual(r.returncode, 2, p)
            self.assertIn("blocked (records)", r.stderr)
        self.put("src/app.py", "print('ok')\n")
        r = self.bash("git add -A && git commit -m slice1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (verify)", r.stderr)
        v = self.tool("verify")
        self.assertEqual(v.returncode, 0, v.stdout)
        self.assertEqual(self.bash("git add -A && git commit -m slice1").returncode, 0)
        self.commit_all("slice1")
        self.assertNotIn("code changed since", self.tool("status").stdout)
        with open(os.path.join(self.top, "web", "app.js"), "a") as f:  # outside this project
            f.write("// edit\n")
        self.assertNotIn("code changed since", self.tool("status").stdout)
        self.put("src/app.py", "print('changed')\n")
        self.assertIn("code changed since", self.tool("status").stdout)

    def test_records_only_commit_in_a_subfolder_needs_no_verify(self):
        self.cfg(checks=["true"])
        i = self.intent()
        self.commit_all("kit")
        self.put(self.ipath(i, "aidlc-state.md"), "# AI-DLC State\n\n### Next\n1. x\n")
        self.assertEqual(self.bash("git commit -am state").returncode, 0)
        self.commit_all("state")
        with open(os.path.join(self.top, "web", "app.js"), "a") as f:  # changes outside are never records
            f.write("// edit\n")
        self.assertEqual(self.bash("git commit -am web").returncode, 2)


# ---------------------------------------------------------------- KI-7: fingerprint
class Fingerprint(Helpers, Base):
    def test_stable_without_changes_and_changes_with_any_product_file(self):
        self.put("src/a.py", "a = 1\n")
        self.put("src/b.py", "b = 1\n")
        self.put(".gitignore", self.read(".gitignore") + "build/\n")
        self.commit_all("base")
        f0 = self.fp()
        self.assertRegex(f0, r"^[0-9a-f]{64}$")
        self.assertEqual(self.fp(), f0)  # the second run starts from the cached index
        self.assertTrue(os.path.exists(os.path.join(self.dir, ".aidlc-lean", "fingerprint.index")))
        self.assertEqual(self.fp(), f0)
        # records, kit files, change requests and ignored files do not count
        for path in ("aidlc-docs/x/aidlc-state.md", "aidlc-docs/x/" + PLAN, ".kiro/notes.md",
                     "aidlc-docs/contracts/changes/CR-a-1-x.md", "aidlc-docs/contracts/OWNERS", "build/out.bin"):
            self.put(path, "x\n")
        self.assertEqual(self.fp(), f0)
        self.put("src/a.py", "a = 2\n")  # a tracked file changes
        f1 = self.fp()
        self.assertNotEqual(f1, f0)
        self.put("src/a.py", "a = 1\n")  # content based: the same content gives the same value
        self.assertEqual(self.fp(), f0)
        os.remove(os.path.join(self.dir, "src", "b.py"))  # a tracked file is deleted
        f2 = self.fp()
        self.assertNotIn(f2, (f0, f1))
        self.put("src/b.py", "b = 1\n")
        self.assertEqual(self.fp(), f0)
        self.put("src/new.py", "n = 1\n")  # an untracked file appears
        f3 = self.fp()
        self.assertNotIn(f3, (f0, f1, f2))
        os.remove(os.path.join(self.dir, "src", "new.py"))
        self.assertEqual(self.fp(), f0)
        self.put("aidlc-docs/contracts/payments/api.yaml", "openapi: 3.0.0\n")  # contracts are product code
        f4 = self.fp()
        self.assertNotEqual(f4, f0)
        self.put("aidlc-docs/contracts/payments/api.yaml", "openapi: 3.1.0\n")
        self.assertNotEqual(self.fp(), f4)
        self.assertEqual([n for n in os.listdir(os.path.join(self.dir, ".aidlc-lean")) if n.startswith("fp-")], [])

    def test_value_depends_only_on_the_current_files(self):  # the cached index never leaks an old state
        self.put("src/a.py", "a = 1\n")
        self.commit_all("base")
        f0 = self.fp()
        for _ in range(2):
            os.remove(os.path.join(self.dir, "src", "a.py"))  # a file becomes a folder ...
            self.put("src/a.py/inner.py", "z = 1\n")
            self.assertNotEqual(self.fp(), f0)
            shutil.rmtree(os.path.join(self.dir, "src", "a.py"))  # ... and a file again
            self.put("src/a.py", "a = 1\n")
            self.assertEqual(self.fp(), f0)
        if hasattr(os, "geteuid") and os.geteuid() != 0:  # root reads anything
            self.put("src/locked.py", "s = 1\n")
            os.chmod(os.path.join(self.dir, "src", "locked.py"), 0)
            self.addCleanup(os.chmod, os.path.join(self.dir, "src", "locked.py"), 0o644)
            f1 = self.fp()
            self.assertNotEqual(f1, f0)
            self.assertEqual(self.fp(), f1)

    def test_no_objects_are_written_to_the_repository(self):
        self.commit_all("base")
        objects = os.path.join(self.dir, ".git", "objects")

        def count():  # the commit starts git's auto-maintenance, which takes objects/maintenance.lock for a moment
            return sum(1 for _, _, files in os.walk(objects) for f in files
                       if not f.endswith(".lock") and not f.startswith("maintenance"))

        before = count()
        self.put("src/big.txt", "y" * 200000)
        self.fp()
        self.assertEqual(count(), before)

    def test_session_start_and_status_compute_it_once(self):
        self.cfg(checks=["true"])
        self.ready()
        self.assertEqual(self.tool("verify").returncode, 0)
        shim = tempfile.mkdtemp(prefix="lean-shim-")
        self.addCleanup(shutil.rmtree, shim, True)
        log = os.path.join(shim, "calls.log")
        with open(os.path.join(shim, "git"), "w") as f:
            f.write('#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s"\nexec "%s" "$@"\n' % (log, shutil.which("git")))
        os.chmod(os.path.join(shim, "git"), 0o755)
        env = self.env()
        env["PATH"] = shim + os.pathsep + env.get("PATH", "")
        start = json.dumps({"session_id": "s", "hook_event_name": "SessionStart", "cwd": self.dir})
        for args, data in ((["hook", "SessionStart"], start), (["status"], None)):
            open(log, "w").close()
            p = subprocess.run(TOOL + args, cwd=self.dir, input=data, capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("Last verify: PASS", p.stdout)
            # the stage line uses the same value (a PASS on partial code: no unit's code generation is done yet)
            self.assertIn("- [-] Build and Test — verify PASS on partial code", p.stdout)
            self.assertNotIn("code changed since", p.stdout)
            with open(log) as f:
                calls = f.read().splitlines()
            self.assertEqual(len([c for c in calls if c.startswith("ls-files -c -o")]), 1, (args, calls))
            self.assertEqual(len([c for c in calls if "update-index --add" in c]), 1, (args, calls))

    def test_records_only_commit_needs_no_verify(self):  # ' M path' first in git status is parsed right
        self.cfg(checks=["true"])
        i = self.intent()
        self.commit_all("kit")
        self.say("noted")  # appends to the ledger: git status now starts with ' M aidlc-docs/audit/...'
        self.put(self.ipath(i, "aidlc-state.md"), "# AI-DLC State\n")
        self.assertEqual(self.bash("git commit -am records").returncode, 0)
        self.put("src/app.py", "x = 1\n")
        self.assertEqual(self.bash("git add -A && git commit -m code").returncode, 2)

    def test_contract_change_after_verify_needs_a_new_verify(self):
        self.cfg(checks=["true"])
        self.put("aidlc-docs/contracts/api.yaml", "openapi: 3.0.0\n")
        self.ready()
        self.assertEqual(self.tool("verify").returncode, 0)
        self.commit_all("v1")
        self.assertEqual(self.bash("git commit -am nothing-new").returncode, 0)
        self.put("aidlc-docs/contracts/api.yaml", "openapi: 3.1.0\n")
        self.assertIn("code changed since", self.tool("status").stdout)
        r = self.bash("git commit -am contract")
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked (verify)", r.stderr)
        self.assertEqual(self.tool("verify").returncode, 0)
        self.assertEqual(self.bash("git commit -am contract").returncode, 0)


# ---------------------------------------------------------------- KI-13: capped context
class ContextCaps(Helpers, Base):
    flags = ["--multi-team", "--team", "payments"]

    def test_session_start_and_resumed_turn_inject_a_bounded_block(self):
        i = self.intent()
        items = "\n".join("%d. %s" % (k, "detail " * 600) for k in range(1, 30))
        self.put(self.ipath(i, "aidlc-state.md"), "# AI-DLC State: x\n\n## Session notes\n### Next\n%s\n\n"
                 "### Open questions and blockers\n" % items)
        for n in range(1, 41):
            self.put("aidlc-docs/contracts/changes/CR-catalog-%d-c%d.md" % (n, n),
                     "# CR\n\n- Requested by team: catalog\n- Owner team: payments\n"
                     "- Paths: aidlc-docs/contracts/payments/api.yaml\n")
        out = self.hook("SessionStart", {}).stdout.rstrip("\n")
        self.assertLessEqual(len(out), 4000)
        self.assertLessEqual(len(out.splitlines()), 40)
        self.assertIn("[AI-DLC Lean] session context", out)
        self.assertIn("(truncated; run `python3 .kiro/aidlc-lean/aidlc_lean.py status`", out)
        self.assertIn("Change requests waiting for your team: CR-catalog-1, ", out)
        self.assertIn(" and 35 more", out)
        self.assertIn("CR-catalog-40", self.tool("status").stdout)  # the CLI status keeps everything
        turn = json.loads(self.read(".aidlc-lean/turn.json"))
        turn["ts"] = "2026-01-01T00:00:00.000Z"
        turn["sessions"] = {}
        self.put(".aidlc-lean/turn.json", json.dumps(turn))
        out = self.say("back again").stdout.rstrip("\n")
        self.assertIn("Resumed after", out)
        self.assertIn("(truncated; run", out)
        self.assertLessEqual(len(out), 4000 + len("[AI-DLC Lean] "))
        self.assertLessEqual(len(out.splitlines()), 40)

    def test_the_next_items_come_first_so_the_cap_cuts_progress_lines(self):
        i = self.intent()
        self.units(i, [("u%d" % k, "payments", "src/u%d/" % k) for k in range(8)])  # 39 Stage progress lines
        self.put(self.ipath(i, "aidlc-state.md"), "# AI-DLC State: x\n\n## Session notes\n### Next\n"
                 "1. Finish the refund endpoint\n2. Ask finance about VAT\n")
        start = self.hook("SessionStart", {}).stdout
        turn = json.loads(self.read(".aidlc-lean/turn.json"))
        turn["ts"], turn["sessions"] = "2026-01-01T00:00:00.000Z", {}
        self.put(".aidlc-lean/turn.json", json.dumps(turn))
        resumed = self.say("back again").stdout
        self.assertIn("Resumed after", resumed)
        for out in (start, resumed):
            lines = out.rstrip("\n").splitlines()
            self.assertLessEqual(len(lines), 40)
            self.assertTrue(lines[-1].startswith("(truncated; run"), lines[-1])
            self.assertIn("  From aidlc-state.md (Next):\n    1. Finish the refund endpoint\n    2. Ask finance about "
                          "VAT\n  Stage progress:\n    - [ ] Reverse Engineering\n", out)
            self.assertIn("- [ ] Code Generation (u0)", out)
            self.assertNotIn("- [ ] Release", out)  # the cap cut the end of the progress list
        st = self.tool("status").stdout  # not capped: everything, the progress list first as before
        self.assertIn("    - [ ] Release\n  From aidlc-state.md (Next):\n    1. Finish the refund endpoint\n", st)

    def test_short_context_is_not_cut(self):
        self.intent()
        out = self.hook("SessionStart", {}).stdout
        self.assertIn("Active intent", out)
        self.assertIn("- [ ] Release", out)
        self.assertNotIn("truncated", out)


# ---------------------------------------------------------------- KI-4, GB-14.9, GB-14.3, missed items, GB-14.2
class Commands(Helpers, Base):
    def test_doctor_counts_only_this_clones_session_starts(self):  # KI-4
        self.cfg(checks=["true"])
        self.hook("SessionStart", {})
        d = self.tool("doctor")
        self.assertEqual(d.returncode, 0, d.stdout)
        self.assertIn("hooks last ran in this clone at", d.stdout)
        self.commit_all("kit")
        clone = os.path.join(os.path.realpath(tempfile.mkdtemp(prefix="lean-clone-")), "b")
        self.addCleanup(shutil.rmtree, os.path.dirname(clone), True)
        subprocess.run(["git", "clone", "-q", self.dir, clone], capture_output=True)
        d = subprocess.run(TOOL + ["doctor"], cwd=clone, capture_output=True, text=True, env=self.env())
        self.assertEqual(d.returncode, 1, d.stdout)
        self.assertIn("hooks have never run here", d.stdout)
        subprocess.run(TOOL + ["hook", "SessionStart"], cwd=clone, capture_output=True, text=True, env=self.env(),
                       input=json.dumps({"session_id": "s2", "hook_event_name": "SessionStart", "cwd": clone}))
        d = subprocess.run(TOOL + ["doctor"], cwd=clone, capture_output=True, text=True, env=self.env())
        self.assertNotIn("hooks have never run here", d.stdout)

    def test_resume_note_is_per_kiro_session(self):  # GB-14.9
        self.intent()
        self.hook("UserPromptSubmit", {"session_id": "chat_A", "prompt": "hello from A"})
        self.hook("SessionStart", {"session_id": "chat_B"})
        self.hook("UserPromptSubmit", {"session_id": "chat_B", "prompt": "hello from B"})
        turn = json.loads(self.read(".aidlc-lean/turn.json"))
        turn["sessions"]["chat_A"] = "2026-01-01T00:00:00.000Z"  # chat A went quiet long ago; chat B is busy
        self.put(".aidlc-lean/turn.json", json.dumps(turn))
        self.assertNotIn("Resumed after", self.hook("UserPromptSubmit", {"session_id": "chat_B",
                                                                         "prompt": "B again"}).stdout)
        out = self.hook("UserPromptSubmit", {"session_id": "chat_A", "prompt": "A is back"}).stdout
        self.assertIn("Resumed after", out)
        self.assertIn("Active intent", out)
        self.assertNotIn("Resumed after", self.hook("UserPromptSubmit", {"session_id": "chat_A",
                                                                         "prompt": "A again"}).stdout)

    def test_audit_pack_resolves_the_intent_like_use(self):  # GB-14.3
        i = self.intent("feature-x")
        docs = os.path.join(self.dir, DOCS)
        before = sorted(os.listdir(docs))
        p = self.tool("audit", "pack", "feature-x")
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertTrue(os.path.exists(os.path.join(docs, i, "audit.md")))
        p = self.tool("audit", "pack", "no-such-intent")
        self.assertEqual(p.returncode, 1)
        self.assertIn("Unknown intent no-such-intent", p.stdout)
        self.assertEqual(sorted(os.listdir(docs)), before)

    def test_standard_release_without_checks_says_nothing_was_verified(self):
        i = self.ready()
        self.commit_all()
        r = self.tool("release")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Warning: no checks are configured", r.stdout)
        body = self.read(self.ipath(i, "operations/release.md"))
        self.assertIn("- checks: none configured (nothing was verified)", body)
        self.assertNotIn("verify: n/a", body)

    def test_status_after_the_release_is_approved_says_released(self):
        self.cfg(checks=["true"])
        self.ready()
        self.assertEqual(self.tool("verify").returncode, 0)
        self.commit_all()
        self.assertEqual(self.tool("release").returncode, 0)
        self.assertIn("request RELEASE", self.tool("status").stdout)
        self.approve("RELEASE")
        st = self.tool("status").stdout
        self.assertIn("- [x] Release — released: approved", st)
        self.assertIn("Next: nothing: this intent is released", st)
        self.assertIn("new <slug>", st)
        self.assertNotIn("aidlc_lean.py release`", st)

    def test_audit_verify_without_ledger_files_fails(self):
        shutil.rmtree(os.path.join(self.dir, DOCS, "audit"))
        v = self.tool("audit", "verify")
        self.assertEqual(v.returncode, 1, v.stdout)
        self.assertIn("no ledger files", v.stdout)
        self.assertIn("audit ledger is missing", self.tool("doctor").stdout)

    def test_use_logs_intent_switched(self):
        a = self.intent("first")
        b = self.intent("second")
        r = self.tool("use", "first")
        self.assertEqual(r.returncode, 0, r.stdout)
        ev = self.events("INTENT_SWITCHED")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["data"], {"from": b, "to": a})
        self.assertEqual(ev[0]["intent"], a)
        self.assertEqual(self.tool("use", "first").returncode, 0)
        self.assertEqual(self.events("INTENT_SWITCHED")[-1]["data"], {"from": a, "to": a})
        self.assertEqual(self.tool("audit", "pack", "second").returncode, 0)
        pack = self.read(self.ipath(b, "audit.md"))
        self.assertIn("## Intent switches (`use`) (1)", pack)
        self.assertIn("from %s to %s" % (b, a), pack)
        self.assertEqual(self.tool("use", "nope").returncode, 1)

    def test_the_code_generation_plan_comes_from_the_template_once(self):  # GB-14.2 (v0.1: `plan`)
        self.assertEqual(self.tool("stage", "start", "code-generation").returncode, 1)  # no active intent
        i = self.intent("big-change")
        p = self.tool("stage", "start", "code-generation")
        self.assertEqual(p.returncode, 0, p.stdout)
        text = self.read(self.ipath(i, PLAN))
        for placeholder in ("{{TITLE}}", "{{INTENT}}", "{{UNIT}}", "{{DATE}}", "{{STAGE}}"):
            self.assertNotIn(placeholder, text)
        source = self.read(".kiro/aidlc-lean/templates/code-generation-plan.md")
        if "{{TITLE}}" in source:
            self.assertIn("big change", text)
        self.put(self.ipath(i, PLAN), "# Plan: mine\n")
        p = self.tool("stage", "start", "code-generation")
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("Kept the existing", p.stdout)
        self.assertEqual(self.read(self.ipath(i, PLAN)), "# Plan: mine\n")
        usage = self.tool("--help").stdout
        self.assertIn("stage start <id> [--unit U]", usage)
        self.assertNotIn("\n  plan ", usage)
        self.assertEqual(self.tool("plan").returncode, 1)  # the v0.1 command is gone


class RegulatedCommands(Helpers, Base):
    flags = ["--regulated"]

    def test_release_without_checks_is_refused(self):
        i = self.ready()
        for sid in ("reverse-engineering", "user-stories", "units", "functional-design", "nfr-design",
                    "infrastructure-design"):  # Next follows the stage order: these come before the plan
            self.ok("stage", "skip", sid, "--reason", "not needed")
        self.assertIn("aidlc_lean.py stage start code-generation", self.tool("status").stdout)  # no plan yet
        self.ok("stage", "start", "code-generation")
        self.approve("PLAN")
        r = self.tool("release")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("no checks configured", r.stdout)
        self.assertFalse(self.exists(self.ipath(i, "operations/release.md")))

    def test_evidence_masks_secrets_and_verify_records_its_hash(self):  # GB-10
        i = self.intent()
        secrets = ["hunter2", "eyJhbGciOiJIUzI1NiJ9", "pa55word", "abcdefghijklmnopqrstuvwxyz0123456789",
                   "wJalrXUtnFEMI", "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"]
        lines = ['{"password": "hunter2"}', "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def",
                 "postgres://app:pa55word@db/x", "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
                 "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                 "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                 "-----BEGIN PRIVATE KEY-----", "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC", "-----END PRIVATE KEY-----"]
        self.put("emit.py", "print(%r)\n" % "\n".join(lines))
        self.cfg(checks=[sys.executable + " emit.py"])
        v = self.tool("verify")
        self.assertEqual(v.returncode, 0, v.stdout)
        ev = self.events("VERIFY")[-1]
        self.assertTrue(ev["data"]["evidence"].startswith(self.ipath(i, "construction/build-and-test/evidence/")))
        body = self.read(ev["data"]["evidence"])
        for s in secrets:
            self.assertNotIn(s, body)
            self.assertNotIn(s, self.read(ev["data"]["summary"]))
        self.assertIn("postgres://app:***@db/x", body)
        with open(os.path.join(self.dir, ev["data"]["evidence"]), "rb") as f:
            self.assertEqual(ev["data"]["evidence_sha256"], hashlib.sha256(f.read()).hexdigest())
        r = self.bash("git push --force https://app:pa55word@example.com/r.git")  # blocked: the ledger keeps it masked
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("pa55word", json.dumps(self.events("BLOCKED")))


# ---------------------------------------------------------------- GB-10: mask() patterns
class Masking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = load_kit_module()

    def masked(self, text, secret, keep=None):
        out = self.L.mask(text)
        self.assertNotIn(secret, out, text)
        if keep:
            self.assertIn(keep, out)
        return out

    def test_aws_secret_access_keys(self):
        key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        self.masked("AWS_SECRET_ACCESS_KEY=%s" % key, key, keep="AWS_SECRET_ACCESS_KEY=***")
        self.masked("aws_secret_access_key = %s" % key, key, keep="aws_secret_access_key = ***")
        self.masked("export AWS_SESSION_TOKEN=FwoGZXIvYXdzEJr", "FwoGZXIvYXdzEJr")
        self.masked("key id AKIAIOSFODNN7EXAMPLE", "IOSFODNN7EXAMPLE", keep="AKIA***")

    def test_json_style_passwords(self):
        self.masked('{"user": "bob", "password": "hunter2"}', "hunter2", keep='"password": "***"')
        self.masked("{'passwd': 'hunter 2'}", "hunter 2", keep="'passwd': '***'")
        self.masked('{"api_key":"sk-live-1"}', "sk-live-1", keep='"api_key":"***"')
        self.masked('{"password": "pa\\"ss word"}', "ss word")

    def test_authorization_bearer(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc-def_ghi"
        self.masked("Authorization: Bearer %s" % jwt, jwt, keep="Authorization: Bearer ***")
        self.masked('{"Authorization": "Bearer %s"}' % jwt, jwt)
        self.masked("curl -H 'authorization: token abcdef123456'", "abcdef123456")
        self.masked("retrying with bearer %s" % jwt, jwt)

    def test_url_credentials(self):
        self.masked("postgres://app:pa55word@db/x", "pa55word", keep="postgres://app:***@db/x")
        self.masked("git clone https://x-access-token:s3cr3tvalue@github.com/o/r.git", "s3cr3tvalue",
                    keep="https://x-access-token:***@github.com/o/r.git")
        self.assertEqual(self.L.mask("see https://example.com/a@b and http://host:8080/x"),
                         "see https://example.com/a@b and http://host:8080/x")

    def test_github_tokens(self):
        for token in ("ghp_" + "a1" * 18, "gho_" + "b2" * 18, "ghs_" + "c3" * 18,
                      "github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz0123456789ABCDEF"):
            prefix = "github_pat_" if token.startswith("github_pat_") else token[:4]
            self.masked("using %s now" % token, token[len(prefix):], keep=prefix + "***")

    def test_pem_private_key_blocks(self):
        pem = ("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAexamplekeymaterial\nAbCdEf0123456789+/xyz\n"
               "-----END RSA PRIVATE KEY-----")
        out = self.masked("before\n%s\nafter" % pem, "examplekeymaterial")
        self.assertNotIn("AbCdEf0123456789", out)
        self.assertIn("before", out)
        self.assertIn("after", out)
        self.masked("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n", "b3BlbnNzaC1rZXktdjEAAAAA")

    def test_earlier_patterns_still_masked_and_plain_output_untouched(self):
        self.masked("password=hunter2", "hunter2")
        self.masked("DB_PASSWORD=hunter2", "hunter2")
        self.masked("token: abc123", "abc123")
        plain = "tokens: 1234, max_tokens=100, secretary: Jane, 3 passed in 0.2s, key=value"
        self.assertEqual(self.L.mask(plain), plain)

    def test_long_lines_stay_fast(self):
        t0 = time.time()
        self.L.mask(("token_" * 3000) + "\n" + ("a." * 30000) + "\n" + ("x" * 200000) + "\n" + ("-a" * 30000))
        self.assertLess(time.time() - t0, 3.0)


class GuardHookDescription(unittest.TestCase):
    def test_description_matches_what_the_guard_does(self):
        with open(os.path.join(REPO, "kit", ".kiro", "hooks", "aidlc-lean-guard.json"), encoding="utf-8") as f:
            desc = json.load(f)["hooks"][0]["description"]
        self.assertNotIn("Reads are never held", desc)
        self.assertIn("Read tools are not checked", desc)
        self.assertIn("shell commands that touch the kit's records", desc)


if __name__ == "__main__":
    unittest.main()
