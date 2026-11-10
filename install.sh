#!/usr/bin/env bash
# Install AI-DLC Lean into a project for Kiro CLI (v3 engine).
# usage: ./install.sh <project-dir> [--regulated] [--multi-team] [--team NAME] [--with-pstack]
# The project is <project-dir>, the folder that gets .kiro/; it may be a subfolder of a bigger git repository.
# Re-running it updates the kit files; aidlc-docs/ (including aidlc-docs/lean.json) is kept as it is, and so are the
# templates a person changed or added in .kiro/aidlc-lean/templates/ (the kit's version goes to <name>.kit-new).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
USAGE="usage: $0 <project-dir> [--regulated] [--multi-team] [--team NAME] [--with-pstack]"
die() { echo "install.sh: $*" >&2; echo "$USAGE" >&2; exit 1; }
case "${1:-}" in -h|--help) echo "$USAGE"; exit 0 ;; esac
TARGET="${1:-}"
[ -n "$TARGET" ] || die "missing <project-dir>"
if [ ! -d "$TARGET" ]; then
  case "$TARGET" in -*) die "put <project-dir> first (got $TARGET)" ;; *) die "not a directory: $TARGET" ;; esac
fi
shift
# Check every option before anything is written, so a typo such as --regulate changes nothing.
PSTACK=0; WANT_REGULATED=0; WANT_MULTI_TEAM=0; ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --with-pstack) PSTACK=1 ;;
    --regulated) WANT_REGULATED=1; ARGS+=("$1") ;;
    --multi-team) WANT_MULTI_TEAM=1; ARGS+=("$1") ;;
    --team)
      if [ $# -lt 2 ] || [ -z "$2" ] || [ "${2#-}" != "$2" ]; then die "--team needs a team name"; fi
      ARGS+=("$1" "$2"); shift ;;
    -h|--help) echo "$USAGE"; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done
command -v python3 >/dev/null || { echo "python3 (3.8+) is required" >&2; exit 1; }
cd "$TARGET"
# `aidlc_lean.py init` keeps the config next to .kiro/, in the project folder, which is not always the git top level.
CFG="$(pwd -P)/aidlc-docs/lean.json"
if [ -f aidlc/lean.json ] && [ ! -f "$CFG" ]; then
  # A v0.1 project. This version does not read aidlc/lean.json, so installing would quietly drop its mode, checks
  # and protected_paths. The config belongs to the team: a person moves it, the installer does not.
  {
    echo "install.sh: aidlc/lean.json is an AI-DLC Lean v0.1 config, and this version reads aidlc-docs/lean.json."
    echo "  Installing now would drop its mode, checks and protected_paths, so nothing was changed."
    echo "  Move it yourself (e.g. mkdir -p aidlc-docs && git mv aidlc/lean.json aidlc-docs/lean.json), check the"
    echo "  paths in it (contracts_dir, fingerprint_exclude), commit, and re-run this installer."
  } >&2
  exit 1
fi
IS_GIT=1
git rev-parse --show-toplevel >/dev/null 2>&1 || IS_GIT=0
CFG_EXISTED=0
if [ -f "$CFG" ]; then CFG_EXISTED=1; fi
# The kit folder step. `check` only reads: every template and the manifest, and whether every file this installer
# writes can be written. `apply` decides the same way and changes things. The kit's own files are replaced;
# templates are kept where a person changed or added them.
# -I: a program read from stdin would otherwise import from the project folder (e.g. a json.py there).
kit_step() {
python3 -I - "$1" "$HERE" "$PSTACK" "$IS_GIT" "$WANT_MULTI_TEAM" <<'PY'
import hashlib, json, os, re, shutil, subprocess, sys
MODE, HERE, PSTACK, IS_GIT, MULTI = sys.argv[1], sys.argv[2], sys.argv[3] == "1", sys.argv[4] == "1", \
    sys.argv[5] == "1"
KIT, DST = os.path.join(HERE, "kit", ".kiro", "aidlc-lean"), os.path.join(".kiro", "aidlc-lean")
TDIR, MANIFEST, NEW = os.path.join(DST, "templates"), os.path.join(DST, "kit-templates.sha256"), ".kit-new"
HEADER = ["# Written by install.sh: the sha256 of each template as the kit installed it, and as <name>.kit-new the kit",
          "# version already offered next to a template a person changed. A re-install replaces a template that still",
          "# has its sha256, and offers a kit version as <name>.kit-new only once."]
# v0.1 template names, exact case: v0.2 renamed CR.md and DECISIONS.md to lower case and dropped the others
V01 = {"SPEC.md", "PLAN.md", "STATE.md", "REVIEW.md", "UNITS.md", "DECISIONS.md", "RELEASE.md", "AUDIT-PACK.md", "CR.md"}
# the templates of v0.2.0, which wrote no kit-templates.sha256
V02 = {"aidlc-state.md": "8477cd7b6d906b45d2f3aa84def0a6ea8f5413f9c5af2204782c2428aba3b92f",
       "application-design.md": "6d37d3efe2f8abe76becb3ac2fb5fae0d98e433a80db6fe42fac74f30f885284",
       "architecture.md": "c243197004d414cd8f6008715ad29995a83e249bc2d51d83092e8699027f5555",
       "code-generation-plan.md": "ed49480e4206003374c5800d7b2fcf1e7a155a6b3e2e00b7291691d124d8c032",
       "cr.md": "92bbd0e0bed5a48c732fbccf489824aaf31628b4dbd42fdea902a8774b814100",
       "decisions.md": "8442fbfa58aee12e96e4a17161543f211eb04cbdd0b9b27c23d07242dcc162ce",
       "functional-design.md": "26ae1d2267037566f3b8511d8b355ded0ebf389e07dbe3c722bcdd2fefaa87a0",
       "infrastructure-design.md": "2f8ffc0a90d3a5527e26e477a321dfce8dad94785606baf69d3cf6cd49d7b4aa",
       "lean.json": "12e3d40c555668407b197c42c7ac9d3f1c6398598618ffc0becb41072884d8e6",
       "nfr-design.md": "24217b500575921cc33f3236c01e627d1df62b3b6280498e338c19548b5eab2f",
       "requirements.md": "223c9d918cd7a0231710df9b07e3074a4450ce3b091725c09a5abe6924394c71",
       "stories.md": "c77af2d96056b0a1484ba1f0d4bb80a6cb6f60f6f87850f254f7135d54ceaa28",
       "unit-of-work.md": "82d13c12a2acec365f0155592f02e82f2c117079de0994f02b4b2ce91cb53704"}


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def files(d):  # file names exactly as listed (os.path.exists ignores case on macOS); no dotfiles such as .DS_Store
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d) if not n.startswith(".") and os.path.isfile(os.path.join(d, n)))


def stop(problem, then=""):
    if MODE == "check":
        print("install.sh: %s; nothing was changed.%s" % (problem, then), file=sys.stderr)
    else:  # a change since `check`: the shell's exit trap says that the install stopped part way
        print("install.sh: %s." % problem, file=sys.stderr)
    sys.exit(1)


# 1. Read everything and decide, before anything is changed.
try:
    kit = {n: sha(os.path.join(KIT, "templates", n)) for n in files(os.path.join(KIT, "templates"))}
    names = files(TDIR)
    digests = {n: sha(os.path.join(TDIR, n)) for n in names}
    has_manifest, recorded, ignored = os.path.isfile(MANIFEST), {}, False
    if has_manifest:
        with open(MANIFEST, "rb") as f:
            raw = f.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:  # e.g. a comment saved in another encoding: the records are ASCII
            text, ignored = raw.decode("utf-8", "replace"), True
        for line in text.splitlines():
            m = re.match(r"([0-9a-f]{64})  (\S+)$", line.rstrip())
            if m:
                recorded[m.group(2)] = m.group(1)
            elif line.strip() and not line.startswith("#"):
                ignored = True
except OSError as e:
    stop("cannot read %s (%s)" % (e.filename, e.strerror))
# A v0.1 install wrote no manifest and used other names (lean.json is a v0.1 name too, and still shipped). Only there
# are files with v0.1 names, and lean.json, the kit's; in a later install a file with a v0.1 name is the team's.
later = (set(V02) | set(kit)) - {"lean.json"}
v01_install = not has_manifest and any(n in V01 for n in names) and not any(n in later for n in names)


def kits(name, digest):  # a version of this template the kit installed, unchanged since
    return digest in (recorded.get(name), V02.get(name)) or (v01_install and name in kit)


old, added, writes, offers, changed, collided = [], [], {}, {}, [], []
for n in names:
    if n.endswith(NEW) or n in kit:
        continue
    if (v01_install and n in V01) or kits(n, digests[n]):
        old.append(n)
    else:
        added.append(n)
by_case = {n.lower(): n for n in names if n not in old and not n.endswith(NEW)}
for n, digest in sorted(kit.items()):
    src = os.path.join(KIT, "templates", n)
    other = by_case.get(n.lower())
    if n not in digests and other and other != n and os.path.exists(os.path.join(TDIR, n)):
        # A case-insensitive file system: the team's file `other` is this kit file too. Never write through it;
        # offer the kit's version once, as for a changed template.
        added.remove(other)
        if digests[other] != digest:
            offers[n] = digest
            if n + NEW in digests or recorded.get(n + NEW) != digest:
                writes[n + NEW] = src
                collided.append((other, n))
    elif n not in digests or digests[n] == digest or kits(n, digests[n]):
        if digests.get(n) != digest:
            writes[n] = src
    else:  # a person changed it: offer the kit's version once (again while the earlier copy is still there)
        offers[n] = digest
        if n + NEW in digests or recorded.get(n + NEW) != digest:
            writes[n + NEW] = src
            changed.append(n)
stale = [n for n in names if n.endswith(NEW) and n not in writes]  # merged or no longer needed
if MODE == "check":
    def blocker(d):  # None if this installer can add to and delete from folder d, or create it; else what stops it
        d = d or "."
        while not os.path.isdir(d):  # not there yet: its nearest existing folder must take a new entry
            if os.path.lexists(d):
                return d  # a file where a folder must be
            d = os.path.dirname(d) or "."
        return None if os.access(d, os.W_OK | os.X_OK) else d

    def file_blocker(p):  # written in place (cp, shutil.copy, an append) or created
        if os.path.lexists(p):
            return None if os.access(p, os.W_OK) else p
        return blocker(os.path.dirname(p))

    def tree_blocker(p):  # rm -rf, then copied again (or copied for the first time)
        if not os.path.lexists(p):
            return blocker(os.path.dirname(p))
        bad = []
        for d, _, _ in os.walk(p, onerror=lambda e: bad.append(e.filename)):
            if not os.access(d, os.W_OK | os.X_OK):
                bad.append(d)
        return bad[0] if bad else blocker(os.path.dirname(p))

    def model(p):
        with open(p, encoding="utf-8", errors="replace") as f:
            return next((line[6:].strip() for line in f if line.startswith("model:")), "")

    def listing(d):
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    cfg_path = os.path.join("aidlc-docs", "lean.json")
    cfg = {}
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError) as e:
            stop("aidlc-docs/lean.json is not valid JSON (%s)" % e, " Fix it, then run this installer again.")
    kiro, pack = os.path.join(HERE, "kit", ".kiro"), os.path.join(HERE, "kit-pstack", ".kiro")
    skills = os.path.join(".kiro", "skills")
    files_ = [os.path.join(".kiro", "hooks", n) for n in files(os.path.join(kiro, "hooks"))
              if n.startswith("aidlc-lean-") and n.endswith(".json")]
    files_ += [os.path.join(".kiro", "steering", "aidlc-lean.md"), MANIFEST]
    files_ += [os.path.join(DST, n) for n in os.listdir(KIT) if n not in ("templates", "__pycache__")]
    files_ += [os.path.join(TDIR, n) for n in writes]
    trees = [os.path.join(skills, n) for n in listing(os.path.join(kiro, "skills")) if n.startswith("aidlc-lean-")]
    gone = [os.path.join(TDIR, n) for n in old + stale]
    gone_trees = [os.path.join(skills, n) for n in ("aidlc-lean-spec", "aidlc-lean-build")]
    pack_files = os.path.exists(os.path.join(".kiro", "steering", "aidlc-lean-pstack.md")) or any(
        n.startswith("pstack-") for n in listing(skills))
    if PSTACK:
        files_.append(os.path.join(".kiro", "steering", "aidlc-lean-pstack.md"))
        trees += [os.path.join(skills, n) for n in listing(os.path.join(pack, "skills")) if n.startswith("pstack-")]
        gone.append(os.path.join(".kiro", "agents", "lean-reviewer-gpt.md"))
        for n in files(os.path.join(pack, "agents")):
            dst = os.path.join(".kiro", "agents", n)
            if not os.path.isfile(dst) or model(dst) == model(os.path.join(pack, "agents", n)):  # else kept
                files_.append(dst)
    if PSTACK or pack_files:
        files_.append(os.path.join(DST, "LICENSE-pstack"))
    # What `lean init` writes: lean.json when there is none, the ledger, this clone's state (all replaced through a
    # temp file in the same folder, or appended to), .gitignore while it lacks `.aidlc-lean/`, and in multi-team
    # mode the contracts folder with OWNERS and changes/.
    folders = ["aidlc-docs", os.path.join("aidlc-docs", "audit"), ".aidlc-lean"]
    files_ += [os.path.join("aidlc-docs", "audit", n) for n in files(os.path.join("aidlc-docs", "audit"))]
    try:
        with open(".gitignore", encoding="utf-8", errors="replace") as f:
            ignored_local = ".aidlc-lean/" in f.read()
    except OSError:
        ignored_local = False
    if not ignored_local:
        files_.append(".gitignore")
    if cfg.get("multi_team") if cfg else MULTI:
        contracts = str(cfg.get("contracts_dir") or os.path.join("aidlc-docs", "contracts")).rstrip("/")
        folders += [contracts, os.path.join(contracts, "changes")]
    if not IS_GIT:
        folders.append(".")  # git init
    found = [file_blocker(p) for p in files_] + [tree_blocker(p) for p in trees] + [blocker(d) for d in folders]
    found += [blocker(os.path.dirname(p)) for p in gone if os.path.lexists(p)]
    found += [tree_blocker(p) for p in gone_trees if os.path.lexists(p)]
    bad = list(dict.fromkeys(p for p in found if p))
    if bad:
        stop("cannot write %s (permission denied)" % (", ".join(bad[:5]) + (
            " and %d more" % (len(bad) - 5) if len(bad) > 5 else "")),
             " Make %s writable, then run this installer again." % ("it" if len(bad) == 1 else "them"))
    sys.exit(0)
# 2. Change things.
removed = []


def remove(path):
    os.remove(path)
    removed.append(path)


os.makedirs(TDIR, exist_ok=True)
for name in os.listdir(KIT):  # the kit's own files; others here (LICENSE-pstack, the team's) are left alone
    src, dst = os.path.join(KIT, name), os.path.join(DST, name)
    if name in ("templates", "__pycache__"):
        continue
    if os.path.isdir(src):
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    else:
        shutil.copy(src, dst)
for d, _, fns in os.walk(os.path.join(DST, "__pycache__")):
    removed += [os.path.join(d, fn) for fn in fns]
shutil.rmtree(os.path.join(DST, "__pycache__"), ignore_errors=True)
for n in old + stale:  # first, so that writing cr.md cannot land in a v0.1 CR.md on a case-insensitive file system
    remove(os.path.join(TDIR, n))
for n, src in sorted(writes.items()):
    shutil.copy(src, os.path.join(TDIR, n))
with open(MANIFEST, "w", encoding="utf-8") as f:
    f.write("\n".join(HEADER) + "\n")
    f.writelines("%s  %s\n" % (digest, n) for n, digest in sorted(kit.items()))
    f.writelines("%s  %s%s\n" % (digest, n, NEW) for n, digest in sorted(offers.items()))
T = TDIR + "/"
if ignored:
    print("note: %s had lines that are neither `<sha256>  <name>` records nor UTF-8 comments; they were ignored, "
          "and the file was written again without them." % MANIFEST)
if old:
    print("Removed old kit templates (the kit no longer ships them): " + ", ".join(T + n for n in old))
for n in changed:
    print("Kept %s%s: it is not the version the kit installed, so a person changed it. The kit's new version is in "
          "%s%s%s: compare the two, merge by hand, then delete the %s file (a re-install offers this kit version only "
          "once)." % (T, n, T, n, NEW, NEW))
for other, n in collided:
    print("Kept %s%s: on this file system it is the same file as the kit's %s, so it was not overwritten. The kit's "
          "version is in %s%s%s." % (T, other, n, T, n, NEW))
for n in added:
    print("Kept %s%s: the kit does not ship it (your team's template)." % (T, n))
# On a case-insensitive file system (macOS) git keeps the old name of a tracked kit file whose new name differs only
# in case (v0.1 templates/CR.md, now cr.md), and Linux clones then miss the new file. So drop from the git index the
# tracked kit files this run removed that are not on disk with exactly that name; `git add -A` records the new names.
if subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL).returncode != 0:
    sys.exit(0)
listed = subprocess.run(["git", "ls-files", "-z", "--", DST + "/"], stdout=subprocess.PIPE).stdout
ours = {os.fsencode(p).lower() for p in removed}


def on_disk(path):  # each part listed with exactly this name
    here = b"."
    for part in path.split(b"/"):
        try:
            if part not in os.listdir(here):
                return False
        except OSError:
            return False
        here = os.path.join(here, part)
    return True


gone = [p for p in listed.split(b"\0") if p and p.lower() in ours and not on_disk(p)]
if gone:
    names = ", ".join(os.fsdecode(p) for p in gone)
    # -f: also when the old name has staged changes; its file is gone from disk, as `git add -A` would record
    if subprocess.run(["git", "rm", "--cached", "-q", "-f", "--"] + gone, env=dict(os.environ, GIT_LITERAL_PATHSPECS="1")).returncode == 0:
        print("Dropped from the git index (old kit names; `git add -A` records the current ones): " + names)
    else:
        print("WARNING: could not drop these old kit names from the git index; run `GIT_LITERAL_PATHSPECS=1 git rm --cached` on them "
              "before you commit: " + names, file=sys.stderr)
PY
}
kit_step check  # stops here, before anything is changed, if a file cannot be read or written
trap 'rc=$?; if [ "$rc" -ne 0 ]; then echo "install.sh: stopped part way (see the error above); some kit files may already be the new ones. Fix the problem and run this installer again (re-running it is safe)." >&2; fi' EXIT
[ "$IS_GIT" = 1 ] || { echo "note: $TARGET is not a git repo; running git init"; git init -q; }
mkdir -p .kiro/hooks .kiro/steering .kiro/skills .kiro/aidlc-lean
kit_step apply
cp "$HERE/kit/.kiro/hooks/"aidlc-lean-*.json .kiro/hooks/
cp "$HERE/kit/.kiro/steering/aidlc-lean.md" .kiro/steering/
for d in "$HERE/kit/.kiro/skills/"aidlc-lean-*; do rm -rf ".kiro/skills/$(basename "$d")"; cp -R "$d" .kiro/skills/; done
# v0.1 skills that v0.2 replaced: left in place, they would still load and describe the old flow.
for old in aidlc-lean-spec aidlc-lean-build; do
  if [ -e ".kiro/skills/$old" ] && [ ! -e "$HERE/kit/.kiro/skills/$old" ]; then
    rm -rf ".kiro/skills/$old"
    echo "Removed .kiro/skills/$old/ (a v0.1 skill; aidlc-lean-inception and aidlc-lean-construction replace it)."
  fi
done
model_of() { awk '/^model:/ { sub(/^model:[ \t]*/, ""); sub(/[ \t\r]+$/, ""); print; exit }' "$1"; }
tools_of() { awk '/^tools:/ { sub(/[ \t\r]+$/, ""); print; exit }' "$1"; }
if [ "$PSTACK" = 1 ]; then
  mkdir -p .kiro/agents
  cp "$HERE/kit-pstack/.kiro/steering/aidlc-lean-pstack.md" .kiro/steering/
  for d in "$HERE/kit-pstack/.kiro/skills/"pstack-*; do rm -rf ".kiro/skills/$(basename "$d")"; cp -R "$d" .kiro/skills/; done
  # Subagents: touch only the pack's own files. Other .kiro/agents/lean-*.md files belong to the team.
  if [ -f .kiro/agents/lean-reviewer-gpt.md ]; then
    rm -f .kiro/agents/lean-reviewer-gpt.md
    echo "Removed .kiro/agents/lean-reviewer-gpt.md (from an older pack; lean-reviewer-k3.md replaces it)."
  fi
  for src in "$HERE/kit-pstack/.kiro/agents/"lean-*.md; do
    dst=".kiro/agents/$(basename "$src")"
    if [ -f "$dst" ] && [ "$(model_of "$dst")" != "$(model_of "$src")" ]; then
      # A person changed the model (step 5 below asks them to): keep their file.
      mine="$(model_of "$dst")"; shipped="$(model_of "$src")"
      echo "Kept $dst: its model (${mine:-none, the session model}) differs from the shipped one (${shipped:-none, the session model}), so a person set it."
      if [ "$(tools_of "$dst")" != "$(tools_of "$src")" ]; then
        echo "  Its tools line also differs from the shipped one ($(tools_of "$src"))."
      fi
      echo "  To take the new version, compare it with $src and edit by hand, or delete your copy and re-run."
    else
      cp "$src" "$dst"
    fi
  done
  echo "Installed the pstack quality pack (10 skills, 3 subagents: lean-worker, lean-reviewer-opus, lean-reviewer-k3)."
fi
# pstack-derived files must keep their MIT notice, also when a re-install leaves out --with-pstack.
for p in .kiro/skills/pstack-* .kiro/steering/aidlc-lean-pstack.md; do
  [ -e "$p" ] || continue
  cp "$HERE/kit-pstack/LICENSE-pstack" .kiro/aidlc-lean/LICENSE-pstack
  if [ "$PSTACK" = 0 ]; then
    echo "Kept the pstack MIT notice (.kiro/aidlc-lean/LICENSE-pstack) because pstack pack files are installed. Re-run with --with-pstack to update the pack."
  fi
  break
done
# With a lean.json already there, init would only warn about --regulated / --multi-team; this installer says it below.
INIT_ARGS=()
for a in ${ARGS[@]+"${ARGS[@]}"}; do
  if [ "$CFG_EXISTED" = 1 ] && { [ "$a" = --regulated ] || [ "$a" = --multi-team ]; }; then continue; fi
  INIT_ARGS+=("$a")
done
python3 .kiro/aidlc-lean/aidlc_lean.py init ${INIT_ARGS[@]+"${INIT_ARGS[@]}"}
if [ "$CFG_EXISTED" = 1 ] && { [ "$WANT_REGULATED" = 1 ] || [ "$WANT_MULTI_TEAM" = 1 ]; }; then
  # init never changes an existing lean.json: say so instead of leaving the mode flags silently unused.
  # -I: a program read from stdin would otherwise import from the project folder (e.g. a json.py there).
  python3 -I - "$CFG" "$WANT_REGULATED" "$WANT_MULTI_TEAM" >&2 <<'PY'
import json, os, sys
path, want = sys.argv[1], {"regulated": sys.argv[2] == "1", "multi_team": sys.argv[3] == "1"}
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
flags = {"regulated": "--regulated", "multi_team": "--multi-team"}
mode = ", ".join("%s: %s" % (k, "true" if cfg.get(k) else "false") for k in flags)
skipped = [flags[k] for k in flags if want[k] and not cfg.get(k)]
shown = os.path.relpath(path)
if skipped:
    print("WARNING: %s already exists, so it was kept as it is (%s): %s was NOT applied."
          % (shown, mode, " and ".join(skipped)))
    print('  To change the mode, edit "regulated" / "multi_team" in %s yourself (the agent cannot) and commit it.' % shown)
    if "--multi-team" in skipped:
        owners = (cfg.get("contracts_dir") or "aidlc-docs/contracts").rstrip("/") + "/OWNERS"
        print("  For multi-team, then re-run this installer with --team NAME so it creates %s." % owners)
else:
    print("note: %s already exists and was kept as it is (%s)." % (shown, mode))
PY
fi
echo
echo "Next:"
echo "  1. Edit aidlc-docs/lean.json: set \"checks\" (e.g. [\"pytest -q\"]) and \"protected_paths\" (e.g. [\"tests/acceptance/**\"])."
echo "  2. Commit .kiro/, aidlc-docs/ and .gitignore (not .aidlc-lean/, which is per clone and gitignored)."
echo "  3. Start Kiro CLI in this folder: kiro-cli --v3   (trust the workspace when asked)."
echo "  4. In Kiro, allow the command 'python3 .kiro/aidlc-lean/aidlc_lean.py' when it first asks."
if [ "$PSTACK" = 1 ]; then
  echo "  5. Reviewer models are set in .kiro/agents/lean-reviewer-*.md (model: ...); change them if your Kiro install has other models enabled. A re-install keeps a file whose model you changed."
fi
