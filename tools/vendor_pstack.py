#!/usr/bin/env python3
"""Regenerate kit-pstack/ (the optional AI-DLC Lean quality pack) from a local pstack checkout.

usage: python3 tools/vendor_pstack.py [PSTACK_DIR]
default PSTACK_DIR: the newest version folder under ~/.claude/plugins/cache/cursor-plugins/pstack/

The pstack version in the card footers is read from PSTACK_DIR's plugin.json
(.claude-plugin/plugin.json or plugin.json). Eight cards are copied with small mechanical edits: the
skill is renamed to pstack-<name>, Cursor/Claude Code adapter lines are dropped, and references to
cards that are not shipped are rewritten. interrogate and swarm get Kiro-specific SKILL.md files
written here; interrogate's reference files are copied with the edits in REF_EDITS.

Every edit must apply, and every generated file is scanned for FORBIDDEN text, for the AI-DLC Lean v0.1
names that v0.2 retired (RETIRED), and for references to pstack skills that are not shipped. These are
explicit checks, not asserts, so `python3 -O` runs them too. The pack is built in a temporary folder next
to kit-pstack/ and replaces it only after every check passed, so a failed run leaves the old pack as it
was. pstack is MIT licensed (c) 2026 Lauren Tan.
"""
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "kit-pstack")
CACHE = "~/.claude/plugins/cache/cursor-plugins/pstack"
USAGE = "usage: python3 tools/vendor_pstack.py [PSTACK_DIR]"
LICENSE_LINES = ("MIT License", "Copyright (c) 2026 Lauren Tan")  # the footer below repeats these
FOOTER = ("\n\n---\n\n*Adapted from pstack %s (MIT License, (c) 2026 Lauren Tan, "
          "https://github.com/cursor/plugins/tree/main/pstack) for AI-DLC Lean on Kiro CLI. "
          "See `.kiro/aidlc-lean/LICENSE-pstack`.*\n")
ADAPTER_RE = re.compile(r"^In Claude Code, read \[the Claude Code adapter\].*\n\n?", re.M)
# Text that must not reach the pack: other hosts and their tool names, and pstack features Lean does not ship.
FORBIDDEN = ("Claude Code", "Cursor", "~/.cursor", "disable-model-invocation", "pstack-models", "bugbot",
             "Read, Grep, Glob")

# AI-DLC Lean v0.1 names that v0.2 replaced with the AI-DLC layout under aidlc-docs/<intent>/ (requirements.md,
# application-design.md, <unit>-code-generation-plan.md, aidlc-state.md, ...). None of them may come back.
RETIRED = ("aidlc/", "SPEC.md", "PLAN.md", "STATE.md", "REVIEW.md", "UNITS.md", "DECISIONS.md", "RELEASE.md",
           "AUDIT-PACK.md")

COPIED = {
    "principle-prove-it-works": [
        # Not in build-and-test/evidence/: that folder holds the evidence files `lean verify` writes in regulated mode.
        ("(the **show-me-your-work** skill)",
         "(in AI-DLC Lean: keep it under `aidlc-docs/<intent>/construction/build-and-test/` and note it in the "
         "intent's decisions.md)"),
    ],
    "principle-test-behavior-not-implementation": [],
    "principle-boundary-discipline": [],
    "principle-fix-root-causes": [],
    "principle-sequence-verifiable-units": [
        ("The sequencing complement to the **prove-it-works** principle skill, which keeps each check real, and the "
         "**build-the-lever** principle skill, which makes the per-unit check cheap.",
         "The sequencing complement to the **pstack-principle-prove-it-works** skill, which keeps each check real."),
    ],
    "principle-model-the-domain": [],
    "blast-radius": [
        ("Companion to `how` and `why`. `how` tells you what the code does. `why` tells you why it's shaped that way. "
         "Blast radius tells you what it breaks somewhere else.",
         "Reading the code tells you what it does. Blast radius tells you what a change breaks somewhere else."),
        ("Use `why` step 2 to pull the PR and commits.",
         "Read the PR description and `git log -p` for the touched files."),
        ("Same rules as `why`. Cite", "Cite"),
        ("6. For a big or wide change, run it as an `arena`. Ask more than one model the same question and merge the answers.",
         "6. For a big or wide change, ask more than one model: dispatch `lean-reviewer-opus` and `lean-reviewer-k3` in "
         "parallel with the same question and the diff (skill `pstack-swarm`) and merge the answers."),
        ("Write it through `unslop`, cite real code,", "Write it plainly, without filler, cite real code,"),
    ],
    "correct": [
        ("Use for /correct.", "Use when the human corrects the same kind of mistake twice."),
    ],
}
APPEND = {
    "correct": ("\n\n## In AI-DLC Lean\n\nYou cannot edit `aidlc-docs/lean.json` or the hooks. When the fix for a mistake "
                "class is a new check or a blocked command, write the exact `checks` or `deny_commands` entry and ask the "
                "human to add it. Put the rule table in `AGENTS.md`."),
}
REFS = ("reviewer-prompt.md", "rubric.md", "code-quality-review.md", "lead-judgment.md")
REF_EDITS = {
    "rubric.md": [("(Read, Grep, Glob)", "(read_file, grep_search, file_search)")],
    # One brief file for both reviewers, named in a short prompt (see INTERROGATE, Steps 3 and 4).
    "reviewer-prompt.md": [("Build each reviewer subagent's prompt from this template, filling in the placeholders.",
                            "Build the reviewer brief from this template, filling in the placeholders. In AI-DLC Lean the "
                            "lead writes it once to `aidlc-docs/<intent>/construction/build-and-test/review-brief.md`, "
                            "and each reviewer's prompt only names that file.")],
}
SHIPPED = set(COPIED) | {"interrogate", "swarm"}

INTERROGATE = """---
name: pstack-interrogate
description: Multi-model adversarial review of a change. Use at the AI-DLC Lean review step, or for "interrogate", "adversarial review", "multi-model review", "stress test this". Two reviewers on different models challenge the change and you write a synthesized verdict to the intent's review.md.
---

# Interrogate: multi-model review

Dispatch one reviewer per model to review a change adversarially. The adversarial signal comes from model diversity, not assigned personas. The deliverable is a synthesized verdict in `aidlc-docs/<intent>/construction/build-and-test/review.md`. Do NOT auto-apply changes while reviewing.

## Step 1, Scope

- The diff: `git diff <base>..HEAD`, where base is the commit before the intent's work (find it with `git log`), or the files the human names.
- The intent's pages under `aidlc-docs/<intent>/`: `inception/requirements/requirements.md` (goal, AC-n, NFR targets), `inception/application-design/application-design.md` if it exists, and per unit the design pages under `construction/<unit>/` (BR-n) and `construction/plans/<unit>-code-generation-plan.md` (the test for each AC and BR).

## Step 2, Intent

State the intent in one paragraph from the requirements goal, the acceptance criteria and the commit messages. If you are unsure about the intent, ask the human before proceeding.

## Step 3, Write the brief once

Write one brief for both reviewers to `aidlc-docs/<intent>/construction/build-and-test/review-brief.md`: the template in `references/reviewer-prompt.md` with its placeholders filled in.
- `{INTENT}`: the intent paragraph.
- `{DIFF_OR_FILES}`: the full diff plus the acceptance criteria table from requirements.md. The reviewers have read tools only (no shell, no writes), so they cannot run git or tests: put any test output they need in the brief.
- `{RUBRIC_CONTENTS}`: the contents of `references/rubric.md`, followed by the AI-DLC Lean lens below.
- `{CODE_QUALITY_CONTENTS}`: the contents of `references/code-quality-review.md`.

The AI-DLC Lean lens:
- Every AC and BR has the test its code-generation plan maps it to, and that test asserts the expected value.
- Authorization covers every new or changed endpoint, including admin and maintenance routes.
- Nothing outside the approved requirements and design changed without a decisions.md line.
- Contract changes match approved change requests.

The brief records what the reviewers were shown: do not change it after the dispatch, and commit it with review.md.

## Step 4, Dispatch the reviewers

In ONE message, call `invoke_sub_agent` twice:

- `lean-reviewer-opus`
- `lean-reviewer-k3`

Give both the same short prompt that names the brief, for example: "Adversarial review: read aidlc-docs/<intent>/construction/build-and-test/review-brief.md and follow it. Return your findings in your reply." Never paste the brief into the prompt. Kiro starts a subagent only after its call has been written out in full, so a long prompt starts the second reviewer late and spends the brief's tokens twice; with short prompts both start together.

Their models are fixed in `.kiro/agents/`. If one fails to start, for example because that model is not enabled on this Kiro install, say so and continue with the other.

Each reviewer returns its findings in its reply. It can read and search the repo for context, but it cannot change files or run commands.

## Step 5, Synthesize

As results come back, build one picture.
- Merge findings that describe the same issue differently, and note which models raised each.
- Findings that both models raised independently are the highest signal.
- Read a lone model's finding, but weight it accordingly.
- Note disagreements. If one model flags something and the other explicitly says the opposite, that is context for the verdict.
- When a reviewer names a command or test that would confirm a finding, run it yourself and use the result.

## Step 6, Lead judgment

You are the lead reviewer: a pragmatic senior engineer, not a neutral aggregator. Read `references/lead-judgment.md`. Put every finding in one bucket, with the model(s) that raised it and a one-line rationale:

- **Act on**: real issues affecting correctness, security or maintainability; they would block a real PR.
- **Consider**: legitimate, but not clearly worth fixing now.
- **Noted**: valid but not actionable now.
- **Dismissed**: wrong, nitpicky or missing context, with a brief reason.

## Output

Write `aidlc-docs/<intent>/construction/build-and-test/review.md` with these sections: Intent, Reviewers (agent, model, number of findings), Act on, Consider, Noted, Dismissed, Agreement map, Out-of-design changes. In the last one, check the diff against application-design.md and the design pages yourself: list each change to an interface, field or behaviour they do not describe, with its decisions.md line or "no decision recorded", or write "none".

Then, as a separate step, fix the Act-on items with tests, run `lean verify`, and add to review.md what was fixed.
"""

SWARM = """---
name: pstack-swarm
description: Fan out up to 5 parallel subagents, drain them, and return one report. Use in AI-DLC Lean for read-only surveys of existing code, multi-model checks and verification gauntlets; parallel code writing only for disjoint units.
---

# Swarm

Open a todo list with one entry per phase before launching anything: 1. Frame, 2. Fan out, 3. Aggregate, 4. Report.

## Phase A: Frame

1. State the done predicate and the artifact or report the swarm must return.
2. Choose the shape:
   - partition the work into slices (one module, acceptance example or risk area each);
   - race N workers on identical briefs, deciding up front between `first pass`, `rank all` and `best-of`;
   - or mix both.
3. Pick the workers:
   - `lean-worker` runs on the session's model and can write files and use the shell;
   - `lean-reviewer-opus` and `lean-reviewer-k3` give model diversity for judgment-heavy questions. They are read-only: read tools only, no shell.
4. At most 5 workers. Reviewers report only in their reply. A `lean-worker` may instead write its report to its own file, `aidlc-docs/<intent>/construction/swarm/<worker>.md`.

## Phase B: Fan out

Write the shared brief once to a file, `aidlc-docs/<intent>/construction/swarm/brief.md`: the goal, the scope, how to verify, what to report, and the material every worker needs. A reviewer cannot run commands, so put the diff and any command output it needs in the brief. Reports use `PASS`, `ISSUES` or `BLOCKED` with evidence (`file:line`, command output). A worker that can prove a defect lists every defect it can prove, not only the first.

Then dispatch all workers in ONE message with `invoke_sub_agent`, each with a short prompt: the brief's path plus that worker's own slice or race arm. Kiro starts a subagent only after its call has been written out in full, so long prompts start the workers one after another; short ones start them together. A worker sees nothing of this chat, so the brief and its prompt must stand alone.

**Writing code in parallel** is for `lean-worker` only, and only when all of these hold:
- `inception/application-design/unit-of-work.md` (if the intent has none, create it with `lean stage start units` and finish that stage first) or the code-generation plan gives each worker disjoint paths;
- requirements and application design are approved (or the design stage was skipped for `Size: small`), and, in regulated mode, the code-generation plan of every unit the workers touch;
- workers run no git commands.

After all workers finish, run `lean verify` once on the combined result. AI-DLC Lean's hooks gate every worker's writes exactly like your own.

If a worker drops out, proceed with N-1 and note it.

## Phase C: Aggregate

- Read the results. When a reviewer names a command that would confirm a finding, run it yourself.
- Drop a result that lacks the evidence its brief asked for and re-dispatch that worker once. After a second miss, record a gap; a gap does not count as a pass.
- For coverage, every slice needs a result. For a race, apply the rule declared up front.
- Do not paste raw worker output.

## Phase D: Report

Return one consolidated report: a result table, one line per issue, and any gaps or dropouts (plus the race rule, if used). Move lasting conclusions to where they belong: the assumptions in requirements.md, review.md, or the Session notes in aidlc-state.md.
"""

STEERING = """---
inclusion: always
---
# AI-DLC Lean quality pack (adapted from pstack)

Load these on-demand skills at the matching AI-DLC stage.

- **Existing code, big change**: `pstack-swarm` for a read-only survey (one worker per module) during reverse engineering. Before you change existing behaviour, use `pstack-blast-radius`.
- **Data and design**: `pstack-principle-model-the-domain` before you choose data shapes.
- **Code generation**:
  - `pstack-principle-sequence-verifiable-units` for the code-generation plan's steps;
  - `pstack-principle-boundary-discipline` for validation and authorization;
  - `pstack-principle-test-behavior-not-implementation` when writing tests;
  - `pstack-principle-fix-root-causes` when debugging.
- **Before calling anything done**: `pstack-principle-prove-it-works`, then `lean verify`.
- **Review**: `pstack-interrogate`, with `lean-reviewer-opus` and `lean-reviewer-k3` in parallel; the verdict goes to `aidlc-docs/<intent>/construction/build-and-test/review.md`.
- **The human corrects the same mistake twice**: `pstack-correct`.

Subagents:
- `lean-worker` (the session's model);
- `lean-reviewer-opus`, `lean-reviewer-k3` (read-only, no shell: put the diff in their brief).

At most 5 at once. AI-DLC Lean's gates apply to them as to you.
"""

REVIEWER_DESCRIPTION = ("AI-DLC Lean reviewer on %s, read-only (read tools only, no shell). Dispatched by pstack-interrogate "
                        "or pstack-swarm with a short prompt that names a brief file holding the diff.")
BRIEF_FILE_RULE = "When your prompt names a brief file, read that file first and follow it. "
REVIEWER_RULES = ("You are read-only: your tools can only read and search files. You have no shell and cannot write files, "
                  "so do not try to run git, tests or other commands. " + BRIEF_FILE_RULE + "The lead puts the diff, and "
                  "any command output you need, in your brief; read the surrounding code to check it, and return your "
                  "findings in your reply. If confirming a finding needs a command, name the command in your reply for "
                  "the lead to run.\n"
                  "Back every claim with evidence: `file:line`, or a quote from the diff or output in your brief. If you "
                  "find nothing, say so; an empty result is valid.")
WORKER_RULES = (BRIEF_FILE_RULE + "Write only to the paths your brief names. Run no git commands. AI-DLC Lean's hooks gate "
                "your writes; if one blocks you, stop and report BLOCKED with the hook's message instead of finding another "
                "route.\n"
                "Back every claim with evidence: `file:line`, or a command and its output. If you find nothing, say so; "
                "an empty result is valid.")
# The reviewers are read-only by construction: their only tool group is "read" (no shell, no write).
# name: (model, or None for the session model; tools; description; role; rules)
AGENTS = {
    "lean-reviewer-opus": ("claude-opus-5.5", '["read"]', REVIEWER_DESCRIPTION % "claude-opus-5.5",
                           "an independent, adversarial reviewer", REVIEWER_RULES),
    "lean-reviewer-k3": ("kimi-k3", '["read"]', REVIEWER_DESCRIPTION % "kimi-k3",
                         "an independent, adversarial reviewer", REVIEWER_RULES),
    "lean-worker": (None, '["read", "write", "shell"]',
                    "AI-DLC Lean swarm worker on the session model. Dispatched by pstack-swarm.",
                    "a worker in a parallel swarm", WORKER_RULES),
}
AGENT_BODY = "You are {role} dispatched by the AI-DLC Lean lead. Do exactly the task in your brief and nothing else.\n{rules}\n"

# `skill` or **skill** (backticked or bold), or a /skill command
REF_RE = re.compile(r"`([^`\n]+)`|\*\*([^*\n]+)\*\*|(?:^|[\s(\"'])/([a-z][a-z0-9-]*)\b", re.M)


def fail(msg):
    raise SystemExit("vendor_pstack: " + msg)


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, ValueError) as e:
        fail("cannot read %s: %s" % (path, e))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def newest_cached():
    base = os.path.expanduser(CACHE)
    try:
        names = os.listdir(base)
    except OSError:
        names = []
    versions = [n for n in names if re.match(r"^\d+(\.\d+)*$", n) and os.path.isdir(os.path.join(base, n))]
    if not versions:
        fail("no pstack version folder under %s; pass the pstack folder as an argument.\n%s" % (base, USAGE))
    return os.path.join(base, max(versions, key=lambda n: tuple(int(p) for p in n.split("."))))


def read_version(src):
    found = {}
    for name in (os.path.join(".claude-plugin", "plugin.json"), "plugin.json"):
        path = os.path.join(src, name)
        if not os.path.isfile(path):
            continue
        try:
            data = json.loads(read(path))
        except ValueError as e:
            fail("%s is not valid JSON: %s" % (path, e))
        if not isinstance(data, dict) or data.get("name") != "pstack":
            fail("%s does not describe the pstack plugin (expected \"name\": \"pstack\")" % path)
        version = data.get("version")
        if not isinstance(version, str) or not re.match(r"^\d+(\.\d+)*([-+][0-9A-Za-z.-]+)?$", version):
            fail("%s has no usable version (%r)" % (path, version))
        found[name] = version
    if not found:
        fail("no .claude-plugin/plugin.json or plugin.json in %s, so the pstack version is unknown" % src)
    if len(set(found.values())) > 1:
        fail("the plugin.json files in %s disagree on the version: %s" % (src, found))
    return list(found.values())[0]


def apply_edits(label, text, edits):
    for old, new in edits:
        if old not in text:
            fail("%s: the upstream text for an edit is gone; update the edit tables in tools/vendor_pstack.py: %r"
                 % (label, old[:80]))
        text = text.replace(old, new)
    return text


def upstream_names(src):
    names = set(n for n in os.listdir(os.path.join(src, "skills")) if os.path.isdir(os.path.join(src, "skills", n)))
    agents = os.path.join(src, "agents")
    if os.path.isdir(agents):
        names.update(n[:-3] for n in os.listdir(agents) if n.endswith(".md"))
    return names


def unshipped_refs(text, upstream):
    bad = set()
    for m in REF_RE.finditer(text):
        tok = (m.group(1) or m.group(2) or m.group(3) or "").strip().lstrip("/")
        if tok.startswith("pstack-"):
            if tok[len("pstack-"):] not in SHIPPED:
                bad.add(tok)
        elif tok in upstream or "principle-" + tok in upstream:
            bad.add(tok)
    return sorted(bad)


def build(src, version, license_text, out):
    footer = FOOTER % version
    skills = os.path.join(out, ".kiro", "skills")
    for name, edits in COPIED.items():
        text = read(os.path.join(src, "skills", name, "SKILL.md"))
        text = re.sub(r"(?m)^name:\s*%s\s*$" % re.escape(name), "name: pstack-%s" % name, text, count=1)
        if text.count("name: pstack-%s" % name) != 1:
            fail("%s: the upstream card has no 'name: %s' line" % (name, name))
        text = re.sub(r"(?m)^disable-model-invocation:.*\n", "", text)
        text = ADAPTER_RE.sub("", text)
        text = apply_edits(name, text, edits)
        write(os.path.join(skills, "pstack-" + name, "SKILL.md"), text.rstrip() + APPEND.get(name, "") + footer)
    write(os.path.join(skills, "pstack-interrogate", "SKILL.md"), INTERROGATE + footer)
    for ref in REFS:
        text = read(os.path.join(src, "skills", "interrogate", "references", ref))
        write(os.path.join(skills, "pstack-interrogate", "references", ref), apply_edits(ref, text, REF_EDITS.get(ref, [])))
    write(os.path.join(skills, "pstack-swarm", "SKILL.md"), SWARM + footer)
    write(os.path.join(out, ".kiro", "steering", "aidlc-lean-pstack.md"), STEERING)
    for name, (model, tools, description, role, rules) in AGENTS.items():
        fm = ["---", "name: %s" % name, "description: %s" % description, "tools: %s" % tools]
        fm += (["model: %s" % model] if model else []) + ["---", ""]
        write(os.path.join(out, ".kiro", "agents", name + ".md"), "\n".join(fm) + AGENT_BODY.format(role=role, rules=rules))
    write(os.path.join(out, "LICENSE-pstack"), license_text)


def check_pack(out, version, upstream):
    """Scan every generated file. Explicit checks (not asserts), so they also run under python3 -O."""
    footer = FOOTER % version
    problems = []
    for dirpath, _, files in os.walk(out):
        for fn in sorted(files):
            path = os.path.join(dirpath, fn)
            name = os.path.relpath(path, out).replace(os.sep, "/")
            if name == "LICENSE-pstack":
                continue
            text = read(path)
            problems += ["%s: contains %r" % (name, bad) for bad in FORBIDDEN if bad in text]
            problems += ["%s: contains %r, an AI-DLC Lean v0.1 name (v0.2 keeps each intent under aidlc-docs/<intent>/ "
                         "with the AI-DLC artifact names)" % (name, bad) for bad in RETIRED if bad in text]
            problems += ["%s: refers to %r, which is not a shipped skill (ship it, or rewrite the reference)" % (name, tok)
                         for tok in unshipped_refs(text, upstream)]
            if fn == "SKILL.md":
                folder = os.path.basename(dirpath)
                if not re.search(r"(?m)^name: %s$" % re.escape(folder), text):
                    problems.append("%s: no 'name: %s' line" % (name, folder))
                if text.count(footer) != 1:
                    problems.append("%s: the pstack %s attribution footer is missing or repeated" % (name, version))
    if problems:
        fail("the generated pack failed its checks; kit-pstack/ was not changed:\n  " + "\n  ".join(problems))


def swap_in(new, out):
    old = "%s.old-%d" % (out, os.getpid())
    if os.path.lexists(old):
        shutil.rmtree(old)
    had_old = os.path.lexists(out)
    if had_old:
        os.rename(out, old)
    try:
        os.rename(new, out)
    except OSError:
        if had_old:
            os.rename(old, out)
        raise
    if had_old:
        shutil.rmtree(old)


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(argv) > 1 or (argv and argv[0].startswith("-")):
        fail(USAGE)
    src = os.path.abspath(os.path.expanduser(argv[0])) if argv else newest_cached()
    if not os.path.isdir(os.path.join(src, "skills")):
        fail("pstack not found at %s (no skills/ folder)" % src)
    version = read_version(src)
    license_text = read(os.path.join(src, "LICENSE"))
    for line in LICENSE_LINES:
        if line not in license_text:
            fail("%s/LICENSE no longer contains %r; check the license and update LICENSE_LINES and FOOTER" % (src, line))
    upstream = upstream_names(src)
    tmp = tempfile.mkdtemp(prefix=".kit-pstack-new-", dir=HERE)
    try:
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp, 0o777 & ~umask)  # mkdtemp makes it 0700; the pack folder should get normal permissions
        build(src, version, license_text, tmp)
        check_pack(tmp, version, upstream)
        swap_in(tmp, OUT)
    finally:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    print("kit-pstack regenerated from %s (pstack %s, %d files)" % (src, version, n))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
