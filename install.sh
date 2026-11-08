#!/usr/bin/env bash
# Install AI-DLC Lean into a project for Kiro CLI (v3 engine).
# usage: ./install.sh <project-dir> [--regulated] [--multi-team] [--team NAME] [--with-pstack]
# The project is <project-dir>, the folder that gets .kiro/; it may be a subfolder of a bigger git repository.
# Re-running it updates the kit files; aidlc-docs/ (including aidlc-docs/lean.json) is kept as it is.
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
git rev-parse --show-toplevel >/dev/null 2>&1 || { echo "note: $TARGET is not a git repo; running git init"; git init -q; }
CFG_EXISTED=0
if [ -f "$CFG" ]; then CFG_EXISTED=1; fi
mkdir -p .kiro/hooks .kiro/steering .kiro/skills .kiro/aidlc-lean
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
# The kit folder is replaced as a whole, so templates that no longer ship (v0.1 SPEC.md, PLAN.md, ...) go too.
rm -rf .kiro/aidlc-lean && cp -R "$HERE/kit/.kiro/aidlc-lean" .kiro/aidlc-lean && rm -rf .kiro/aidlc-lean/__pycache__
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
# On a case-insensitive file system (macOS) git keeps the old name of a tracked kit file whose new name differs only
# in case (v0.1 templates/CR.md, now cr.md), and Linux clones then miss the new file. So drop from the git index every
# tracked path under .kiro/aidlc-lean/ that is not on disk with exactly that name; `git add -A` records the new names.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  python3 -I - <<'PY'
import os, subprocess, sys
listed = subprocess.run(["git", "ls-files", "-z", "--", ".kiro/aidlc-lean/"], stdout=subprocess.PIPE).stdout

def on_disk(path):  # each part listed with exactly this name (os.path.exists ignores case there)
    here = b"."
    for part in path.split(b"/"):
        try:
            if part not in os.listdir(here):
                return False
        except OSError:
            return False
        here = os.path.join(here, part)
    return True

gone = [p for p in listed.split(b"\0") if p and not on_disk(p)]
if gone:
    names = ", ".join(os.fsdecode(p) for p in gone)
    # -f: also when the old name has staged changes; its file is gone from disk, as `git add -A` would record
    if subprocess.run(["git", "rm", "--cached", "-q", "-f", "--"] + gone, env=dict(os.environ, GIT_LITERAL_PATHSPECS="1")).returncode == 0:
        print("Dropped from the git index (old kit names; `git add -A` records the current ones): " + names)
    else:
        print("WARNING: could not drop these old kit names from the git index; run `GIT_LITERAL_PATHSPECS=1 git rm --cached` on them "
              "before you commit: " + names, file=sys.stderr)
PY
fi
python3 .kiro/aidlc-lean/aidlc_lean.py init ${ARGS[@]+"${ARGS[@]}"}
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
