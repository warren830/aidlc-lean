#!/usr/bin/env python3
"""aidlc-lean: the deterministic part of the AI-DLC Lean kit for Kiro CLI (v3 engine).

Commands (people and the agent; `lean` = python3 .kiro/aidlc-lean/aidlc_lean.py):
  init [--regulated] [--multi-team] [--team NAME]   set up aidlc-docs/ in this project
  new <slug> [--title T] [--ideation]
                              start an intent: aidlc-docs/<yymmdd>-<slug>/ with aidlc-state.md and decisions.md; it
                              becomes the active intent. Default: Ideation is recorded as skipped and the intent
                              starts with inception/requirements/requirements.md. --ideation: it starts with
                              ideation/intent-capture/intent-statement.md
  use <intent>                switch the active intent (logged as INTENT_SWITCHED)
  status                      where the active intent stands: stage progress and the next step (it also brings
                              the generated part of aidlc-state.md up to date)
  stage start <id> [--unit U]                   create the stage's document from its template; in progress
  stage done <id> [--unit U] --note "<text>"    record what the stage did (inputs, outputs, key decisions)
  stage skip <id> [--unit U] --reason "<text>"  record why the stage is skipped
  stage skip ideation|operations --reason "<text>"
                              skip every stage of that phase that has no record yet (operations: not ci-pipeline)
  request IDEATION|REQUIREMENTS|DESIGN|INCEPTION|PLAN [--unit U]|RELEASE|CR-<team>-<n>
                              print the approval line for the human to type (RELEASE: only while `release`
                              would pass and its release.md is for the current code)
  verify                      run the configured checks; writes construction/build-and-test/build-and-test-summary.md
                              (regulated mode: also construction/build-and-test/evidence/verify-<time>.md)
  cr new <slug> --owner TEAM --paths a,b   open a contract change request; once the owner team approves it, it
                              unlocks those contract paths for the team that requested it, while it is open
  cr close <CR-id> --reason "<why>"        close it (the requesting or the owning team): it unlocks nothing more
  release                     write operations/release.md once approvals and checks are green
  audit verify | audit pack [intent]       check the hash chain / write aidlc-docs/<intent>/audit.md
                              (no intent given and none active: aidlc-docs/audit.md, all intents)
  doctor                      check the install

Stages in order (documents are in aidlc-docs/<intent>/; * = per unit, --unit U, default the only unit; the
units are the first column of the table in unit-of-work.md, or `app` without that file):
 Ideation (optional per intent: `new --ideation`, or `stage start <id>` until the requirements are approved; once
 it is used, IDEATION must be approved and current for the REQUIREMENTS/INCEPTION approval, code and release)
  intent-capture          ideation/intent-capture/intent-statement.md             required when Ideation is used
  market-research         ideation/market-research/market-research.md             skippable
  feasibility             ideation/feasibility/feasibility-assessment.md          skippable
  scope-definition        ideation/scope-definition/scope-document.md             required when Ideation is used
  team-formation          ideation/team-formation/team-assessment.md              skippable
  rough-mockups           ideation/rough-mockups/wireframes.md                    skippable
  approval-handoff        ideation/approval-handoff/initiative-brief.md           required when Ideation is used;
                                                                                  approval IDEATION (all its pages)
 Inception
  reverse-engineering     inception/reverse-engineering/architecture.md           skippable (greenfield)
  requirements            inception/requirements/requirements.md                  approval REQUIREMENTS or INCEPTION
  user-stories            inception/user-stories/stories.md                       skippable
  application-design      inception/application-design/application-design.md      approval DESIGN or INCEPTION;
                                                                                  skippable only with `Size: small`
  units                   inception/application-design/unit-of-work.md            skippable
 Construction
  functional-design*      construction/<unit>/functional-design/functional-design.md          skippable
  nfr-design*             construction/<unit>/nfr-design/nfr-design.md                        skippable
  infrastructure-design*  construction/<unit>/infrastructure-design/infrastructure-design.md  skippable
  code-generation*        construction/plans/<unit>-code-generation-plan.md + code    approval PLAN (regulated mode)
  build-and-test          construction/build-and-test/build-and-test-summary.md   recorded by `verify`
  ci-pipeline             construction/ci-pipeline/ci-config.md                   skippable; also after RELEASE
 Release
  release                 operations/release.md                                   written by `release`; approval RELEASE
                                                                                  (the approval records the stage done)
 Operations (optional in every mode, before or after RELEASE; the agent writes pages and config, it never deploys)
  deployment-pipeline     operations/deployment-pipeline/deployment-strategy.md   skippable
  environment-provisioning  operations/environment-provisioning/environment-inventory.md  skippable
  deployment-execution    operations/deployment-execution/deployment-log.md       skippable
  observability-setup     operations/observability-setup/observability.md         skippable
  incident-response       operations/incident-response/runbooks.md                skippable
  performance-validation  operations/performance-validation/load-test-plan.md     skippable
  feedback-optimization   operations/feedback-optimization/feedback-loop.md       skippable
After RELEASE only the Operations stages and ci-pipeline take stage commands.

The project is the folder that contains .kiro/aidlc-lean/ (this script's folder), which
may be a subfolder of a bigger git repository. Start kiro-cli in that folder.

Hook entry, used only by .kiro/hooks/*.json (the agent must not run it):
  hook SessionStart | hook UserPromptSubmit | hook PreToolUse

Stdlib only; Python >= 3.8.
"""
import collections
import contextlib
import fnmatch
import getpass
import hashlib
import json
import os
import posixpath
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:  # Windows: no advisory locks; parallel hooks then run unlocked
    fcntl = None

VERSION = "0.3.0"
KIT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(KIT_DIR, "templates")
TOOL = "python3 .kiro/aidlc-lean/aidlc_lean.py"
DOCS = "aidlc-docs"  # everything the method keeps, named as in AI-DLC v1

DEFAULT_CONFIG = {
    "version": 1,
    "regulated": False,
    "multi_team": False,
    "plan": "auto",  # auto (PLAN approvals needed in regulated mode) | always | never
    "checks": [],
    "check_timeout_sec": 1800,
    "protected_paths": [],
    "free_paths": ["*.md", "docs/**"],
    "deny_commands": [
        r"git\s+push\s+.*(--force|-f\b)",
        r"\brm\s+-(?=[a-zA-Z]*r)(?=[a-zA-Z]*f)[a-zA-Z]+\s+(/|~|\*|\.)(\s|$)",
        r"\bterraform\s+(apply|destroy)\b",
        r"\bkubectl\s+(delete|apply|replace)\b",
        r"\baws\s+\S+\s+(delete|terminate|remove)-",
        r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE)\b",
    ],
    "contracts_dir": DOCS + "/contracts",
    "teams": [],
    "approvers": {},
    "fingerprint_exclude": [DOCS + "/**", ".kiro/**"],
    "state_reminder_after_writes": 25,
    "resume_gap_hours": 4,
}

# ---------------------------------------------------------------- the AI-DLC stages
# doc: the stage's document, relative to aidlc-docs/<intent>/ ({unit} for per-unit stages);
# template None: the tool writes the document. skippable: True, False, "small" (only with Size: small) or
# "unused" (only while Ideation is not in use: the stages Ideation needs once it is used).
Stage = collections.namedtuple("Stage", "id name doc template skippable per_unit phase")
STAGES = (  # in the order of the Stage progress list
    Stage("intent-capture", "Intent Capture", "ideation/intent-capture/intent-statement.md", "intent-statement.md",
          "unused", False, "ideation"),
    Stage("market-research", "Market Research", "ideation/market-research/market-research.md", "market-research.md",
          True, False, "ideation"),
    Stage("feasibility", "Feasibility", "ideation/feasibility/feasibility-assessment.md", "feasibility-assessment.md",
          True, False, "ideation"),
    Stage("scope-definition", "Scope Definition", "ideation/scope-definition/scope-document.md", "scope-document.md",
          "unused", False, "ideation"),
    Stage("team-formation", "Team Formation", "ideation/team-formation/team-assessment.md", "team-assessment.md",
          True, False, "ideation"),
    Stage("rough-mockups", "Rough Mockups", "ideation/rough-mockups/wireframes.md", "wireframes.md", True, False,
          "ideation"),
    Stage("approval-handoff", "Approval Handoff", "ideation/approval-handoff/initiative-brief.md",
          "initiative-brief.md", "unused", False, "ideation"),
    Stage("reverse-engineering", "Reverse Engineering", "inception/reverse-engineering/architecture.md",
          "architecture.md", True, False, "inception"),
    Stage("requirements", "Requirements Analysis", "inception/requirements/requirements.md", "requirements.md",
          False, False, "inception"),
    Stage("user-stories", "User Stories", "inception/user-stories/stories.md", "stories.md", True, False, "inception"),
    Stage("application-design", "Application Design", "inception/application-design/application-design.md",
          "application-design.md", "small", False, "inception"),
    Stage("units", "Units Generation", "inception/application-design/unit-of-work.md", "unit-of-work.md", True,
          False, "inception"),
    Stage("functional-design", "Functional Design", "construction/{unit}/functional-design/functional-design.md",
          "functional-design.md", True, True, "construction"),
    Stage("nfr-design", "NFR Requirements + Design", "construction/{unit}/nfr-design/nfr-design.md",
          "nfr-design.md", True, True, "construction"),
    Stage("infrastructure-design", "Infrastructure Design",
          "construction/{unit}/infrastructure-design/infrastructure-design.md", "infrastructure-design.md", True, True,
          "construction"),
    Stage("code-generation", "Code Generation", "construction/plans/{unit}-code-generation-plan.md",
          "code-generation-plan.md", False, True, "construction"),
    Stage("build-and-test", "Build and Test", "construction/build-and-test/build-and-test-summary.md", None, False,
          False, "construction"),
    Stage("ci-pipeline", "CI Pipeline", "construction/ci-pipeline/ci-config.md", "ci-config.md", True, False,
          "construction"),
    Stage("release", "Release", "operations/release.md", None, False, False, "release"),
    Stage("deployment-pipeline", "Deployment Pipeline", "operations/deployment-pipeline/deployment-strategy.md",
          "deployment-strategy.md", True, False, "operations"),
    Stage("environment-provisioning", "Environment Provisioning",
          "operations/environment-provisioning/environment-inventory.md", "environment-inventory.md", True, False,
          "operations"),
    Stage("deployment-execution", "Deployment Execution", "operations/deployment-execution/deployment-log.md",
          "deployment-log.md", True, False, "operations"),
    Stage("observability-setup", "Observability Setup", "operations/observability-setup/observability.md",
          "observability.md", True, False, "operations"),
    Stage("incident-response", "Incident Response", "operations/incident-response/runbooks.md", "runbooks.md", True,
          False, "operations"),
    Stage("performance-validation", "Performance Validation", "operations/performance-validation/load-test-plan.md",
          "load-test-plan.md", True, False, "operations"),
    Stage("feedback-optimization", "Feedback Optimization", "operations/feedback-optimization/feedback-loop.md",
          "feedback-loop.md", True, False, "operations"),
)
STAGE_BY_ID = {s.id: s for s in STAGES}
PER_UNIT_STAGES = tuple(s for s in STAGES if s.per_unit)  # AI-DLC's per-unit loop: designs, then code generation
UNIT_DESIGN_STAGES = tuple(s for s in PER_UNIT_STAGES if s.id != "code-generation")
STAGE_EVENTS = ("STAGE_STARTED", "STAGE_COMPLETED", "STAGE_SKIPPED")
# The optional phases (v0.3): `stage skip ideation|operations` skips each of their stages that has no record yet,
# logged as one PHASE_SKIPPED {phase, stages, reason}. Operations does not include ci-pipeline.
PHASES = collections.OrderedDict((("ideation", "Ideation"), ("operations", "Operations")))
PHASE_STAGES = {p: tuple(s for s in STAGES if s.phase == p) for p in PHASES}
IDEATION_STAGES = PHASE_STAGES["ideation"]
IDEATION_IDS = tuple(s.id for s in IDEATION_STAGES)
IDEATION_REQUIRED = tuple(s.id for s in IDEATION_STAGES if s.skippable == "unused")
HANDOFF_DOC = STAGE_BY_ID["approval-handoff"].doc
# stages that still take stage commands after RELEASE (and are not part of the release Next before it)
AFTER_RELEASE_IDS = ("ci-pipeline",) + tuple(s.id for s in PHASE_STAGES["operations"])
NOT_REQUESTED = "not requested (lean new without --ideation)"  # the reason `new` records for the Ideation skip
REQ_DOC = STAGE_BY_ID["requirements"].doc
DESIGN_DOC = STAGE_BY_ID["application-design"].doc
UNITS_DOC = STAGE_BY_ID["units"].doc
PLAN_DOC = STAGE_BY_ID["code-generation"].doc
PLANS_DIR = "construction/plans"
SUMMARY_DOC = STAGE_BY_ID["build-and-test"].doc
EVIDENCE_DIR = "construction/build-and-test/evidence"
RELEASE_DOC = STAGE_BY_ID["release"].doc
STATE_DOC = "aidlc-state.md"
DECISIONS_DOC = "decisions.md"
AUDIT_DOC = "audit.md"
TEMPLATE_NAMES = tuple(s.template for s in STAGES if s.template) + ("aidlc-state.md", "decisions.md", "cr.md",
                                                                    "lean.json")
PLAN_FILE_RE = re.compile(r"^(.+)-code-generation-plan\.md$")
UNIT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# folder names under construction/ that are not units. Not ci-pipeline: a v0.2 intent may have a unit of that name,
# and its pages (construction/ci-pipeline/<stage>/...) do not collide with the CI Pipeline page (.../ci-config.md).
RESERVED_UNITS = ("plans", "build-and-test")
# "Size: small", also "- **Size:** small" (the first Size line counts). The template's placeholder
# "Size: <small|large>" is a Size line too, so a page that still has it is not small.
SIZE_RE = re.compile(r"(?im)^[ \t>*-]*\**[ \t]*Size[ \t]*\**[ \t]*[:：][ \t]*\**[ \t]*([A-Za-z]+|<)")
# a task checkbox in a code-generation plan: "- [x] 2. ..." or "* [ ] ..." at the start of a line
CHECKBOX_RE = re.compile(rb"(?m)^([ \t]*[-*] )\[[xX ]\]")
# the same boxes with their state and the rest of the line (plan_steps counts what plan_sha256 normalises)
STEP_RE = re.compile(rb"(?m)^([ \t]*[-*] )\[([xX ])\]([^\n]*)")
BEGIN_MARK = "<!-- lean:begin progress -->"
END_MARK = "<!-- lean:end progress -->"
NOTE_MAX = 2000
APPROVAL_KINDS = ("IDEATION", "REQUIREMENTS", "DESIGN", "INCEPTION", "PLAN", "RELEASE")

READ_TOOL_RE = re.compile(r"(read|list|glob|grep|search|fetch|view|thinking|todo|report|load|disclose|subagent_response)", re.I)
SHELL_TOOLS = {"execute_bash", "execute_pwsh", "execute_cmd", "shell", "bash", "run_command"}
KIND_RE = r"IDEATION|REQUIREMENTS|DESIGN|INCEPTION|PLAN|RELEASE|CR-[A-Za-z0-9_]+-\d+"
APPROVE_RE = re.compile(  # the whole line must be the approval, so "approve design after X" does not count
    r"(?im)^[ \t]*(approve|approved|批准|同意)[ \t]*[:：]?[ \t]*(" + KIND_RE + r")"
    r"(?:[ \t]+([0-9a-fA-F]{6,64}))?[ \t]*(\(via[^)\n]{1,200}\))?[ \t]*[.!。！]?[ \t]*$")
REJECT_RE = re.compile(r"(?im)^[ \t]*(reject|驳回|拒绝)[ \t]*[:：]?[ \t]*(" + KIND_RE + r")\b(.*)$")
NEAR_APPROVAL_RE = re.compile(r"(?im)^[ \t]*(approve|approved|批准|同意)[ \t]*[:：]?[ \t]*"
                              r"(SPEC|IDEATION|REQUIREMENTS|DESIGN|INCEPTION|PLAN|RELEASE|CR-)")
ALLOW_PROTECTED_RE = re.compile(r"(?im)^[ \t]*(allow test change|允许改测试|允许修改测试|允许修改验收测试)[ \t]*[.!。！]?[ \t]*$")
KIT_PATHS = (".kiro/hooks/", ".kiro/aidlc-lean/", ".kiro/steering/aidlc-lean.md", ".kiro/skills/aidlc-lean-",
             ".kiro/steering/aidlc-lean-pstack.md", ".kiro/skills/pstack-", ".kiro/agents/lean-")
HOST_PROMPT_RE = re.compile(r"^\s*(\[SYSTEM\]|A workflow you launched)|<original_user_request>")
# key = value where the key names a secret: password=, DB_PASSWORD=, "password": "..", aws_secret_access_key = ..
# The key starts at an identifier boundary and its parts are bounded, so the search stays linear on long lines.
SECRET_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]{0,64}(?:passw(?:or)?d|pwd|secret|token|api[_-]?key|access[_-]?key"
    r"|private[_-]?key|credentials?)(?:[_.-][A-Za-z0-9_.-]{0,64})?[\"']?\s*[=:]\s*)"
    r"(?!\*\*\*)(\"(?:[^\"\\\n]|\\.)*\"?|'[^'\n]*'?|[^\s\"',;]+)")  # (?!***): already masked


def _mask_value(m):
    q = m.group(2)[0]
    return m.group(1) + (q + "***" + q if q in "\"'" else "***")


SECRET_PATTERNS = (  # applied in this order by mask()
    # PEM private key blocks, also when the END line is cut off
    (re.compile(r"-----BEGIN ([A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?)-----.*?(?:-----END \1-----|\Z)", re.S),
     lambda m: "-----BEGIN %s-----***-----END %s-----" % (m.group(1), m.group(1))),
    # passwords in URLs: scheme://user:password@host
    (re.compile(r"\b([A-Za-z][A-Za-z0-9+.-]{0,30}://[^\s:/@]{1,256}:)[^\s@/]{1,256}@"), lambda m: m.group(1) + "***@"),
    # Authorization headers (any scheme), then bare bearer tokens
    (re.compile(r"(?i)\b((?:proxy-)?authorization[\"']?[ \t]*[=:][ \t]*[\"']?"
                r"(?:(?:bearer|basic|token|digest|negotiate)[ \t]+)?)[^\s\"',;]+"), lambda m: m.group(1) + "***"),
    (re.compile(r"(?i)\b(bearer[ \t]+)[A-Za-z0-9._~+/-]{8,}=*"), lambda m: m.group(1) + "***"),
    (SECRET_RE, _mask_value),
    # tokens that are secret on their own
    (re.compile(r"\b(gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}"), lambda m: m.group(1) + "***"),
    (re.compile(r"(AKIA|ASIA)[0-9A-Z]{16}"), lambda m: m.group(1) + "***"),
    (re.compile(r"\b(xox[abprs]-)[A-Za-z0-9-]{10,}"), lambda m: m.group(1) + "***"),
)
# context the hooks inject into the model (SessionStart, resumed turns) is capped
CONTEXT_MAX_LINES = 40
CONTEXT_MAX_CHARS = 4000
CONTEXT_LINE_CHARS = 300
TRUNCATED_NOTE = "(truncated; run `%s status` for the rest)" % TOOL
MAX_TRACKED_SESSIONS = 50
REVIEW_DOC = "construction/build-and-test/review.md"  # the release review the agent writes (skill aidlc-lean-release)
# Subagents. Kiro 3.1.0 runs the workspace SessionStart and UserPromptSubmit hooks for a subagent it starts, with the
# parent chat's session_id and nothing else that marks a subagent; the UserPromptSubmit prompt is the prompt the
# agent dispatched. So PreToolUse of a delegation tool keeps the dispatched prompt's sha256 as a pending dispatch
# (.aidlc-lean/subagents.json), and the prompt hook takes a prompt that matches one as the subagent's, not a person's.
DELEGATION_TOOLS = ("invoke_sub_agent", "orchestrate_subagent")
DELEGATION_TOOL_RE = re.compile(r"sub_?agent|delegat|orchestrat|spawn", re.I)
DISPATCH_FILE = "subagents.json"
DISPATCH_MAX = 50  # pending dispatches kept (the newest)
DISPATCH_TTL_HOURS = 2  # a dispatch no subagent prompt answered within this time is dropped
DISPATCH_PREFIX_CHARS = 200  # fallback match: the prompt starts with the dispatched prompt's first 200 characters
# who recorded a ledger entry, as audit.md and the Stage log label it
PROMPT_EVENTS = ("HUMAN_TURN", "APPROVED", "REJECTED", "APPROVAL_REFUSED")  # from the human's own message
HOOK_LABELS = {"SESSION_START": "hook (session start)", "SUBAGENT_START": "hook (subagent start)",
               "SUBAGENT_PROMPT": "hook (subagent prompt)", "HOST_TURN": "hook (host prompt)",
               "BLOCKED": "hook (agent tool call)", "PROTECTED_CHANGE": "hook (agent tool call)"}


# ---------------------------------------------------------------- basics
def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""


def plan_sha256(path):
    """sha256 of a code-generation plan with every task checkbox read as [ ], or None if it cannot be read.
    A PLAN approval is bound to it, so ticking steps keeps the approval and any other edit voids it."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    return sha256_bytes(CHECKBOX_RE.sub(rb"\1[ ]", data))


PlanSteps = collections.namedtuple("PlanSteps", "total open first text")


def plan_steps(path):
    """The task checkboxes of a code-generation plan, counted as plan_sha256 normalises them: total, open (not
    ticked), the number of the first open box (None when all are ticked) and its text; None if it cannot be read."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    boxes = [(m.group(2) != b" ", m.group(3)) for m in STEP_RE.finditer(data)]
    first = next((k for k, (done, _) in enumerate(boxes, 1) if not done), None)
    text = " ".join(boxes[first - 1][1].decode("utf-8", "replace").split()) if first else ""
    return PlanSteps(len(boxes), sum(1 for done, _ in boxes if not done), first, text)


def text_sha(text):
    """sha256 of a prompt (also one with lone surrogates, which JSON can carry)."""
    return sha256_bytes(text.encode("utf-8", "surrogatepass"))


def ts_epoch(ts):
    """'2026-11-08T10:12:34.567Z' -> seconds since the epoch, or None."""
    for size, fmt in ((23, "%Y-%m-%dT%H:%M:%S.%f"), (19, "%Y-%m-%dT%H:%M:%S")):
        try:
            return datetime.strptime(ts[:size], fmt).replace(tzinfo=timezone.utc).timestamp()
        except (TypeError, ValueError):
            continue
    return None


def run(cmd, cwd, timeout=30):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        return 1, ""


def kit_root():
    """The project root: the folder that contains .kiro/aidlc-lean/, i.e. where this script is installed.
    It can be a subfolder of a bigger git repository (monorepo); git commands run from it work as usual."""
    kiro = os.path.dirname(KIT_DIR)
    if os.path.basename(KIT_DIR) == "aidlc-lean" and os.path.basename(kiro) == ".kiro":
        return os.path.dirname(kiro)
    return None


def find_root(start=None):
    root = kit_root()
    if root:
        return root
    start = os.path.abspath(start or os.getcwd())  # script run from outside an installed kit
    code, out = run(["git", "rev-parse", "--show-toplevel"], start)
    if code == 0 and out:
        return out
    return start


def rel(root, path):
    if not path:
        return ""
    p = path if os.path.isabs(path) else os.path.join(root, path)
    p = os.path.realpath(p)
    r = os.path.realpath(root)
    try:
        out = os.path.relpath(p, r)
    except ValueError:
        return path
    return out.replace(os.sep, "/")


def case_insensitive_fs(root):
    """Does the file system of the project ignore letter case (macOS and Windows by default)? Probed on .kiro/ or
    aidlc-docs/, whichever exists."""
    for name in (".kiro", DOCS):
        path = os.path.join(root, name)
        if os.path.exists(path):
            try:
                return os.path.samefile(path, os.path.join(root, name.upper()))
            except OSError:
                return False
    return False


def true_case(root, relpath):
    """A project-relative path with each component that exists spelled as it is on disk (the rest as given): on a
    case-insensitive file system AIDLC-DOCS/LEAN.JSON is aidlc-docs/lean.json, and the path checks compare names."""
    if not relpath or relpath == ".." or relpath.startswith("../") or os.path.isabs(relpath):
        return relpath
    parts, cur = relpath.split("/"), root
    for k, part in enumerate(parts):
        try:
            names = os.listdir(cur)
        except OSError:
            break
        if part not in names:
            hit = [n for n in names if n.lower() == part.lower()]
            if len(hit) != 1:
                break
            parts[k] = hit[0]
        cur = os.path.join(cur, parts[k])
    return "/".join(parts)


def escapes(relpath):
    """Does a project-relative path lead outside the project folder?"""
    return relpath == ".." or relpath.startswith("../") or os.path.isabs(relpath)


def norm_contracts_dir(root, raw, insensitive):
    """(contracts_dir as configured, its resolved target, problem for doctor or None). The configured path is kept
    as written, only normalised lexically (`./`, `//`, a trailing `/`; `..` stays, as in v0.2: a monorepo project may
    share a contracts folder next to it); an absolute path into the project is made relative. The target is the same
    folder with symlinks resolved, as the paths of tool calls are. A path is a contract under either. On a
    case-insensitive file system both have the letter case on disk. Doctor names only values that are ambiguous:
    empty, the project folder itself, or an absolute path that does not exist (read inside the project)."""
    default = DEFAULT_CONFIG["contracts_dir"]
    given = str(raw if raw is not None else default).strip()
    problem = None
    text = given
    if not given:
        text, problem = default, "contracts_dir in %s/lean.json is empty: AI-DLC Lean uses %s" % (DOCS, default)
    elif os.path.isabs(given):
        inside = rel(root, given)
        if not escapes(inside):
            text = inside  # the same folder, relative to the project
        elif not os.path.isdir(given):
            text = given.lstrip("/")
            problem = ("contracts_dir %r in %s/lean.json is an absolute path to no folder: AI-DLC Lean reads it as %r "
                       "in the project folder; write that, or the path of an existing folder" % (given, DOCS, text))
    text = posixpath.normpath(text)
    if text == ".":
        text, problem = default, ("contracts_dir %r in %s/lean.json is the project folder itself: AI-DLC Lean uses %s; "
                                  "name the folder that holds the contracts" % (given, DOCS, default))
    resolved = rel(root, os.path.join(root, text))
    if insensitive:
        text, resolved = true_case(root, text), true_case(root, resolved)
    return text, resolved, problem


def matches(relpath, patterns):
    for pat in patterns or []:
        if pat.endswith("/") and relpath.startswith(pat):
            return True
        if fnmatch.fnmatchcase(relpath, pat):
            return True
    return False


def read_text(path, default=""):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return default


def _umask():
    m = os.umask(0)
    os.umask(m)
    return m


def write_text(path, text):
    """Replace a file atomically. Each writer uses its own temp file in the same folder, so parallel hook
    processes (subagents) never trip over each other's temp file."""
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError:
            mode = 0o666 & ~_umask()
        os.chmod(tmp, mode)  # mkstemp makes 0600 files; keep the usual permissions
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def create_new(path, text):
    """Create a file that must not exist yet (False if it does). Race-free: O_CREAT|O_EXCL."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return True


@contextlib.contextmanager
def file_lock(path):
    """Exclusive advisory lock (POSIX flock) for read-modify-write of local state. Where there is no fcntl
    (Windows) or the file system refuses the lock, it degrades to running unlocked."""
    f = None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        f = open(path, "a+")
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    except OSError:
        pass
    try:
        yield
    finally:
        if f is not None:
            f.close()  # closing the file releases the lock


def mask(text):
    """Mask secrets before text goes into evidence files or the ledger."""
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def cap_context(lines, max_lines=CONTEXT_MAX_LINES, max_chars=CONTEXT_MAX_CHARS, line_chars=CONTEXT_LINE_CHARS):
    """Bound what a hook injects into the model's context; a cut block ends with TRUNCATED_NOTE."""
    lines = list(lines)
    if len(lines) <= max_lines and all(len(l) <= line_chars for l in lines) and \
            sum(len(l) + 1 for l in lines) <= max_chars:
        return lines
    out, size = [], len(TRUNCATED_NOTE)
    for line in lines:
        if len(line) > line_chars:
            line = line[:line_chars - 3] + "..."
        if len(out) + 1 >= max_lines or size + len(line) + 1 > max_chars:
            break
        out.append(line)
        size += len(line) + 1
    return out + [TRUNCATED_NOTE]


def strip_comments(text):
    return re.sub(r"(?s)<!--.*?-->", "", text)


def one_line(text, limit=NOTE_MAX):
    """Text for one generated Markdown line: whitespace collapsed, no HTML comment markers (they would hide or
    end the generated region of aidlc-state.md), shortened to limit."""
    s = " ".join(str(text or "").split()).replace("<!--", "< !--").replace("-->", "-- >")
    return s if len(s) <= limit else s[:limit - 3] + "..."


def when(ts):
    """'2026-11-08T10:12:34.567Z' -> '2026-11-08 10:12 UTC'."""
    ts = ts or ""
    return "%s %s UTC" % (ts[:10], ts[11:16]) if len(ts) >= 16 else ts


def norm_kind(kind):
    """REQUIREMENTS/DESIGN/... in capitals; a CR id keeps its team's spelling."""
    return "CR-" + kind[3:] if kind.upper().startswith("CR-") else kind.upper()


def team_key(name):
    """A team name as `init --team` and `cr new` write it (letters, digits and _); '' for none."""
    return re.sub(r"[^A-Za-z0-9_]", "_", str(name or "").strip("`* \t"))


def parse_opts(args, allowed):
    """`--name value` or `--name=value` pairs: (dict, None) or (None, error)."""
    out, i = {}, 0
    while i < len(args):
        a = args[i]
        key, eq, val = a.partition("=")
        if eq and key in allowed:
            out[key] = val
            i += 1
            continue
        if a not in allowed:
            return None, "unexpected argument: %s" % a
        if i + 1 >= len(args):
            return None, "%s needs a value" % a
        out[a] = args[i + 1]
        i += 2
    return out, None


# ---------------------------------------------------------------- Markdown helpers
def first_table(text):
    """(header cells, rows of cells) of the first Markdown table outside HTML comments."""
    lines = strip_comments(text).splitlines()
    for i in range(len(lines) - 1):
        sep = lines[i + 1].strip()
        if lines[i].strip().startswith("|") and "---" in sep and re.match(r"^[|:\- \t]+$", sep):
            rows = []
            for line in lines[i + 2:]:
                if not line.strip().startswith("|"):
                    break
                rows.append(table_cells(line))
            return table_cells(lines[i]), rows
    return [], []


def table_cells(line):
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") else s
    return [c.strip() for c in s.split("|")]


def split_paths(cell):
    cell = cell.replace("`", " ").replace("<br>", " ")
    return [p[2:] if p.startswith("./") else p for p in re.split(r"[,;\s]+", cell) if p and p not in ("-", "—")]


def path_in(relpath, globs):
    """A unit's Paths cell: globs (fnmatch), or a plain folder/file that matches itself and everything below it."""
    for g in globs:
        if any(c in g for c in "*?["):
            if fnmatch.fnmatchcase(relpath, g):
                return True
        else:
            g = g.rstrip("/")
            if g and (relpath == g or relpath.startswith(g + "/")):
                return True
    return False


def norm_ws(text):
    return "\n".join(l.rstrip() for l in text.replace("\r\n", "\n").strip().split("\n"))


def says_small(text):
    """Does requirements.md say Size: small? Its first Size line counts; the template's <small|large> is not small."""
    m = SIZE_RE.search(strip_comments(text))
    return bool(m) and m.group(1).lower() == "small"


# ---------------------------------------------------------------- templates
FALLBACK_TEMPLATES = {  # used only when a template file is missing (`doctor` reports it)
    "aidlc-state.md": "# AI-DLC State: {{TITLE}}\nIntent: {{INTENT}} · Mode: {{MODE}} · Created: {{DATE}}\n"
                      "\n## Session notes\nStatus: \n\n### Next\n1. \n",
    "decisions.md": "# Decisions: {{TITLE}}\n\n| ID | Date | Decision | Why | Who |\n|---|---|---|---|---|\n",
    "cr.md": "# {{ID}}: {{TITLE}}\n\n- Requested by team: {{FROM}}\n- Owner team: {{OWNER}}\n- Paths: {{PATHS}}\n"
             "- Opened: {{DATE}}\n\n## Change\n\n## Why\n\n## Compatibility\n\n## Consumers affected\n",
}
FALLBACK_STAGE_TEMPLATE = "# {{STAGE}}: {{TITLE}}\n\nIntent: {{INTENT}} · Created: {{DATE}}\n"
DATE_SENTINEL = "\x00DATE\x00"
MODE_SENTINEL = "\x00MODE\x00"


def template(name, **kw):
    text = read_text(os.path.join(TEMPLATES, name), None)
    if text is None:
        text = FALLBACK_TEMPLATES.get(name, FALLBACK_STAGE_TEMPLATE if name.endswith(".md") else "")
    for k, v in kw.items():
        text = text.replace("{{%s}}" % k, v)
    return text


def doc_vars(pj, intent, stage=None, unit=None):
    """Placeholder values for an intent's documents: {{TITLE}} {{INTENT}} {{DATE}} {{UNIT}} {{STAGE}} {{MODE}}."""
    return {"TITLE": intent_title(pj, intent), "INTENT": intent, "DATE": now()[:10], "UNIT": unit or "",
            "STAGE": stage.name if stage else "", "MODE": mode_text(pj)}


def is_untouched(text, name, kw):
    """True if text is still the rendered template `name` (whatever day it was rendered on)."""
    tpl = template(name, **dict(kw, DATE=DATE_SENTINEL, MODE=MODE_SENTINEL))
    pat = re.escape(norm_ws(tpl)).replace(re.escape(DATE_SENTINEL), r"\d{4}-\d{2}-\d{2}") \
        .replace(re.escape(MODE_SENTINEL), r"[^\n]*")
    return re.fullmatch(pat, norm_ws(text)) is not None


def mode_text(pj):
    on = [name for name, key in (("regulated", "regulated"), ("multi-team", "multi_team")) if pj.cfg.get(key)]
    return ", ".join(on) or "standard"


# ---------------------------------------------------------------- approval events
def covers(e, r):
    """Does an APPROVED / REJECTED / APPROVAL_REQUESTED event cover the file r? INCEPTION covers two files."""
    d = e.get("data") or {}
    files = d.get("files")
    return r in files if isinstance(files, dict) else d.get("path") == r


def covered_sha(e, r):
    """The sha256 of file r that the event recorded."""
    d = e.get("data") or {}
    files = d.get("files")
    return files.get(r) if isinstance(files, dict) else d.get("sha256")


def event_paths(d):
    return d.get("path") or " + ".join(d.get("paths") or [])


# ---------------------------------------------------------------- project
_UNSET = object()


class Project:
    def __init__(self, root):
        self.root = root
        self.docs = os.path.join(root, DOCS)
        self.local = os.path.join(root, ".aidlc-lean")
        self.cfg = dict(DEFAULT_CONFIG)
        self._clone_id = None
        self._fingerprint = _UNSET
        self._committed = _UNSET
        self._events = None
        cfg_path = os.path.join(self.docs, "lean.json")
        self.initialized = os.path.exists(cfg_path)
        if self.initialized:
            try:
                self.cfg.update(json.loads(read_text(cfg_path, "{}")))
            except ValueError as e:
                raise SystemExit("%s/lean.json is not valid JSON: %s" % (DOCS, e))
        self.case_insensitive = case_insensitive_fs(root)
        # contracts_dir as configured (lexically normalised) and its resolved target: see contract_form
        self.cfg["contracts_dir"], self.contracts_real, self.contracts_dir_problem = norm_contracts_dir(
            root, self.cfg.get("contracts_dir"), self.case_insensitive)

    def relpath(self, path):
        """A tool call's path as the guards compare it: project-relative, symlinks resolved, and on a
        case-insensitive file system in the letter case on disk."""
        r = rel(self.root, path)
        return true_case(self.root, r) if self.case_insensitive else r

    # ---- local (gitignored) state, written by hooks and commands only
    def local_get(self, name, default=None):
        try:
            return json.loads(read_text(os.path.join(self.local, name), ""))
        except ValueError:
            return default

    def local_put(self, name, value):
        write_text(os.path.join(self.local, name), json.dumps(value, ensure_ascii=False, indent=1))

    def state_lock(self):
        """Serializes read-modify-write of .aidlc-lean/*.json across parallel hook processes."""
        return file_lock(os.path.join(self.local, "state.lock"))

    def doc_lock(self):
        """Serializes regenerating aidlc-state.md (a separate lock: callers may hold state_lock)."""
        return file_lock(os.path.join(self.local, "aidlc-state.lock"))

    def local_dict(self, name):
        value = self.local_get(name, {})
        return value if isinstance(value, dict) else {}

    def count_write(self):
        """One more code write since aidlc-state.md was last updated (feeds the reminder), and when it was (a
        review.md older than it no longer counts as the review of this code)."""
        with self.state_lock():
            c = self.local_dict("counters.json")
            c["writes_since_state"] = (c.get("writes_since_state") or 0) + 1
            c["last_code_write"] = now()
            self.local_put("counters.json", c)

    def reset_write_count(self):
        with self.state_lock():
            c = self.local_dict("counters.json")
            c["writes_since_state"] = 0
            self.local_put("counters.json", c)

    def clone_id(self):
        if not self._clone_id:
            path = os.path.join(self.local, "clone-id")
            self._clone_id = read_text(path).strip() or self._create_clone_id(path)
        return self._clone_id

    def _create_clone_id(self, path):
        host = re.sub(r"[^A-Za-z0-9]", "", socket.gethostname().split(".")[0])[:16] or "host"
        new = "%s-%s" % (host.lower(), uuid.uuid4().hex[:6])
        os.makedirs(self.local, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except FileExistsError:  # a parallel hook process is creating it: use its id
            for _ in range(200):
                cid = read_text(path).strip()
                if cid:
                    return cid
                time.sleep(0.005)
            with self.state_lock():  # still empty (its creator died): replace it, one process at a time
                cid = read_text(path).strip()
                if not cid:
                    write_text(path, new + "\n")
                    cid = new
            return cid
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new + "\n")
        return read_text(path).strip() or new

    def team(self):
        return os.environ.get("AIDLC_LEAN_TEAM") or self.local_dict("local.json").get("team")

    def identity(self):
        _, email = run(["git", "config", "user.email"], self.root)
        _, name = run(["git", "config", "user.name"], self.root)
        try:
            os_user = getpass.getuser()
        except Exception:  # noqa: BLE001
            os_user = "unknown"
        return {"git_email": email, "git_name": name, "os_user": os_user,
                "host": socket.gethostname(), "team": self.team()}

    # ---- intents: the folders directly under aidlc-docs/, except audit/ and contracts/
    def reserved(self):
        """The folders under aidlc-docs/ that are not intents: audit/, contracts/ and the contracts folder, by its
        configured name (a symlink there is not an intent) and by its resolved target."""
        names = {"audit", "contracts"}
        for path in (self.cfg.get("contracts_dir"), getattr(self, "contracts_real", "")):
            parts = str(path or "").strip("/").split("/")
            if len(parts) > 1 and parts[0] == DOCS:
                names.add(parts[1])
        return names

    def list_intents(self):
        if not os.path.isdir(self.docs):
            return []
        skip = self.reserved()
        return sorted(x for x in os.listdir(self.docs)
                      if x not in skip and not x.startswith(".") and os.path.isdir(os.path.join(self.docs, x)))

    def active(self):
        items = self.list_intents()
        a = self.local_dict("active.json").get("intent")
        if a in items:
            return a
        return items[0] if len(items) == 1 else None

    def doc(self, intent, relpath=""):
        return os.path.join(self.docs, intent, relpath) if relpath else os.path.join(self.docs, intent)

    def short(self, intent, relpath):
        """A project-relative path shown relative to the intent folder."""
        prefix = "%s/%s/" % (DOCS, intent)
        return relpath[len(prefix):] if relpath.startswith(prefix) else relpath

    def is_tool_record(self, r):
        """Files only the tool writes: build-and-test-summary.md, build-and-test/evidence/**, audit.md."""
        parts = r.split("/")
        if len(parts) < 2 or parts[0] != DOCS:
            return False
        if parts[1:] == [AUDIT_DOC]:
            return True
        if len(parts) < 3 or parts[1] in self.reserved():
            return False
        rest = parts[2:]
        return rest == [AUDIT_DOC] or (rest[:2] == ["construction", "build-and-test"] and (
            rest[2:] == ["build-and-test-summary.md"] or (len(rest) > 2 and rest[2] == "evidence")))

    # ---- units and plans
    def units(self, intent):
        """(names, info, ignored). names: the first column of the first table in unit-of-work.md; info: per unit,
        its paths (a Paths column) and owner team. Without that file, or while it is still the template, the only
        unit is `app` and info is empty. ignored: names that cannot be folder names."""
        text = read_text(self.doc(intent, UNITS_DOC), None)
        if not text or not text.strip() or \
                is_untouched(text, "unit-of-work.md", doc_vars(self, intent, STAGE_BY_ID["units"])):
            return ["app"], {}, []
        header, rows = first_table(text)
        pcol = next((i for i, h in enumerate(header) if "path" in h.lower()), None)
        ocol = next((i for i, h in enumerate(header) if "owner" in h.lower() or "team" in h.lower()), None)
        names, info, ignored = [], {}, []
        for cells in rows:
            name = cells[0].strip().strip("`*").strip() if cells else ""
            if not name or name in ("-", "...", "…") or "<" in name or "{{" in name:
                continue
            if not UNIT_NAME_RE.match(name) or name in RESERVED_UNITS:
                ignored.append(name)
                continue
            if name in info:
                continue
            names.append(name)
            info[name] = {"paths": split_paths(cells[pcol]) if pcol is not None and pcol < len(cells) else [],
                          "owner": cells[ocol].strip("`* ") if ocol is not None and ocol < len(cells) else ""}
        if not names:
            return ["app"], {}, ignored
        return names, info, ignored

    def units_for_path(self, intent, relpath):
        """The units whose paths contain relpath; ['app'] without unit-of-work.md; None if no unit claims it."""
        names, info, _ = self.units(intent)
        if not info:
            return ["app"]
        hit = [n for n in names if path_in(relpath, info[n]["paths"])]
        return hit or None

    def plans(self, intent):
        """{unit: path} of the code-generation plans that exist for an intent."""
        d = self.doc(intent, PLANS_DIR)
        out = {}
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                m = PLAN_FILE_RE.match(n)
                if m and os.path.isfile(os.path.join(d, n)):
                    out[m.group(1)] = os.path.join(d, n)
        return out

    def is_plan(self, path):
        """Is path an intent's code-generation plan (aidlc-docs/<intent>/construction/plans/<unit>-...)?"""
        parts = rel(self.root, path).split("/")
        return len(parts) == 5 and parts[0] == DOCS and parts[2:4] == PLANS_DIR.split("/") and \
            PLAN_FILE_RE.match(parts[4]) is not None

    def approval_sha(self, path):
        """The sha256 an approval of the file is bound to: its content; for a code-generation plan, its content
        with the task checkboxes unticked (plan_sha256)."""
        return plan_sha256(path) if self.is_plan(path) else sha256_file(path)

    # ---- ledger: one hash-chained JSONL file per clone, committed to git
    def ledger_dir(self):
        return os.path.join(self.docs, "audit")

    def ledger_file(self):
        return os.path.join(self.ledger_dir(), self.clone_id() + ".jsonl")

    def append(self, event, data=None, intent=None):
        os.makedirs(self.ledger_dir(), exist_ok=True)
        path = self.ledger_file()
        with open(path, "a+", encoding="utf-8") as f:
            try:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass
            f.seek(0)
            lines = [l for l in f.read().splitlines() if l.strip()]
            prev, seq = "GENESIS", 0
            if lines:
                last = json.loads(lines[-1])
                prev, seq = last["hash"], last["seq"]
            rec = {"seq": seq + 1, "ts": now(), "event": event, "intent": intent,
                   "actor": self.identity(), "data": data or {}, "prev": prev}
            rec["hash"] = sha256_bytes(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode())
            f.seek(0, 2)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._events = None
        return rec

    def events(self):
        """All ledger records of all clones, oldest first (read once per process, again after an append)."""
        if self._events is None:
            self._events = self._read_events()
        return self._events

    def _read_events(self):
        out = []
        d = self.ledger_dir()
        if not os.path.isdir(d):
            return out
        for name in sorted(os.listdir(d)):
            if not name.endswith(".jsonl"):
                continue
            for line in read_text(os.path.join(d, name)).splitlines():
                if line.strip():
                    try:
                        rec = json.loads(line)
                        rec["_file"] = name
                        out.append(rec)
                    except ValueError:
                        out.append({"event": "CORRUPT_LINE", "ts": "", "_file": name, "data": {}})
        out.sort(key=lambda r: r.get("ts", ""))
        return out

    # ---- approvals
    def approval_state(self, path):
        """Return (status, last_event): status in missing | draft | approved | stale | rejected."""
        if not path or not os.path.exists(path):
            return "missing", None
        r = rel(self.root, path)
        last = None
        for e in self.events():
            if e.get("event") in ("APPROVED", "REJECTED") and covers(e, r):
                last = e
        if not last:
            return "draft", None
        if last["event"] == "REJECTED":
            return "rejected", last
        if covered_sha(last, r) != self.approval_sha(path):
            return "stale", last
        return "approved", last

    def pending_request(self, path):
        """The approval request for the file as it is now that no approval or rejection has answered yet.
        An INCEPTION request counts only while both of its files are unchanged (its approval line needs that)."""
        if not path or not os.path.exists(path):
            return None
        r, cur, pending = rel(self.root, path), self.approval_sha(path), None
        for e in self.events():
            if e.get("event") in ("APPROVED", "REJECTED") and covers(e, r):
                pending = None
            elif e.get("event") == "APPROVAL_REQUESTED" and covers(e, r):
                files = (e.get("data") or {}).get("files")
                if isinstance(files, dict):
                    pending = e if all(sha256_file(os.path.join(self.root, p)) == h for p, h in files.items()) else None
                else:
                    pending = e if covered_sha(e, r) == cur else None
        return pending

    def released(self, intent):
        """RELEASE approved for the intent (also if release.md changed afterwards): the intent is finished."""
        r = rel(self.root, self.doc(intent, RELEASE_DOC))
        last = None
        for e in self.events():
            if e.get("event") in ("APPROVED", "REJECTED") and covers(e, r):
                last = e
        return last if last and last["event"] == "APPROVED" else None

    def plan_required(self):
        mode = self.cfg.get("plan", "auto")
        if mode == "always":
            return True
        if mode == "never":
            return False
        return bool(self.cfg.get("regulated"))

    def size_small(self, intent):
        return says_small(read_text(self.doc(intent, REQ_DOC)))

    def last_stage_event(self, intent, stage, unit=None):
        last = None
        for e in self.events():
            d = e.get("data") or {}
            if e.get("intent") == intent and e.get("event") in STAGE_EVENTS and d.get("stage") == stage \
                    and (d.get("unit") or None) == (unit or None):
                last = e
        return last

    def design_skipped(self, intent):
        """The application-design stage was skipped and requirements.md still says Size: small."""
        e = self.last_stage_event(intent, "application-design")
        return bool(e) and e["event"] == "STAGE_SKIPPED" and self.size_small(intent)

    # ---- the optional phases (v0.3): Ideation and Operations
    def position(self, e):
        """Where a record is in events() (recording order), so two records can be compared exactly."""
        evs = self.events()
        if getattr(self, "_positions_of", None) is not evs:
            self._positions_of, self._positions = evs, {id(x): k for k, x in enumerate(evs)}
        return self._positions.get(id(e), -1)

    def phase_skips(self, intent, phase):
        """The intent's PHASE_SKIPPED records of a phase (`new` without --ideation, `stage skip <phase>`), oldest
        first."""
        return [e for e in self.events() if e.get("event") == "PHASE_SKIPPED" and e.get("intent") == intent
                and (e.get("data") or {}).get("phase") == phase]

    def ideation_in_use(self, intent):
        """Ideation counts as used when one of its stages has a start or done record newer than the last phase
        skip of Ideation (with no phase skip: any start or done record)."""
        used = skip = -1
        for k, e in enumerate(self.events()):
            if e.get("intent") != intent:
                continue
            d = e.get("data") or {}
            if e.get("event") == "PHASE_SKIPPED" and d.get("phase") == "ideation":
                skip = k
            elif e.get("event") in ("STAGE_STARTED", "STAGE_COMPLETED") and d.get("stage") in IDEATION_IDS:
                used = k
        return used > skip

    def requirements_approved_event(self, intent):
        """The first REQUIREMENTS or INCEPTION approval recorded for the intent (stale or not), or None. Until
        there is one, `stage start <ideation stage>` may re-open a skipped Ideation."""
        return next((e for e in self.events() if e.get("event") == "APPROVED" and e.get("intent") == intent
                     and (e.get("data") or {}).get("kind") in ("REQUIREMENTS", "INCEPTION")), None)

    def last_verify(self):
        for e in reversed(self.events()):
            if e.get("event") == "VERIFY" and e.get("_file") == os.path.basename(self.ledger_file()):
                return e
        return None

    # ---- content fingerprint of the working tree (what verify ran against)
    def contract_form(self, relpath):
        """relpath written under contracts_dir as configured when it is under that folder or under its resolved
        target (a symlinked contracts folder: tool-call paths have their symlinks resolved), else None. On a
        case-insensitive file system the letter case does not count."""
        conf = self.cfg["contracts_dir"]
        for base in (conf, self.contracts_real):
            a, b = (relpath.lower(), base.lower()) if self.case_insensitive else (relpath, base)
            if a == b or a.startswith(b + "/"):
                return conf + relpath[len(base):]
        return None

    def is_owners_file(self, relpath):
        return self.contract_form(relpath) == self.cfg["contracts_dir"] + "/OWNERS"

    def is_contract(self, relpath):
        """A contract file: under contracts_dir, except its OWNERS file and the changes/ requests (records)."""
        c, base = self.contract_form(relpath), self.cfg["contracts_dir"]
        return bool(c) and c != base and c != base + "/OWNERS" and not c.startswith(base + "/changes/")

    def is_record_path(self, relpath):
        """Process records, not product code: fingerprint_exclude (aidlc-docs/**, .kiro/**), but contracts count
        as code."""
        return matches(relpath, self.cfg.get("fingerprint_exclude")) and not self.is_contract(relpath)

    def fingerprint(self):
        """Content fingerprint of the product code: every tracked file and every untracked, not-ignored file,
        except record paths (see is_record_path) and the per-clone .aidlc-lean/ state. Computed once per process."""
        if self._fingerprint is _UNSET:
            self._fingerprint = self._compute_fingerprint()
        return self._fingerprint

    def page_code_is(self, fp):
        """Is fp (a verify's or a `lean release` run's code fingerprint) the code, as the generated region of
        aidlc-state.md judges it? The region is committed, so it must read the same in every clone at a commit:
        fp counts when it is the working tree's fingerprint (verify, then commit: right after verify the page says
        so) or the committed code's (HEAD's tree, so another clone's untracked .DS_Store or uncommitted edit changes
        no row). The gates and `lean status` outside the region go by the working tree alone."""
        return bool(fp) and (fp == self.fingerprint() or fp == self.head_fingerprint())

    def head_fingerprint(self):
        """The code fingerprint of the committed product code (HEAD's tree, the same records left out), or None
        without a commit. Computed once per process."""
        if self._committed is _UNSET:
            self._committed = self._compute_committed()
        return self._committed

    def _compute_committed(self):
        try:
            code, out, _ = self._git(["ls-tree", "-r", "-z", "HEAD"])  # paths relative to the project folder
        except subprocess.TimeoutExpired:
            return None
        if code != 0:  # no commit yet
            return None
        entries = {}
        for rec in out.split(b"\0"):
            meta, _, name = rec.partition(b"\t")
            parts = meta.split(b" ")
            p = os.fsdecode(name)
            if name and len(parts) >= 3 and not self.is_record_path(p) and not p.startswith(".aidlc-lean/"):
                entries[p] = "%s %s" % (parts[0].decode(), parts[2].decode())  # as `ls-files -s`: mode, blob id
        h = hashlib.sha256()
        for p in sorted(entries):
            h.update(("%s\0%s\n" % (p, entries[p])).encode("utf-8", "surrogateescape"))
        return h.hexdigest()

    def _git(self, args, env=None, data=None, timeout=110):
        """Run git in the project root with bytes in and out. Raises subprocess.TimeoutExpired."""
        try:
            p = subprocess.run(["git"] + args, cwd=self.root, input=data, capture_output=True, env=env,
                               timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            raise
        except (OSError, subprocess.SubprocessError):
            return 1, b"", b""

    def _compute_fingerprint(self):
        try:
            code, out, _ = self._git(["ls-files", "-c", "-o", "--exclude-standard", "-z"])
            if code != 0:
                return None
            paths = sorted(p for p in set(os.fsdecode(x) for x in out.split(b"\0") if x)
                           if not self.is_record_path(p) and not p.startswith(".aidlc-lean/"))
            fp = self._fingerprint_from_index(paths)
        except subprocess.TimeoutExpired:
            return None
        return fp if fp is not None else self._fingerprint_by_reading(paths)

    def _fingerprint_from_index(self, paths):
        """Hash the blob ids git computes in a private copy of the index. git re-reads only files whose stat
        data changed (its own stat cache); the refreshed copy is kept in .aidlc-lean/fingerprint.index for the
        next run. No objects are written to the repository (update-index --info-only)."""
        code, out, _ = self._git(["rev-parse", "--git-path", "index"])
        if code != 0 or not out.strip():
            return None
        real_index = os.path.join(self.root, os.fsdecode(out.strip()))
        cache = os.path.join(self.local, "fingerprint.index")
        if os.path.isfile(cache):
            fp = self._fingerprint_with_seed(paths, cache, cache)
            if fp is not None:
                return fp
            try:
                os.unlink(cache)  # unusable cache: start again from git's own index
            except OSError:
                pass
        return self._fingerprint_with_seed(paths, real_index, cache)

    def _fingerprint_with_seed(self, paths, seed, cache):
        try:
            os.makedirs(self.local, exist_ok=True)
            self._drop_stale_fingerprint_dirs()
            work = tempfile.mkdtemp(prefix="fp-", dir=self.local)
        except OSError:
            return None
        try:
            index = os.path.join(work, "index")
            try:
                shutil.copy2(seed, index)  # copy2 keeps the mtime git needs for its racy-file check
            except OSError:
                pass  # no index yet (new repository): git starts an empty one
            env = dict(os.environ, GIT_INDEX_FILE=index)
            cfg = ["-c", "core.checkStat=default", "-c", "core.trustctime=true"]
            files = [p for p in paths if not p.endswith("/")]  # "x/" = an untracked nested repository
            unreadable = set()
            for _ in range(10):  # --replace: a cached x/y entry gives way when x is a file again (and vice versa)
                todo = b"".join(os.fsencode(p) + b"\0" for p in files if p not in unreadable)
                code, _, err = self._git(cfg + ["update-index", "--add", "--remove", "--replace", "--info-only", "-z",
                                                "--stdin"], env=env, data=todo)
                if code == 0:
                    break
                m = re.search(rb"Unable to process path (.+)", err)
                bad = os.fsdecode(m.group(1).strip()) if m else None
                if bad is None or bad in unreadable or bad not in files:
                    return None
                unreadable.add(bad)  # e.g. no read permission: fingerprinted as unreadable, like a missing file
            else:
                return None
            code, out, _ = self._git(["ls-files", "-s", "-z"], env=env)
            if code != 0:
                return None
            wanted, entries, stale = set(paths), {}, []
            for rec in out.split(b"\0"):
                meta, _, name = rec.partition(b"\t")
                if not name:
                    continue
                p = os.fsdecode(name)
                if p in wanted and p not in unreadable:
                    mode, oid = meta.split(b" ")[:2]
                    entries[p] = "%s %s" % (mode.decode(), oid.decode())
                else:
                    stale.append(name)
            h = hashlib.sha256()
            for p in paths:
                kind = entries.get(p) or ("dir" if p.endswith("/") else "unreadable" if p in unreadable else "deleted")
                h.update(("%s\0%s\n" % (p, kind)).encode("utf-8", "surrogateescape"))
            digest = h.hexdigest()
            try:  # keep the refreshed copy as the next run's stat cache (best effort)
                keep = not stale or self._git(["update-index", "--force-remove", "-z", "--stdin"], env=env,
                                              data=b"".join(n + b"\0" for n in stale))[0] == 0
                if keep and os.path.exists(index):
                    os.replace(index, cache)  # atomic; parallel hooks each leave a valid cache
            except (OSError, subprocess.TimeoutExpired):
                pass
            return digest
        except (OSError, ValueError):  # ValueError: unexpected ls-files output; the caller falls back
            return None
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _drop_stale_fingerprint_dirs(self):
        """Remove work folders left behind by a killed hook process."""
        for name in os.listdir(self.local):
            path = os.path.join(self.local, name)
            try:
                if name.startswith("fp-") and time.time() - os.path.getmtime(path) > 3600:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass

    def _fingerprint_by_reading(self, paths):
        """Fallback when git's index cannot be used: read and hash every file."""
        h = hashlib.sha256()
        for p in paths:
            fh = sha256_file(os.path.join(self.root, p)) or "DELETED"
            h.update(("%s\0%s\n" % (p, fh)).encode("utf-8", "surrogateescape"))
        return h.hexdigest()

    def protected_files(self):
        pats = self.cfg.get("protected_paths") or []
        if not pats:
            return {}
        code, out = run(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], self.root, timeout=120)
        files = [x for x in out.split("\0") if x] if code == 0 else []
        return {p: sha256_file(os.path.join(self.root, p)) for p in sorted(files) if matches(p, pats)}

    # ---- multi-team
    def owners(self):
        path = os.path.join(self.root, self.cfg["contracts_dir"], "OWNERS")
        rules = []
        for line in read_text(path).splitlines():
            line = line.split("#", 1)[0].strip()
            if len(line.split()) >= 2:
                glob, team = line.split()[:2]
                rules.append((glob, team))
        return rules

    def contract_match(self, relpath, globs):
        """matches() for contract globs (OWNERS, a CR's Paths), written with contracts_dir as configured: relpath is
        read in that form (contract_form), and the letter case does not count where the file system has none."""
        relpath = self.contract_form(relpath) or relpath
        globs = [g[2:] if g.startswith("./") else g for g in globs]
        if self.case_insensitive:
            return matches(relpath.lower(), [g.lower() for g in globs])
        return matches(relpath, globs)

    def owner_of(self, relpath):
        owner = None
        for glob, team in self.owners():
            if self.contract_match(relpath, [glob]):
                owner = team  # last match wins, like CODEOWNERS
        return owner

    def cr_files(self):
        d = os.path.join(self.root, self.cfg["contracts_dir"], "changes")
        if not os.path.isdir(d):
            return []
        return [os.path.join(d, n) for n in sorted(os.listdir(d)) if n.startswith("CR-") and n.endswith(".md")]

    def cr_path(self, cid):
        d = os.path.join(self.root, self.cfg["contracts_dir"], "changes")
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if name == cid + ".md" or name.startswith(cid + "-"):
                    return os.path.join(d, name)
        return None

    @staticmethod
    def cr_fields(path):
        text = read_text(path)
        f = {}
        for key in ("Owner team", "Requested by team", "Paths"):
            m = re.search(r"(?im)^\s*[-*]?\s*%s\s*:\s*(.+)$" % re.escape(key), text)
            f[key] = m.group(1).strip() if m else ""
        f["paths"] = [p.strip() for p in f["Paths"].split(",") if p.strip()]
        m = re.match(r"(CR-[A-Za-z0-9_]+-\d+)(-|\.md)", os.path.basename(path))
        f["id"] = m.group(1) if m else os.path.basename(path)[:-3]
        return f

    def cr_closed(self, cid):
        """The CR_CLOSED event of a change request (`cr close`), or None while it is open."""
        for e in self.events():
            if e.get("event") == "CR_CLOSED" and (e.get("data") or {}).get("id") == cid:
                return e
        return None

    def approved_cr_for(self, relpath, owner):
        """The id of an open change request, approved by the owner team, that unlocks relpath for this clone's
        team: only the team that requested it (its `Requested by team`) may edit the owner's contract."""
        me = team_key(self.team())
        for path in self.cr_files():
            f = self.cr_fields(path)
            if not self.contract_match(relpath, f["paths"]) or not me or team_key(f["Requested by team"]) != me:
                continue
            status, ev = self.approval_state(path)
            if status == "approved" and (ev["actor"].get("team") == owner) and not self.cr_closed(f["id"]):
                return f["id"]
        return None

    def cr_state(self, path):
        """A change request as status and audit.md show it: 'closed', or its approval state while it is open."""
        f = self.cr_fields(path)
        if self.cr_closed(f["id"]):
            return "closed"
        s, _ = self.approval_state(path)
        if s == "approved":
            return "open, approved"
        if s in ("rejected", "stale"):
            return "open, %s" % s
        return "open, waiting for team %s" % (f["Owner team"] or "?")


def intent_title(pj, intent):
    for e in reversed(pj.events()):
        if e.get("event") == "INTENT_CREATED" and e.get("intent") == intent and e.get("data", {}).get("title"):
            return e["data"]["title"]
    m = re.search(r"(?m)^#\s*AI-DLC State:\s*(.+)$", read_text(pj.doc(intent, STATE_DOC)))
    return m.group(1).strip() if m else re.sub(r"^\d{6}-", "", intent).replace("-", " ")


# ---------------------------------------------------------------- what approvals cover
def file_target(pj, kind, path):
    return {"kind": kind, "path": rel(pj.root, path), "sha256": pj.approval_sha(path)}


def approval_target(pj, intent, kind, unit=None, given_hash=None, approving=False):
    """What a request, approval or rejection of `kind` covers: (target, None) or (None, error).
    target: kind, sha256 and either path (one file) or paths + files {path: sha256} (INCEPTION); unit for PLAN."""
    if kind.startswith("CR-"):
        path = pj.cr_path(kind)
        if not path:
            return None, "there is no %s file in %s/changes/" % (kind, pj.cfg["contracts_dir"].rstrip("/"))
        closed = pj.cr_closed(kind)
        if closed:
            return None, "%s was closed on %s (%s); a further change needs a new change request (`%s cr new`)" % (
                kind, closed["ts"][:10], one_line((closed.get("data") or {}).get("reason"), 120), TOOL)
        return file_target(pj, kind, path), None
    if kind not in APPROVAL_KINDS:
        return None, ("unknown kind %s (kinds: IDEATION, REQUIREMENTS, DESIGN, INCEPTION, PLAN, RELEASE, "
                      "CR-<team>-<n>)" % kind)
    if not intent:
        return None, "there is no active intent"
    if kind == "IDEATION":  # every Ideation page that exists, "\0"-joined in stage order
        if not pj.ideation_in_use(intent):
            return None, "%s does not use Ideation (%s)" % (intent, ideation_skip_text(pj, intent))
        missing = [STAGE_BY_ID[s].name for s in IDEATION_REQUIRED
                   if not os.path.isfile(pj.doc(intent, STAGE_BY_ID[s].doc))]
        if missing:
            return None, ("IDEATION needs the pages of Intent Capture, Scope Definition and Approval Handoff; %s has "
                          "no page yet for %s (`%s stage start <id>`)" % (intent, ", ".join(missing), TOOL))
        return ideation_target(pj, intent), None
    if kind == "INCEPTION":  # requirements.md + "\0" + application-design.md, whichever of the two exist
        paths = [p for p in (pj.doc(intent, REQ_DOC), pj.doc(intent, DESIGN_DOC)) if os.path.isfile(p)]
        if not paths:
            return None, "%s has no requirements.md or application-design.md yet" % intent
        blobs = [read_bytes(p) for p in paths]
        files = [(rel(pj.root, p), sha256_bytes(b)) for p, b in zip(paths, blobs)]
        return {"kind": kind, "paths": [p for p, _ in files], "files": dict(files),
                "sha256": sha256_bytes(b"\0".join(blobs))}, None
    if kind == "PLAN":
        plans = pj.plans(intent)
        if unit:
            if unit not in plans:
                return None, "unit %s has no code-generation plan (create it with `%s stage start code-generation " \
                             "--unit %s`)" % (unit, TOOL, unit)
            hits = [unit]
        elif given_hash:
            hits = [u for u, p in sorted(plans.items()) if (pj.approval_sha(p) or "").startswith(given_hash.lower())]
            if not hits:
                return None, "no code-generation plan of %s has the hash %s (a plan changed since that request?). " \
                             "Ask for a fresh request" % (intent, given_hash[:8])
        else:
            hits = sorted(plans)
        if not hits:
            return None, "%s has no code-generation plan yet (`%s stage start code-generation`)" % (intent, TOOL)
        if len(hits) > 1:
            return None, "%s has several code-generation plans (%s): %s" % (
                intent, ", ".join(hits), "type the approval line with the hash that `request PLAN --unit <unit>` "
                                         "shows" if approving else "use `request PLAN --unit <unit>`")
        target = file_target(pj, kind, plans[hits[0]])
        target["unit"] = hits[0]
        return target, None
    path = pj.doc(intent, {"REQUIREMENTS": REQ_DOC, "DESIGN": DESIGN_DOC, "RELEASE": RELEASE_DOC}[kind])
    if not os.path.isfile(path):
        return None, "%s does not exist yet" % rel(pj.root, path)
    return file_target(pj, kind, path), None


def rejection_target(pj, intent, kind, rest):
    """Like approval_target; a PLAN rejection names its plan by hash (`reject PLAN 1a2b3c4d why`), or is about
    the only plan, or about the plan requested last."""
    if kind != "PLAN":
        return approval_target(pj, intent, kind)
    m = re.match(r"[ \t:：]*([0-9a-fA-F]{6,64})\b", rest or "")
    if m:
        target, _ = approval_target(pj, intent, kind, given_hash=m.group(1))
        if target:
            return target, None
    target, err = approval_target(pj, intent, kind)
    if target or not intent:
        return target, err
    for e in reversed(pj.events()):
        d = e.get("data") or {}
        if e.get("event") == "APPROVAL_REQUESTED" and e.get("intent") == intent and d.get("kind") == "PLAN" \
                and d.get("unit") in pj.plans(intent):
            return approval_target(pj, intent, kind, unit=d["unit"])
    return None, err


def target_data(target):
    return {k: target[k] for k in ("kind", "path", "paths", "files", "sha256", "unit") if target.get(k) is not None}


def approver_keys(target):
    """The approvers lists an approval must pass (INCEPTION also passes the REQUIREMENTS and DESIGN lists;
    the v0.1 key SPEC still restricts requirements and design approvals)."""
    kind = target["kind"]
    if kind.startswith("CR-"):
        return ["CR"]
    if kind == "INCEPTION":
        keys = ["INCEPTION", "REQUIREMENTS", "SPEC"]
        if any(p.endswith("/" + DESIGN_DOC) for p in target.get("paths") or []):
            keys.append("DESIGN")
        return keys
    return [kind, "SPEC"] if kind in ("REQUIREMENTS", "DESIGN") else [kind]


# ---------------------------------------------------------------- Ideation (v0.3): the IDEATION approval
def ideation_target(pj, intent):
    """What IDEATION covers: every Ideation page that exists, in stage order; its sha256 is taken over the pages
    joined with "\\0", and each page's own sha256 is kept (files), as for INCEPTION."""
    paths = [p for p in (pj.doc(intent, s.doc) for s in IDEATION_STAGES) if os.path.isfile(p)]
    blobs = [read_bytes(p) for p in paths]
    files = [(rel(pj.root, p), sha256_bytes(b)) for p, b in zip(paths, blobs)]
    return {"kind": "IDEATION", "paths": [p for p, _ in files], "files": dict(files),
            "sha256": sha256_bytes(b"\0".join(blobs)) if paths else None}


def ideation_skip_text(pj, intent):
    """Why Ideation is not in use, for messages."""
    skips = pj.phase_skips(intent, "ideation")
    if skips:
        return "Ideation skipped: " + one_line((skips[-1].get("data") or {}).get("reason"), 200)
    return "no Ideation record"


def ideation_state(pj, intent):
    """(status, last APPROVED/REJECTED IDEATION event) while Ideation is in use: missing (no initiative brief),
    draft, approved, stale (an Ideation page changed, was added or removed since the approval) or rejected."""
    last = None
    for e in pj.events():
        if e.get("event") in ("APPROVED", "REJECTED") and e.get("intent") == intent \
                and (e.get("data") or {}).get("kind") == "IDEATION":
            last = e
    if not last:
        return ("draft" if os.path.isfile(pj.doc(intent, HANDOFF_DOC)) else "missing"), None
    if last["event"] == "REJECTED":
        return "rejected", last
    return ("approved" if last["data"].get("sha256") == ideation_target(pj, intent)["sha256"] else "stale"), last


def ideation_pending(pj, intent):
    """The IDEATION request that no approval or rejection has answered yet, while the Ideation pages are still the
    ones it covers (none added, removed or changed) and its approval line would be recorded (Intent Capture, Scope
    Definition and Approval Handoff recorded done: a stage started again after the request waits for its `stage
    done`), else None. So Stage progress and Next offer the line only while the prompt hook takes it."""
    pending = None
    for e in pj.events():
        d = e.get("data") or {}
        if e.get("intent") != intent or d.get("kind") != "IDEATION":
            continue
        if e.get("event") in ("APPROVED", "REJECTED"):
            pending = None
        elif e.get("event") == "APPROVAL_REQUESTED":
            pending = e
    if pending and pending["data"].get("sha256") == ideation_target(pj, intent)["sha256"] \
            and not ideation_undone(pj, intent):
        return pending
    return None


def ideation_problem(pj, intent, ok):
    """(message, short) when Ideation is in use and IDEATION is not in ok (approved; also stale in standard mode),
    else None. Code writes, release and the REQUIREMENTS/INCEPTION approval need IDEATION then."""
    if not intent or not pj.ideation_in_use(intent):
        return None
    s, _ = ideation_state(pj, intent)
    if s in ok:
        return None
    pend = ideation_pending(pj, intent)
    if pend:
        fix = "the request is out: wait for the human to type `approve IDEATION %s`" % pend["data"]["sha256"][:8]
    elif s == "rejected":
        fix = "revise the Ideation pages as the human asked and get them approved (`%s request IDEATION`)" % TOOL
    elif s == "stale":
        fix = ("an Ideation page changed (or was added or removed) since its approval: get IDEATION approved again "
               "(`%s request IDEATION`)" % TOOL)
    else:
        fix = ("finish the Ideation pages (skill aidlc-lean-ideation) and get the human's approval (`%s request "
               "IDEATION`)" % TOOL)
    return "Ideation is in use for %s and IDEATION is %s: %s" % (intent, s, fix), "IDEATION is %s" % s


def ideation_note(pj, intent):
    """(mark, detail) of the Approval Handoff row from the IDEATION approval, or None when nothing was requested or
    decided."""
    s, last = ideation_state(pj, intent)
    d = last["data"] if last else {}
    if s == "approved":
        return "x", "approved via IDEATION (sha %s) · %s" % (d["sha256"][:8], last["ts"][:10])
    pend = ideation_pending(pj, intent)
    if pend:
        return "A", "waiting for approval: approve IDEATION %s" % pend["data"]["sha256"][:8]
    if s == "rejected":
        return "-", "rejected · %s: %s" % (last["ts"][:10], one_line(d.get("words"), 120))
    if s == "stale":
        return "-", ("stale: an Ideation page changed since it was approved via IDEATION (sha %s) · %s; request it "
                     "again" % ((d.get("sha256") or "?")[:8], last["ts"][:10]))
    return None


# ---------------------------------------------------------------- the code-write gate
def gate_problems(pj, intent, relpath=None, strict=False):
    """What stops code changes for an intent, as (gate, message, short) tuples; empty when code may be written.
    In standard mode a stale approval still counts (status shows it as stale); in regulated mode, or with
    strict (release), it does not."""
    ok = ("approved",) if (strict or pj.cfg.get("regulated")) else ("approved", "stale")
    released = pj.released(intent)
    if released:
        return [("released", "%s is released (RELEASE approved). Start follow-ups and fixes as a new intent: "
                             "`%s new <slug>`." % (intent, TOOL), "already released")]
    out = []
    idea = ideation_problem(pj, intent, ok)  # Ideation in use: IDEATION comes first
    if idea:
        out.append(("ideation", idea[0] + " before writing code.", idea[1]))
    req = pj.doc(intent, REQ_DOC)
    s, _ = pj.approval_state(req)
    if s not in ok:
        out.append(("requirements", "%s is %s. Finish it and get the human's approval (`%s request REQUIREMENTS`, or "
                    "`request INCEPTION` together with the application design) before writing code."
                    % (rel(pj.root, req), s, TOOL), "requirements.md is %s" % s))
    design = pj.doc(intent, DESIGN_DOC)
    s, _ = pj.approval_state(design)
    if s not in ok and not pj.design_skipped(intent):
        if s == "missing" and pj.size_small(intent):
            hint = ("write it and get it approved (`%s request DESIGN`), or, as requirements.md says Size: small, "
                    "skip it with `%s stage skip application-design --reason \"<why>\"`" % (TOOL, TOOL))
        else:
            hint = ("write it (`%s stage start application-design`) and get the human's approval (`%s request "
                    "DESIGN`, or `request INCEPTION` together with the requirements)" % (TOOL, TOOL))
        out.append(("design", "the application design (%s) is %s; %s before writing code."
                    % (rel(pj.root, design), s, hint), "application-design.md is %s (and not skipped)" % s))
    if pj.plan_required():
        plans = pj.plans(intent)
        if relpath:  # a code write: the plans of the units whose paths hold it (None: no unit claims it)
            units = pj.units_for_path(intent, relpath)
        else:  # release: every unit (code-generation is never skipped) and every plan that exists
            units = pj.units(intent)[0]
            units = units + [u for u in plans if u not in units]
        if units:
            todo = [(u, plans.get(u) or pj.doc(intent, PLAN_DOC.format(unit=u)), "") for u in units]
        else:
            why = " (%s is in no unit's paths in unit-of-work.md, so every plan counts)" % relpath if relpath else ""
            todo = [(u, p, why) for u, p in sorted(plans.items())]
            if not plans:
                out.append(("plan", "%s has no code-generation plan yet%s. Write one (`%s stage start code-generation "
                            "--unit <unit>`) and get it approved (`%s request PLAN --unit <unit>`) before writing "
                            "code." % (intent, why, TOOL, TOOL), "no code-generation plan"))
        for u, path, why in todo:
            s, _ = pj.approval_state(path)
            if s not in ok:
                out.append(("plan", "the code-generation plan of unit %s (%s) is %s%s. %s"
                            % (u, rel(pj.root, path), s, why, plan_fix(pj, u, path, s)),
                            "the plan of unit %s is %s" % (u, s)))
    return out


def plan_fix(pj, unit, path, status):
    """What gets a unit's code-generation plan approved, by its approval status (one or two sentences)."""
    req = "`%s request PLAN --unit %s`" % (TOOL, unit)
    pend = pj.pending_request(path)
    if pend:
        return ("The request is out: wait for the human to type `approve PLAN %s`, then write its code."
                % pend["data"]["sha256"][:8])
    if status == "missing":
        fix = "Write it (`%s stage start code-generation --unit %s`) and get it approved (%s)" % (TOOL, unit, req)
    elif status == "stale":
        fix = ("It changed after its approval (ticking steps does not count, editing a step's text does): get it "
               "approved again (%s)" % req)
    elif status == "rejected":
        fix = "Revise it as the human asked and get it approved (%s)" % req
    else:
        fix = "Finish it and get it approved (%s)" % req
    return fix + " before writing its code."


# ---------------------------------------------------------------- stage progress (aidlc-state.md and status)
def requirements_ideation_problem(pj, intent):
    """ideation_problem for the REQUIREMENTS/INCEPTION request and approval: a stale IDEATION counts in standard
    mode, as for code writes."""
    return ideation_problem(pj, intent, ("approved",) if pj.cfg.get("regulated") else ("approved", "stale"))


def pending_refused(pj, intent, pend):
    """Why the prompt hook would refuse the approval line of a pending request now, else None: REQUIREMENTS or
    INCEPTION while Ideation is in use and IDEATION is not approved (§9.2), RELEASE while `lean release` would not
    pass (§8.1). Stage progress then does not offer that line. Only what every clone sees the same way counts here
    (the ledger and the files, not this clone's own verify): the page is committed."""
    kind = (pend.get("data") or {}).get("kind")
    if kind in ("REQUIREMENTS", "INCEPTION"):
        idea = requirements_ideation_problem(pj, intent)
        return "Ideation is in use and %s (the requirements are approved after it)" % idea[1] if idea else None
    if kind == "RELEASE":
        problems, _ = release_problems(pj, intent, local=False)
        return "not ready to release: " + "; ".join(problems) if problems else None
    return None


def approval_note(pj, path, intent=None):
    """(mark, detail) from a file's approval record, or None when nothing was requested or decided. With intent,
    a pending request whose approval line the prompt hook would refuse now is not shown as waiting (no line)."""
    s, last = pj.approval_state(path)
    d = last["data"] if last else {}
    via = "" if d.get("kind") in ("PLAN", "RELEASE", None) else " via %s" % d.get("kind")
    if s == "approved":
        return "x", "approved%s (sha %s) · %s" % (via, d["sha256"][:8], last["ts"][:10])
    pend = pj.pending_request(path)
    if pend:
        why = pending_refused(pj, intent, pend) if intent else None
        if why:
            return "-", "%s requested; the approval waits: %s" % (pend["data"]["kind"], why)
        return "A", "waiting for approval: approve %s %s" % (pend["data"]["kind"], pend["data"]["sha256"][:8])
    if s == "rejected":
        return "-", "rejected · %s: %s" % (last["ts"][:10], one_line(d.get("words"), 120))
    if s == "stale":
        return "-", "stale: changed since it was approved%s (sha %s) · %s; request it again" % (
            via, d["sha256"][:8], last["ts"][:10])
    return None


def stage_event(pj, intent, st, unit=None):
    """The record that decides a stage's status: its own last start, done or skip record, or a later phase skip
    that covered it. Once Ideation is in use again (a start or done record newer than its last phase skip), the
    phase skips of Ideation no longer count: the start supersedes them. So does a skip of a stage Ideation needs
    (intent-capture, scope-definition, approval-handoff), recorded while Ideation was not in use: the stage is
    required again, and it has no record until it is started or done."""
    ev = pj.last_stage_event(intent, st.id, unit)
    if st.phase not in PHASES:
        return ev
    in_use = st.phase == "ideation" and pj.ideation_in_use(intent)
    if in_use and st.id in IDEATION_REQUIRED and ev and ev["event"] == "STAGE_SKIPPED":
        return None
    covering = [e for e in pj.phase_skips(intent, st.phase) if st.id in ((e.get("data") or {}).get("stages") or [])]
    if not covering or in_use:
        return ev
    skip = covering[-1]
    return skip if ev is None or pj.position(skip) > pj.position(ev) else ev


def stage_recorded(pj, intent, st, unit=None):
    """Has the stage a record that counts (done or skipped, also by a phase skip)? From the records, not from the
    Stage progress mark (a done Approval Handoff shows `-` until IDEATION is decided)."""
    ev = stage_event(pj, intent, st, unit)
    return bool(ev) and ev["event"] in ("STAGE_COMPLETED", "STAGE_SKIPPED", "PHASE_SKIPPED")


def ideation_asked(pj, intent):
    """The intent's first IDEATION request, approval or rejection, or None. From then on the human decides
    Ideation: it can no longer be dropped, and Next no longer points to the optional Ideation stages (a new page
    would void the request or the approval)."""
    return next((e for e in pj.events() if e.get("intent") == intent and e.get("event") in (
        "APPROVAL_REQUESTED", "APPROVED", "REJECTED") and (e.get("data") or {}).get("kind") == "IDEATION"), None)


def ideation_undone(pj, intent):
    """The stages Ideation needs (intent-capture, scope-definition, approval-handoff) that are not recorded as done,
    as names; IDEATION is requested and approved only once all three are."""
    out = []
    for sid in IDEATION_REQUIRED:
        ev = stage_event(pj, intent, STAGE_BY_ID[sid])
        if not (ev and ev["event"] == "STAGE_COMPLETED"):
            out.append(STAGE_BY_ID[sid].name)
    return out


def ideation_undone_text(pj, intent):
    return ("IDEATION needs Intent Capture, Scope Definition and Approval Handoff done while Ideation is in use (they "
            "cannot be skipped then); not done yet: %s (`%s stage done <id> --note ...` once its page is written)"
            % (", ".join(ideation_undone(pj, intent)), TOOL))


def has_record(mark):
    """A stage has a record once it is done or skipped (started, waiting or not started: no record yet)."""
    return mark in ("x", "S")


def stage_status(pj, intent, st, unit):
    """(mark, detail): x done, S skipped, - in progress, A waiting for approval, ' ' not started."""
    if st.id == "build-and-test":
        return build_status(pj, intent)
    ev = stage_event(pj, intent, st, unit)
    path = pj.doc(intent, st.doc.format(unit=unit))
    started = ("-", "in progress") if (ev or os.path.exists(path)) else (" ", "")
    if ev and ev["event"] == "PHASE_SKIPPED":
        return "S", "skipped: " + one_line(ev["data"].get("reason"), 200)
    if ev is None and st.id in IDEATION_REQUIRED and pj.ideation_in_use(intent):
        own = pj.last_stage_event(intent, st.id)
        if own and own["event"] == "STAGE_SKIPPED":  # skipped before Ideation was used (stage_event)
            started = (started[0], "required now that Ideation is in use (its skip from before no longer counts)")
    if st.id == "approval-handoff" and pj.ideation_in_use(intent):  # the IDEATION approval completes Ideation
        note = ideation_note(pj, intent)
        if note:
            return note
        if ev and ev["event"] == "STAGE_COMPLETED":
            undone = [n for n in ideation_undone(pj, intent) if n != st.name]
            return "-", "done · %s%s; %s" % (ev["ts"][:10], " (edited since)" if edited_since(pj, ev) else "",
                                             "IDEATION also needs %s done" % ", ".join(undone) if undone
                                             else "waiting for `request IDEATION`")
        return started
    if st.id == "release":
        done = pj.released(intent)
        if done:
            return "x", "released: approved (sha %s) · %s" % (done["data"]["sha256"][:8], done["ts"][:10])
        written = last_release_write(pj, intent)
        if os.path.exists(path) and not written:
            return "-", "release.md was not written by `release`: run `release` (`request RELEASE` needs its page)"
        if os.path.exists(path) and not pj.page_code_is(written["data"].get("fingerprint")):
            return "-", "release.md is for older code (written %s): run `verify` and `release` again" % (
                written["ts"][:10])
        missing = release_missing(pj, intent) if written and os.path.exists(path) else []
        pend = pj.pending_request(path) if missing else None
        if missing and not (pend and pending_refused(pj, intent, pend)):  # a refusal reason first
            return "-", "release.md (written %s) does not list %s: run `release` again" % (
                written["ts"][:10], missing_text(missing))
        note = approval_note(pj, path, intent)
        if note:
            return note
        if os.path.exists(path):
            return "-", "release.md written%s; fill in Open items, then `request RELEASE`" % (
                " · " + ev["ts"][:10] if ev else "")
        return " ", ""
    if st.id in ("requirements", "application-design"):
        note = approval_note(pj, path, intent)
        if note:
            return note
        kind = "REQUIREMENTS" if st.id == "requirements" else "DESIGN"
        if ev and ev["event"] == "STAGE_SKIPPED":
            if pj.size_small(intent):
                return "S", "skipped: " + one_line(ev["data"].get("reason"), 200)
            return "-", "skipped, but requirements.md no longer says Size: small: write it and request DESIGN"
        if ev and ev["event"] == "STAGE_COMPLETED":
            return "-", "done · %s%s; waiting for `request %s` (or INCEPTION)" % (
                ev["ts"][:10], " (edited since)" if edited_since(pj, ev) else "", kind)
        return started
    if st.id == "code-generation":
        plan = approval_note(pj, path, intent)
        if ev and ev["event"] == "STAGE_COMPLETED":
            return "x", "done · %s%s%s" % (ev["ts"][:10], " (edited since)" if edited_since(pj, ev) else "",
                                          ("; plan " + plan[1]) if plan else "")
        if plan:
            return ("-", "plan %s; code in progress" % plan[1]) if plan[0] == "x" else (plan[0], "plan " + plan[1])
        if pj.plan_required() and os.path.exists(path):
            return "-", "plan in progress; it needs approval: `request PLAN --unit %s`" % unit
        return started
    if ev and ev["event"] == "STAGE_COMPLETED":
        return "x", "done · %s%s" % (ev["ts"][:10], " (edited since)" if edited_since(pj, ev) else "")
    if ev and ev["event"] == "STAGE_SKIPPED":
        return "S", "skipped: " + one_line(ev["data"].get("reason"), 200)
    return started


def edited_since(pj, ev):
    """Has a completed stage's output changed since its STAGE_COMPLETED? A code-generation plan is compared the
    way plan_sha256 reads it (ticking a step is no edit) when the record has that hash."""
    d = ev.get("data") or {}
    outs = d.get("outputs") or {}
    if d.get("plan_sha256") and len(outs) == 1:
        return plan_sha256(os.path.join(pj.root, list(outs)[0])) != d["plan_sha256"]
    return any(sha256_file(os.path.join(pj.root, p)) != h for p, h in outs.items())


def open_code_units(pj, intent):
    """The units whose code generation has no STAGE_COMPLETED yet (every unit and every plan counts)."""
    out = []
    for u in stage_units(pj, intent, STAGE_BY_ID["code-generation"]):
        ev = pj.last_stage_event(intent, "code-generation", u)
        if not (ev and ev["event"] == "STAGE_COMPLETED"):
            out.append(u)
    return out


def build_status(pj, intent):
    lv = None
    for e in pj.events():
        if e.get("event") == "VERIFY" and e.get("intent") == intent:
            lv = e
    if not lv:
        return " ", ""
    d = lv["data"]
    if not d.get("ok"):
        return "-", "last verify FAILED · %s" % when(lv["ts"])
    if pj.released(intent) or pj.page_code_is(d.get("fingerprint")):  # the committed page: see page_code_is
        partial = open_code_units(pj, intent)
        if partial:  # Build and Test is done once every unit's code is: until then a PASS covers part of it
            return "-", "verify PASS on partial code · %s (code fingerprint %s); code generation not done yet: %s" % (
                when(lv["ts"]), (d.get("fingerprint") or "")[:8], ", ".join(partial))
        return "x", "verify PASS · %s (code fingerprint %s)" % (when(lv["ts"]), (d.get("fingerprint") or "")[:8])
    return "-", "code changed since the last verify PASS · %s: run verify again" % when(lv["ts"])


def stage_units(pj, intent, st):
    if not st.per_unit:
        return [None]
    names = list(pj.units(intent)[0])
    if st.id == "code-generation":  # plans of units that unit-of-work.md does not list still count
        names += [u for u in pj.plans(intent) if u not in names]
    return names


def stage_rows(pj, intent):
    """(stage, unit) in AI-DLC order. The per-unit stages come unit by unit (each unit's designs, then its code
    generation), as in AI-DLC's per-unit loop; a plan for a unit that unit-of-work.md does not list comes last."""
    names = list(pj.units(intent)[0])
    rows = []
    for st in STAGES:
        if not st.per_unit:
            rows.append((st, None))
        elif st is PER_UNIT_STAGES[0]:
            rows += [(s, u) for u in names for s in PER_UNIT_STAGES]
            rows += [(STAGE_BY_ID["code-generation"], u) for u in pj.plans(intent) if u not in names]
    return rows


def stage_label(st, unit):
    return st.name + (" (%s)" % unit if unit else "")


def grouped_phases(pj, intent):
    """{phase: (mark, detail)} for the optional phases shown as ONE line in Stage progress: every stage of the
    phase skipped by one phase skip (`new` without --ideation, `stage skip <phase>`). An intent with no Ideation
    record at all (started before v0.3) shows Ideation as one line too."""
    out = {}
    for phase, stages in PHASE_STAGES.items():
        evs = [stage_event(pj, intent, st) for st in stages]
        first = evs[0]
        if first and first["event"] == "PHASE_SKIPPED" and all(e is first for e in evs):
            out[phase] = ("S", "skipped: " + one_line(first["data"].get("reason"), 200))
        elif phase == "ideation" and not any(evs) and not pj.phase_skips(intent, phase) \
                and not any(os.path.exists(pj.doc(intent, st.doc)) for st in stages):
            out[phase] = ("S", "not used (no Ideation record: the intent was started before AI-DLC Lean 0.3)")
    return out


def progress_lines(pj, intent, override=None):
    """The Stage progress list. override: {stage id: (mark, detail)} shown instead of the stage's status. A phase
    whose stages were all skipped by one phase skip is one line: `- [S] Ideation — skipped: <reason>`."""
    out, grouped, shown = [], grouped_phases(pj, intent), set()
    for st, unit in stage_rows(pj, intent):
        if st.phase in grouped:
            if st.phase not in shown:
                shown.add(st.phase)
                mark, detail = grouped[st.phase]
                out.append("- [%s] %s — %s" % (mark, PHASES[st.phase], detail))
            continue
        mark, detail = (override or {}).get(st.id) or stage_status(pj, intent, st, unit)
        out.append("- [%s] %s%s" % (mark, stage_label(st, unit), (" — " + detail) if detail else ""))
    return out


def open_stages(pj, intent, ids=None):
    """Labels of the stages with a page the agent writes that are not started or still in progress (no record
    yet), in AI-DLC order; ids narrows the list. Without ids it leaves out what is optional until after RELEASE
    (ci-pipeline and Operations), Ideation while it is not in use, and, once IDEATION was requested, the optional
    Ideation stages not started (their page would be new to it: it voids the request or the approval). One already
    started is still to be finished."""
    idea = pj.ideation_in_use(intent)
    asked = idea and ideation_asked(pj, intent)

    def wanted(st):
        if ids is not None:
            return st.id in ids
        return st.id not in AFTER_RELEASE_IDS and (idea or st.phase != "ideation")
    out = []
    for st, u in stage_rows(pj, intent):
        if not st.template or not wanted(st):
            continue
        mark = stage_status(pj, intent, st, u)[0]
        if mark == "-" or (mark == " " and not (asked and st.phase == "ideation" and st.id not in IDEATION_REQUIRED)):
            out.append(stage_label(st, u))
    return out


def source_label(e):
    """Who recorded a ledger entry: 'human (prompt)' for what the prompt hook took from the human's own message
    (approvals, rejections, refused approvals, human turns, and the Release record the RELEASE approval writes),
    'hook (...)' for the other hook entries, 'via CLI' for the tool's commands."""
    ev, d = e.get("event"), e.get("data") or {}
    if ev in PROMPT_EVENTS or (ev == "STAGE_COMPLETED" and d.get("stage") == "release"):
        return "human (prompt)"
    return HOOK_LABELS.get(ev, "via CLI")


def actor_text(e, sep=" (team %s)"):
    a = e.get("actor") or {}
    return "%s%s" % (a.get("git_email") or a.get("os_user") or "?", sep % (a.get("team") or "-"))


def kind_label(d):
    return "%s%s" % (one_line(d.get("kind"), 60) or "?", " (%s)" % one_line(d["unit"], 60) if d.get("unit") else "")


LOG_EVENTS = ("STAGE_COMPLETED", "STAGE_SKIPPED", "PHASE_SKIPPED", "APPROVED", "REJECTED", "APPROVAL_REFUSED")


def phase_skip_stages(d):
    """The stages a PHASE_SKIPPED record covered, as names; '' when it covered the whole phase."""
    ids = [s for s in d.get("stages") or [] if s in STAGE_BY_ID]
    if [s.id for s in PHASE_STAGES.get(d.get("phase"), ())] == ids:
        return ""
    return ", ".join(STAGE_BY_ID[s].name for s in ids) or "none"


def log_lines(pj, intent):
    """The Stage log, in recording order: every completed or skipped stage, with its note and outputs (only the
    latest build-and-test, which verify records on every PASS), and every approval, rejection and refused approval
    (kind, sha, who, when). Each entry says who recorded it: the human's prompt, or a CLI command."""
    evs = [e for e in pj.events() if e.get("intent") == intent and e.get("event") in LOG_EVENTS]
    bt = [e for e in evs if e.get("event") == "STAGE_COMPLETED"
          and (e.get("data") or {}).get("stage") == "build-and-test"]
    out = []
    for e in evs:
        d = e.get("data") or {}
        tail = " · %s · by %s · %s" % (when(e.get("ts")), actor_text(e), source_label(e))
        if e["event"] in ("APPROVED", "REJECTED"):
            out += ["", "### %s %s (sha %s)%s" % (kind_label(d), e["event"].lower(), (d.get("sha256") or "?")[:8],
                                                  tail)]
            files = sorted(d["files"]) if isinstance(d.get("files"), dict) else [d.get("path") or "?"]
            out.append("- Covers: " + ", ".join(one_line(pj.short(intent, p), 200) for p in files))
            if e["event"] == "REJECTED":
                out.append("- Words: " + one_line(d.get("words"), 300))
            continue
        if e["event"] == "APPROVAL_REFUSED":
            given = d.get("given")
            out += ["", "### %s approval refused (%s)%s" % (kind_label(d), ("typed " + one_line(given, 64)[:8])
                                                             if given else "no hash typed", tail),
                    "- Reason: " + one_line(d.get("reason"), 300)]
            continue
        if e["event"] == "PHASE_SKIPPED":  # one entry for the phase; the stages only when it covered some of them
            out += ["", "### %s%s" % (PHASES.get(d.get("phase")) or one_line(d.get("phase"), 60), tail),
                    "- Skipped: " + one_line(d.get("reason"))]
            covered = phase_skip_stages(d)
            if covered:
                out.append("- Stages: " + covered)
            continue
        if bt and d.get("stage") == "build-and-test" and e is not bt[-1]:
            continue
        st = STAGE_BY_ID.get(d.get("stage"))
        out += ["", "### %s%s%s" % (st.name if st else one_line(d.get("stage"), 60),
                                    " (%s)" % one_line(d["unit"], 60) if d.get("unit") else "", tail)]
        if e["event"] == "STAGE_SKIPPED":
            out.append("- Skipped: " + one_line(d.get("reason")))
            continue
        out.append("- Did: " + one_line(d.get("note")))
        outs = d.get("outputs") or {}
        if outs:
            out.append("- Outputs: " + ", ".join("%s (sha %s)" % (pj.short(intent, p), (h or "missing")[:8])
                                                 for p, h in sorted(outs.items())))
    return out


def progress_region(pj, intent):
    log = log_lines(pj, intent)
    return "\n".join([BEGIN_MARK, "## Stage progress"] + progress_lines(pj, intent) +
                     ["", "## Stage log"] + (log or ["", "(nothing recorded yet)"]) + [END_MARK])


def replace_region(text, region):
    """Put region between the lean markers; everything else stays as it is. Without (both) markers the region
    goes right after the header (the title line and the lines that follow it)."""
    b = text.find(BEGIN_MARK)
    e = text.find(END_MARK, b + len(BEGIN_MARK)) if b >= 0 else -1
    if b >= 0 and e >= 0:
        return text[:b] + region + text[e + len(END_MARK):]
    lines = text.replace(BEGIN_MARK, "").replace(END_MARK, "").split("\n")
    i = 0
    first = next((k for k, l in enumerate(lines) if l.strip()), None)
    if first is not None and lines[first].startswith("# "):
        i = first + 1
        while i < len(lines) and lines[i].strip() and not lines[i].lstrip().startswith("#"):
            i += 1
    return "\n".join(lines[:i] + [region] + lines[i:])


def update_state_doc(pj, intent):
    """Regenerate only the progress region of aidlc-state.md; the rest (Session notes) belongs to the agent."""
    if not intent or intent not in pj.list_intents():
        return None
    path = pj.doc(intent, STATE_DOC)
    with pj.doc_lock():
        pj._events = None  # read the ledger again under the lock: the last writer has the newest events
        text = read_text(path, None)
        if text is None:
            text = template(STATE_DOC, **doc_vars(pj, intent))
        new = replace_region(text, progress_region(pj, intent))
        if new != text:
            write_text(path, new)
    return path


def refresh_state_doc(pj, intent, prefix=""):
    """update_state_doc for commands and hooks: the record is already in the ledger, so a failure here only
    leaves the page behind until the next command."""
    try:
        update_state_doc(pj, intent)
    except Exception as e:  # noqa: BLE001
        print("%sCould not update aidlc-state.md (%s: %s)." % (prefix, type(e).__name__, e))


def strip_region(text):
    b = text.find(BEGIN_MARK)
    e = text.find(END_MARK, b + 1) if b >= 0 else -1
    return text[:b] + text[e + len(END_MARK):] if b >= 0 and e >= 0 else text


NEXT_HEADING_RE = re.compile(r"(?im)^#{2,4}[ \t]*Next\b([^\n]*)$")
TEAM_SUFFIX_RE = re.compile(r"(?i)^[ \t]*\([ \t]*team[ \t:]+`?([A-Za-z0-9_.-]+)`?[ \t]*\)")


def state_excerpt(pj, intent, max_lines=12):
    """The first items under the Next headings of aidlc-state.md (outside the generated region), as
    [(label, lines)]: with a team, the items under "### Next (team <team>)" first, then those under the generic
    "### Next". Other teams' Next subsections are left out."""
    text = strip_comments(strip_region(read_text(pj.doc(intent, STATE_DOC))))
    mine, team_items, generic = team_key(pj.team()), None, None
    for m in NEXT_HEADING_RE.finditer(text):
        nxt = re.search(r"(?m)^#{1,6}\s", text[m.end():])
        body = text[m.end():m.end() + nxt.start()] if nxt else text[m.end():]
        items = [l for l in body.strip().splitlines()
                 if l.strip() and not re.match(r"^\s*(\d+[.)]|[-*])\s*$", l)][:max_lines]
        team = TEAM_SUFFIX_RE.match(m.group(1))
        if not team:
            if generic is None:
                generic = items
        elif mine and team_key(team.group(1)) == mine and team_items is None:
            team_items = items
    out = []
    if team_items:
        out.append(("Next, team %s" % pj.team(), team_items))
    if generic:
        out.append(("Next", generic))
    return out


def session_notes_untouched(pj, intent):
    """Are the Session notes of aidlc-state.md (from "## Session notes" to the end, outside the generated region)
    still what `new` wrote, whatever day it was rendered on: the template's, or for `new --ideation` the template's
    with the Ideation Status and Next (ideation_session_notes)?"""
    def notes(text):
        text = strip_region(text)
        m = re.search(r"(?im)^##[ \t]*Session notes\b", text)
        return norm_ws(text[m.start():]) if m else None
    cur = notes(read_text(pj.doc(intent, STATE_DOC), ""))
    if cur is None:
        return False
    rendered = template(STATE_DOC, **dict(doc_vars(pj, intent), DATE=DATE_SENTINEL, MODE=MODE_SENTINEL))
    for tpl in (notes(rendered), notes(ideation_session_notes(rendered))):
        if tpl is None:
            continue
        pat = re.escape(tpl).replace(re.escape(DATE_SENTINEL), r"\d{4}-\d{2}-\d{2}").replace(
            re.escape(MODE_SENTINEL), r"[^\n]*")
        if re.fullmatch(pat, cur) is not None:
            return True
    return False


def owner_team(pj, intent):
    """Multi-team: the team that owns (releases) an intent: the `Owner team:` line in the header of its
    aidlc-state.md (`new` writes it), else the team of the clone that ran `new`; None if unknown."""
    text = read_text(pj.doc(intent, STATE_DOC))
    head = re.split(r"(?m)^##[ \t]", text.split(BEGIN_MARK)[0], 1)[0]
    m = re.search(r"(?im)^[ \t>*-]*\**[ \t]*Owner team[ \t]*\**[ \t]*[:：][ \t]*\**[ \t]*`?([A-Za-z0-9_.-]+)", head)
    if m:
        return m.group(1)
    for e in pj.events():
        if e.get("event") == "INTENT_CREATED" and e.get("intent") == intent:
            return (e.get("actor") or {}).get("team") or None
    return None


# ---------------------------------------------------------------- status text
def waiting_for(pj, path):
    """The Next text while an approval request that covers path is out and unanswered, else None."""
    pend = pj.pending_request(path)
    if not pend:
        return None
    return ("wait for the human to type `approve %s %s` (the request is out: show them that line again if needed, "
            "and do not change what it covers)" % (pend["data"]["kind"], pend["data"]["sha256"][:8]))


def last_release_write(pj, intent):
    """The STAGE_STARTED event of the `lean release` run that wrote operations/release.md as it is now, or None: the
    run whose recorded sha256 is the file's, else (Open items filled in since) one whose code fingerprint is the one
    the file names. Chosen by content, not by the order of the records: that is the clones' clocks."""
    path = pj.doc(intent, RELEASE_DOC)
    if not os.path.isfile(path):
        return None
    writes = [e for e in pj.events() if e.get("intent") == intent and e.get("event") == "STAGE_STARTED"
              and (e.get("data") or {}).get("stage") == "release" and "fingerprint" in (e.get("data") or {})]
    sha = sha256_file(path)
    exact = [e for e in writes if e["data"].get("sha256") == sha]
    if exact:
        return exact[-1]
    m = re.search(r"(?m)^- code fingerprint: (\S+)[ \t]*$", read_text(path))
    named = [e for e in writes if m and e["data"].get("fingerprint") == m.group(1)]
    return named[-1] if named else None


def release_rows(pj, intent):
    """[(APPROVED event, row)] of the Approvals table `lean release` writes: every approval of the intent and every
    CR approval (whatever intent the approving clone had active), oldest first."""
    approvals = [e for e in pj.events() if e.get("event") == "APPROVED"]
    out = []
    for k, e in enumerate(approvals):
        d = e.get("data") or {}
        if e.get("intent") == intent or str(d.get("kind", "")).startswith("CR-"):
            out.append((e, "| %s%s | %s %s" % (d["kind"] + (" (%s)" % d["unit"] if d.get("unit") else ""),
                                              superseded_note(pj, intent, e, approvals[k + 1:]), event_paths(d),
                                              approval_cells(e))))
    return out


def approval_cells(e):
    """The last cells of an approval's row in release.md, '| <sha256:12> | <who> (<team>) | <when> |': what names
    that approval (the ledger record) in the table."""
    a, d = e.get("actor") or {}, e.get("data") or {}
    return "| %s | %s (%s) | %s |" % ((d.get("sha256") or "")[:12], a.get("git_email") or a.get("os_user"),
                                      a.get("team") or "-", e.get("ts"))


def approval_key(e):
    """(sha256:12, who (team), when): the last three cells of an approval's row in release.md, whitespace collapsed."""
    a, d = e.get("actor") or {}, e.get("data") or {}
    return tuple(" ".join(str(x).split()) for x in ((d.get("sha256") or "")[:12], "%s (%s)" % (
        a.get("git_email") or a.get("os_user"), a.get("team") or "-"), e.get("ts")))


def approvals_table_keys(text):
    """The approval_key of every row of the Approvals table of a release.md: that section only, outside HTML
    comments, with each cell's whitespace collapsed (a formatter may pad the columns)."""
    m = re.search(r"(?ms)^##[ \t]+Approvals[ \t]*$(.*?)(?=^##[ \t]|\Z)", strip_comments(text))
    keys = set()
    for line in m.group(1).splitlines() if m else []:
        if line.strip().startswith("|"):
            cells = [" ".join(c.split()) for c in table_cells(line)]
            if len(cells) >= 3:
                keys.add(tuple(cells[-3:]))
    return keys


def release_missing(pj, intent):
    """The approvals the Approvals table of operations/release.md should list but does not (RELEASE's own left
    out): approvals recorded, or pulled, after `lean release` wrote it. It goes by the table's rows, not by the
    clocks of the clones; release.md needs `lean release` again while this is not empty."""
    listed = approvals_table_keys(read_text(pj.doc(intent, RELEASE_DOC)))
    return [e for e, _ in release_rows(pj, intent) if (e.get("data") or {}).get("kind") != "RELEASE"
            and approval_key(e) not in listed]


def missing_text(evs):
    """'REQUIREMENTS approved, CR-shop-1 approved' for release_missing."""
    return ", ".join("%s approved" % kind_label(e.get("data") or {}) for e in evs[-3:]) + (
        " and %d more" % (len(evs) - 3) if len(evs) > 3 else "")


def next_step(pj, intent, lv, current):
    """One line: the next thing to do, following AI-DLC's stage order (Inception, then the per-unit loop of
    Construction, then Build and Test and Release) and stopping at the approvals that are due."""
    if pj.released(intent):
        regulated = pj.cfg.get("regulated")
        if any(not has_record(stage_status(pj, intent, st, None)[0]) for st in PHASE_STAGES["operations"]):
            # kept short: the session context cuts a line after CONTEXT_LINE_CHARS
            return ("optional: record deployment and operations (skill aidlc-lean-operations) or `%s stage skip "
                    "operations --reason ...`; the intent stays released. New work: `%s new <slug>`; %s" % (
                        TOOL, TOOL, "regulated mode blocks code until then" if regulated
                        else "small edits need no intent"))
        return ("nothing: this intent is released (RELEASE approved). Start new work, follow-ups and fixes included, "
                "with `%s new <slug>`; %s" % (TOOL, "regulated mode blocks code changes until then" if regulated
                                               else "small edits need no intent"))
    if pj.ideation_in_use(intent) and ideation_state(pj, intent)[0] != "approved":
        return ideation_next(pj, intent)
    req, design = pj.doc(intent, REQ_DOC), pj.doc(intent, DESIGN_DOC)
    req_s, _ = pj.approval_state(req)
    des_s, _ = pj.approval_state(design)
    need_design = des_s != "approved" and not pj.design_skipped(intent)
    small = pj.size_small(intent)
    if req_s == "missing":
        return "write requirements.md: `%s stage start requirements` (skill aidlc-lean-inception)" % TOOL
    if req_s != "approved":
        wait = waiting_for(pj, req)
        if wait:
            return wait
        if need_design and not small:
            start = "" if os.path.exists(design) else " (`%s stage start application-design`)" % TOOL
            return ("finish requirements.md and the application design%s, then `%s request INCEPTION` and wait for "
                    "the human to approve both" % (start, TOOL))
        return ("finish requirements.md, then `%s request REQUIREMENTS` (or `request INCEPTION` with the design) and "
                "wait for the human to approve" % TOOL)
    if need_design:
        wait = waiting_for(pj, design)
        if wait:
            return wait
        if des_s == "missing" and small:
            return ("write the application design (`%s stage start application-design`) and `request DESIGN`, or skip "
                    "it with `%s stage skip application-design --reason \"<why>\"` (Size: small)" % (TOOL, TOOL))
        if des_s == "missing":
            return ("write the application design: `%s stage start application-design` (skill aidlc-lean-inception), "
                    "then `%s request DESIGN` and wait for the human" % (TOOL, TOOL))
        return "finish application-design.md, then `%s request DESIGN` and wait for the human to approve" % TOOL
    plans = pj.plans(intent)
    if not plans:  # Inception is not finished while one of its stages has no record (Construction has not begun)
        early = open_stages(pj, intent, ("reverse-engineering", "user-stories", "units"))
        if early:
            return ("record the Inception stages that have no record yet: %s (`%s stage done <id> --note ...` once the "
                    "page is written, or `stage skip <id> --reason ...`)" % (", ".join(early), TOOL))
    passed = bool(lv and lv["data"].get("ok") and current)
    listed, info, _ = pj.units(intent)
    mine = pj.team() if pj.cfg.get("multi_team") else None
    elsewhere = []  # multi-team: units another team builds in its own clone
    unrecorded = []  # this clone's units whose code passed verify but has no `stage done code-generation` yet
    for u in stage_units(pj, intent, STAGE_BY_ID["code-generation"]):  # Construction: one unit at a time
        ev = pj.last_stage_event(intent, "code-generation", u)
        if ev and ev["event"] == "STAGE_COMPLETED":
            continue
        owner = (info.get(u) or {}).get("owner") or ""
        if mine and owner not in ("", "-", mine):
            elsewhere.append("%s (team %s)" % (u, owner))
            continue
        plan = plans.get(u)
        if not plan:
            designs = [st.name for st in UNIT_DESIGN_STAGES if u in listed and
                       stage_status(pj, intent, st, u)[0] in (" ", "-")]
            if designs:
                return ("unit %s: record its design stages first: %s (`%s stage start <id> --unit %s`, fill in the "
                        "page, `stage done <id> --unit %s --note ...`; or `stage skip <id> --unit %s --reason ...`), "
                        "then its code-generation plan (skill aidlc-lean-construction)"
                        % (u, ", ".join(designs), TOOL, u, u, u))
            then = (", then `request PLAN --unit %s` and wait for the human" % u if pj.plan_required()
                    else ", then build in small steps following it")
            return ("write the code-generation plan of unit %s: `%s stage start code-generation --unit %s` (skill "
                    "aidlc-lean-construction)%s" % (u, TOOL, u, then))
        if pj.plan_required() and pj.approval_state(plan)[0] != "approved":
            return waiting_for(pj, plan) or ("finish the code-generation plan of unit %s, then `%s request PLAN --unit "
                                             "%s` and wait for the human" % (u, TOOL, u))
        steps = plan_steps(plan)
        if steps and steps.open:  # mid-plan: a passing verify covers the steps done so far, not the unit
            return ("continue the code-generation plan of unit %s: step %d of %d%s; tick each step when it is done "
                    "(skill aidlc-lean-construction)" % (u, steps.first, steps.total,
                                                         " (%s)" % one_line(steps.text, 100) if steps.text else ""))
        if not passed:
            return ("build in small steps following the code-generation plan of unit %s (skill aidlc-lean-construction)"
                    "; run `%s verify` before calling anything done, then `stage done code-generation --unit %s --note "
                    "...`" % (u, TOOL, u))
        unrecorded.append(u)
    owner = owner_team(pj, intent) if mine else None
    releaser = owner if owner and team_key(owner) != team_key(mine) else None  # multi-team: another team releases
    if elsewhere:
        first = "".join("`%s stage done code-generation --unit %s --note ...`, then " % (TOOL, u) for u in unrecorded)
        return ("%swait for unit %s, which another team builds: its stage records come with the ledger when you pull "
                "(skill aidlc-lean-multi-team)%s" % (first, ", ".join(elsewhere),
                                                     "; release is done by team %s" % releaser if releaser else ""))
    if pj.plan_required():  # the release needs every plan approved, also after its unit is done
        for u, p in sorted(plans.items()):
            s = pj.approval_state(p)[0]
            if s != "approved":
                return waiting_for(pj, p) or ("the code-generation plan of unit %s is %s: `%s request PLAN --unit %s` "
                                              "and wait for the human" % (u, s, TOOL, u))
    checks = pj.cfg.get("checks")
    if not passed and (checks or pj.cfg.get("regulated")):
        if not checks:
            return "ask the human to set `checks` in %s/lean.json (regulated mode needs them), then `%s verify`" % (
                DOCS, TOOL)
        return "run `%s verify` and get it green on the current code (skill aidlc-lean-construction)" % TOOL
    if releaser:  # the review, `lean release` and the RELEASE approval happen in the owner team's clone
        todo = open_stages(pj, intent)
        return ("%srelease is done by team %s, the intent's owner team (`Owner team:` in %s), in its clone: commit and "
                "push this team's work (skill aidlc-lean-multi-team)" % (
                    ("record the stages that have no record yet (`%s stage done <id> --note ...` or `stage skip <id> "
                     "--reason ...`): %s; " % (TOOL, ", ".join(todo))) if todo else "", releaser, STATE_DOC))
    rel = pj.doc(intent, RELEASE_DOC)
    rel_s, _ = pj.approval_state(rel)
    written = last_release_write(pj, intent)
    for_this_code = written and written["data"].get("fingerprint") == pj.fingerprint()
    if rel_s in ("draft", "stale", "rejected") and for_this_code and not release_missing(pj, intent):
        wait = waiting_for(pj, rel)
        if wait:
            return wait
        if rel_s == "rejected":
            return ("RELEASE was rejected: do what the human asked (a code change needs `verify` and `release` again), "
                    "then `%s request RELEASE`" % TOOL)
        return "fill in Open items in operations/release.md, then `%s request RELEASE` and wait for the human" % TOOL
    again = ""
    if os.path.exists(rel):
        again = (" (`request RELEASE` needs the release.md it writes)" if not written else
                 " again (its Approvals table lacks newer approvals)" if for_this_code else
                 " again (the code changed since it wrote release.md)")
    if review_is_current(pj, intent, lv):  # the review is written: what is left is the release record
        then = "run `%s release`%s; the review (%s) is newer than the last verify and code change" % (
            TOOL, again, REVIEW_DOC)
    else:
        then = "review in a new chat or by a subagent that did not write the code, then `%s release`%s" % (TOOL, again)
    todo = open_stages(pj, intent)
    if todo:
        return ("record the stages that have no record yet (`%s stage done <id> --note ...` or `stage skip <id> "
                "--reason ...`): %s; then %s (skill aidlc-lean-release)" % (TOOL, ", ".join(todo), then))
    return "%s (skill aidlc-lean-release)" % then


def ideation_next(pj, intent):
    """Next while Ideation is in use and IDEATION is not approved: the next Ideation stage in order, then the
    IDEATION approval; Inception comes after it. Once IDEATION was requested, an optional stage that is not started
    is left out: its new page would void the request or the approval (re-request IDEATION instead)."""
    pend = ideation_pending(pj, intent)
    if pend:
        return ("wait for the human to type `approve IDEATION %s` (the request is out: show them that line again if "
                "needed, and do not change the Ideation pages)" % pend["data"]["sha256"][:8])
    asked = ideation_asked(pj, intent)
    for st in IDEATION_STAGES:
        if st.id == "approval-handoff":
            break
        mark, _ = stage_status(pj, intent, st, None)
        if mark == "-":
            return ("Ideation: finish %s (%s), then `%s stage done %s --note ...` (skill aidlc-lean-ideation)"
                    % (st.name, st.doc, TOOL, st.id))
        if mark == " " and asked and st.id not in IDEATION_REQUIRED:
            continue
        if mark == " ":
            optional = "" if st.id in IDEATION_REQUIRED else (
                "; it is optional: `stage skip %s --reason ...` when it adds nothing" % st.id)
            return ("Ideation: %s: `%s stage start %s` (skill aidlc-lean-ideation), fill in the page, then `stage "
                    "done %s --note ...`%s" % (st.name, TOOL, st.id, st.id, optional))
    s, _ = ideation_state(pj, intent)
    if s == "missing":
        return ("Ideation: write the initiative brief: `%s stage start approval-handoff` (skill aidlc-lean-ideation), "
                "then `stage done approval-handoff --note ...` and `request IDEATION`, and wait for the human" % TOOL)
    ev = stage_event(pj, intent, STAGE_BY_ID["approval-handoff"])
    handoff_done = bool(ev) and ev["event"] == "STAGE_COMPLETED"  # `request IDEATION` needs it (ideation_undone)
    redo = "record the initiative brief done again (`%s stage done approval-handoff --note ...`; skill aidlc-lean-" \
           "ideation)" % TOOL
    if s == "rejected":
        return ("IDEATION was rejected: revise the Ideation pages as the human asked, then %s" % (
            "`%s request IDEATION` and wait for the human" % TOOL if handoff_done else redo))
    if s == "stale":
        return ("an Ideation page changed since IDEATION was approved: %s" % (
            "`%s request IDEATION` again and wait for the human" % TOOL if handoff_done else "finish it, then " + redo))
    if not handoff_done:
        return ("Ideation: finish the initiative brief (%s), `%s stage done approval-handoff --note ...`, then "
                "`request IDEATION` and wait for the human (skill aidlc-lean-ideation)" % (HANDOFF_DOC, TOOL))
    return ("`%s request IDEATION` (it covers every Ideation page) and wait for the human to approve; Inception "
            "comes next" % TOOL)


def review_is_current(pj, intent, lv):
    """Is construction/build-and-test/review.md there and newer than the last verify (this clone's, and the
    intent's in any clone) and the last code write this clone's hook let through?"""
    try:
        mtime = os.path.getmtime(pj.doc(intent, REVIEW_DOC))
    except OSError:
        return False
    times = [e.get("ts") for e in pj.events() if e.get("event") == "VERIFY" and e.get("intent") == intent]
    times += [lv.get("ts")] if lv else []
    times.append(pj.local_dict("counters.json").get("last_code_write"))
    latest = max([t for t in (ts_epoch(x) for x in times if x) if t is not None] or [0])
    return mtime > latest


def intent_status(pj, intent):
    lines = []
    lv = pj.last_verify()
    current = False
    if lv:
        current = lv["data"].get("fingerprint") == pj.fingerprint()
        lines.append("Last verify: %s at %s%s" % ("PASS" if lv["data"].get("ok") else "FAIL", lv["ts"],
                                                  "" if current else " (code changed since)"))
    elif pj.cfg.get("checks"):
        lines.append("Last verify: never run")
    else:
        lines.append("Checks: none configured in %s/lean.json" % DOCS)
    lines.append("Next: " + next_step(pj, intent, lv, current))
    dirty = uncommitted_product_paths(pj) if git_head(pj)[0] else None
    if dirty:  # Stage progress (the committed page) also counts the commit; say what this clone's tree adds
        lines.append("Working tree: %d uncommitted product change%s (%s%s): verify, the commit gate and the RELEASE "
                     "approval check the working tree" % (
                         len(dirty), "" if len(dirty) == 1 else "s", ", ".join(dirty[:3]),
                         ", ..." if len(dirty) > 3 else ""))
        written = last_release_write(pj, intent)
        fp = (written or {}).get("data", {}).get("fingerprint")
        if written and not pj.released(intent) and fp == pj.head_fingerprint() and fp != pj.fingerprint():
            lines.append("Release: release.md is for older code than this clone's working tree (written %s): `request "
                         "RELEASE` and the RELEASE approval are refused here until the working tree holds that code "
                         "again, or run `verify` and `release` again" % written["ts"][:10])
    ignored = pj.units(intent)[2]
    if ignored:
        lines.append("unit-of-work.md: ignored unit names that cannot be folder names: " + ", ".join(ignored))
    return lines


def status_lines(pj, brief=False):
    """brief: for text the hooks inject (long lists shortened, the Next items before the Stage progress); the
    caller also applies cap_context."""
    if not pj.initialized:
        line = "AI-DLC Lean is installed but not initialized: run `%s init`." % TOOL
        if os.path.exists(os.path.join(pj.root, "aidlc", "lean.json")):
            line += " (aidlc/ is from AI-DLC Lean 0.1; since 0.2 everything is in %s/.)" % DOCS
        return [line]
    mode = []
    if pj.cfg.get("regulated"):
        mode.append("regulated")
    if pj.cfg.get("multi_team"):
        mode.append("multi-team (this clone: team %s)" % (pj.team() or "NOT SET"))
    out = ["AI-DLC Lean %s | mode: %s" % (VERSION, ", ".join(mode) or "standard")]
    if pj.cfg.get("multi_team") and pj.team():
        me, pending, involved = team_key(pj.team()), [], []
        for p in pj.cr_files():
            f = pj.cr_fields(p)
            if f["Owner team"] == pj.team() and pj.approval_state(p)[0] != "approved" and not pj.cr_closed(f["id"]):
                pending.append(f["id"])
            elif me in (team_key(f["Owner team"]), team_key(f["Requested by team"])):
                state = pj.cr_state(p)
                involved.append((state == "closed", "%s (%s)" % (f["id"], state)))
        involved = [s for _, s in sorted(involved, key=lambda x: x[0])]  # the open ones first
        for title, items in (("Change requests waiting for your team: ", pending),
                             ("Change requests involving your team: ", involved)):
            if items:
                shown = items[:5] if brief else items
                more = " and %d more" % (len(items) - len(shown)) if len(items) > len(shown) else ""
                out.append(title + ", ".join(shown) + more)
    intent = pj.active()
    if not intent:
        items = pj.list_intents()
        out.append("No active intent. %s" % (("Intents: " + ", ".join(items[-5:]) + ". Use `%s use <intent>`." % TOOL)
                                              if items else "Start one with `%s new <slug>`." % TOOL))
        return out
    out.append("Active intent: %s/%s (%s)" % (DOCS, intent, intent_title(pj, intent)))
    if pj.released(intent):
        out.append("  RELEASED: RELEASE is approved, so this intent is closed. New work needs a new intent: "
                   "`%s new <slug>`." % TOOL)
    out += ["  " + l for l in intent_status(pj, intent)]
    progress = ["  Stage progress:"] + ["    " + l for l in progress_lines(pj, intent)]
    notes = []
    for label, items in state_excerpt(pj, intent):  # this team's Next subsection first, then the generic Next
        notes += ["  From aidlc-state.md (%s):" % label] + ["    " + l.strip() for l in items]
    # the hooks cap what they inject (cap_context): the agent's Next items go first, so the cap cuts progress lines
    return out + (notes + progress if brief else progress + notes)


# ---------------------------------------------------------------- hooks
def hook_session_start(pj, payload):
    if not pj.initialized:
        print(status_lines(pj)[0])
        return 0
    _, head = run(["git", "rev-parse", "--short", "HEAD"], pj.root)
    _, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], pj.root)
    session = payload.get("session_id")
    with pj.state_lock():
        sessions = session_times(pj.local_dict("turn.json"))
        # a SessionStart for a chat this clone already knows, while a dispatched subagent prompt is pending, is that
        # subagent starting (a --resume fires none): the chat's turn state (n, ts, allow_protected) stays as it is
        pending = [d for d in live_dispatches(pj) if not d.get("session") or str(d["session"]) == str(session)] \
            if session and str(session) in sessions else []
        if not pending:
            ts = now()
            if session:
                sessions[str(session)] = ts
            pj.local_put("turn.json", {"n": 0, "session": session, "allow_protected": False, "ts": ts,
                                       "sessions": recent_sessions(sessions)})
    if pending:
        agents = sorted({str(d.get("name")) for d in pending if d.get("name")})[:5]
        pj.append("SUBAGENT_START", {"session": session, "branch": branch, "head": head, "pending": len(pending),
                                     "agents": agents}, intent=pj.active())
        print("\n".join(cap_context(["[AI-DLC Lean] session context for a subagent (from hooks, not the user):"]
                                    + status_lines(pj, brief=True))))
        return 0
    pj.append("SESSION_START", {"session": session, "branch": branch, "head": head}, intent=pj.active())
    print("\n".join(cap_context(["[AI-DLC Lean] session context (from hooks, not the user):"]
                                + status_lines(pj, brief=True))))
    return 0


def live_dispatches(pj):
    """The pending subagent dispatches in .aidlc-lean/subagents.json, oldest first, without expired ones. No lock:
    the caller holds pj.state_lock()."""
    items = pj.local_dict(DISPATCH_FILE).get("pending")
    out = []
    for d in items if isinstance(items, list) else []:
        if isinstance(d, dict) and isinstance(d.get("sha256"), str):
            age = hours_since(d.get("ts"))
            if age is not None and age <= DISPATCH_TTL_HOURS:
                out.append(d)
    return out[-DISPATCH_MAX:]


def dispatched_prompts(tool, tin):
    """[(prompt, agent name)] a delegation tool call hands to subagents (the `prompt` values in its input, also
    in lists of tasks), or [] for any other tool."""
    if not isinstance(tin, dict) or not (tool in DELEGATION_TOOLS or DELEGATION_TOOL_RE.search(tool or "")):
        return []
    out = []

    def walk(value, depth, name):
        if depth > 4:
            return
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("agent") or value.get("agent_name") or name)[:100]
            for k, v in value.items():
                if k == "prompt" and isinstance(v, str):
                    out.append((v, name))
                else:
                    walk(v, depth + 1, name)
        elif isinstance(value, list):
            for v in value[:DISPATCH_MAX]:
                walk(v, depth + 1, name)
    walk(tin, 0, "")
    return out


def record_dispatches(pj, session, tool, prompts):
    """Keep each dispatched prompt's sha256 (and its first characters) as pending until its subagent's prompt
    hook takes it (at most DISPATCH_MAX, for DISPATCH_TTL_HOURS)."""
    with pj.state_lock():
        items = live_dispatches(pj)
        ts = now()
        for p, name in prompts:
            items.append({"sha256": text_sha(p), "prefix": p[:DISPATCH_PREFIX_CHARS], "chars": len(p), "ts": ts,
                          "session": session, "tool": tool, "name": name})
        pj.local_put(DISPATCH_FILE, {"pending": items[-DISPATCH_MAX:]})


def take_dispatch(pj, prompt):
    """The pending dispatch this prompt answers, removed from the list, or None. A prompt matches by its sha256,
    or when it starts with the first DISPATCH_PREFIX_CHARS characters of a dispatched prompt that long."""
    if not os.path.exists(os.path.join(pj.local, DISPATCH_FILE)):
        return None
    digest = text_sha(prompt)
    with pj.state_lock():
        items = live_dispatches(pj)
        how, hit = "sha256", next((k for k, d in enumerate(items) if d["sha256"] == digest), None)
        if hit is None:
            how, hit = "prefix", next((k for k, d in enumerate(items) if isinstance(d.get("prefix"), str) and
                                       len(d["prefix"]) >= DISPATCH_PREFIX_CHARS and prompt.startswith(d["prefix"])),
                                      None)
        if hit is None:
            return None
        d = items.pop(hit)
        pj.local_put(DISPATCH_FILE, {"pending": items})
    return dict(d, match=how)


def session_times(turn):
    """Last human turn (or session start) per Kiro session_id, from .aidlc-lean/turn.json."""
    s = turn.get("sessions")
    return {k: v for k, v in s.items() if isinstance(v, str)} if isinstance(s, dict) else {}


def recent_sessions(sessions):
    return dict(sorted(sessions.items(), key=lambda kv: kv[1])[-MAX_TRACKED_SESSIONS:])


def hook_prompt(pj, payload):
    if not pj.initialized:
        return 0
    prompt = payload.get("prompt") or ""
    session = payload.get("session_id")
    intent = pj.active()
    dispatch = take_dispatch(pj, prompt)
    if dispatch:  # a subagent's task prompt, written by the agent: no approvals, no turn, the chat's state stays
        pj.append("SUBAGENT_PROMPT", {"session": session, "sha256": text_sha(prompt), "chars": len(prompt),
                                      "match": dispatch["match"], "agent": dispatch.get("name") or None,
                                      "tool": dispatch.get("tool")}, intent)
        return 0
    if HOST_PROMPT_RE.search(prompt):
        pj.append("HOST_TURN", {"session": session, "sha256": text_sha(prompt)}, intent)
        return 0
    allow = bool(ALLOW_PROTECTED_RE.search(prompt))
    with pj.state_lock():
        turn = pj.local_dict("turn.json")
        turn_no = (turn.get("n") or 0) + 1
        sessions = session_times(turn)
        # hours since this Kiro session's last human turn (per session_id), so a busy chat elsewhere in this
        # clone does not hide the break; the clone-wide time also counts and is all there is for an unseen session
        gaps = [g for g in (hours_since(turn.get("ts")), hours_since(sessions.get(str(session))) if session else None)
                if g is not None]
        gap_h = max(gaps) if gaps else None
        ts = now()
        if session:
            sessions[str(session)] = ts
        pj.local_put("turn.json", {"n": turn_no, "session": session, "allow_protected": allow, "ts": ts,
                                   "sessions": recent_sessions(sessions)})
    pj.append("HUMAN_TURN", {"session": session, "turn": turn_no, "sha256": text_sha(prompt),
                             "chars": len(prompt), "allow_protected": allow}, intent)
    msgs = []
    if gap_h is not None and gap_h >= (pj.cfg.get("resume_gap_hours") or 1e9):
        # a chat resumed after a break gets no SessionStart; refresh what teammates may have changed
        msgs.append("\n".join(cap_context(["Resumed after %.0f h. This is the same chat resumed, not a fresh context. "
                                           "Current status (pull first if teammates may have pushed):" % gap_h]
                                          + status_lines(pj, brief=True))))
    if allow:
        msgs.append("Protected files (%s) may be edited during this turn only; each edit is logged."
                    % ", ".join(pj.cfg.get("protected_paths") or ["none configured"]))
    recorded = False  # an approval, rejection or refused approval went into the ledger: the Stage log shows it
    for m in APPROVE_RE.finditer(prompt):
        msg, _ = record_approval(pj, intent, m.group(2), m.group(3), m.group(0).strip(), session)
        msgs.append(msg)
        recorded = True
    near = None if APPROVE_RE.search(prompt) else NEAR_APPROVAL_RE.search(prompt)
    if near:
        msg = ("That message mentions an approval but is not one: type the approval alone on its own line, "
               "exactly as shown by `request` (e.g. `approve REQUIREMENTS 1a2b3c4d`).")
        if near.group(2).upper() == "SPEC":
            msg += (" There is no SPEC any more: the approvals are IDEATION (with Ideation), REQUIREMENTS, DESIGN (or "
                    "both together as INCEPTION), PLAN, RELEASE and CR-<team>-<n>.")
        msgs.append(msg)
    for m in REJECT_RE.finditer(prompt):
        kind = norm_kind(m.group(2))
        target, err = rejection_target(pj, intent, kind, m.group(3))
        if not target:
            msgs.append("Rejection of %s NOT recorded: %s." % (kind, err))
            continue
        pj.append("REJECTED", dict(target_data(target), words=mask(m.group(0).strip())[:500], session=session), intent)
        recorded = True
        msgs.append("Recorded: %s rejected by the human%s. Revise it and request approval again." % (
            kind, ": the code-generation plan of unit %s" % target["unit"] if target.get("unit") else ""))
    counters = pj.local_dict("counters.json")
    limit = pj.cfg.get("state_reminder_after_writes") or 0
    if intent and limit and (counters.get("writes_since_state") or 0) >= limit:
        msgs.append("Reminder: %d code edits since aidlc-state.md was last updated; refresh its Session notes at the "
                    "next pause." % counters["writes_since_state"])
    if msgs:
        print("\n".join("[AI-DLC Lean] " + x for x in msgs))
        sys.stdout.flush()  # the confirmation goes out before the page is regenerated
    if recorded and intent:
        refresh_state_doc(pj, intent, "[AI-DLC Lean] ")
    return 0


def hours_since(ts):
    try:
        then = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600.0


def record_approval(pj, intent, kind, given_hash, words, session):
    """(message, recorded). An approval line the hook refuses is logged as APPROVAL_REFUSED, with the reason."""
    kind = norm_kind(kind)

    def refused(check, reason, target=None):
        data = {"kind": kind, "check": check, "reason": mask(reason)[:500], "words": mask(words)[:300],
                "session": session}
        if given_hash:
            data["given"] = given_hash.lower()
        if target:
            data.update({k: target[k] for k in ("path", "paths", "unit", "sha256") if target.get(k) is not None})
        pj.append("APPROVAL_REFUSED", data, intent)
        return "Approval of %s NOT recorded: %s" % (kind, reason), False

    target, err = approval_target(pj, intent, kind, given_hash=given_hash, approving=True)
    if not target:
        return refused("target", "%s." % err)
    digest = target["sha256"]
    if pj.cfg.get("regulated") and not given_hash:
        return refused("hash", "regulated mode needs the hash shown in the request, e.g. `approve %s %s`."
                       % (kind, digest[:8]), target)
    if given_hash and not digest.startswith(given_hash.lower()):
        return refused("hash", "the file changed since that request (you approved %s, current is %s). Ask for a "
                       "fresh request." % (given_hash[:8], digest[:8]), target)
    if kind == "RELEASE":  # release.md describes one state of the code: the one `lean release` checked
        written = last_release_write(pj, intent)
        if not written or written["data"].get("fingerprint") != pj.fingerprint():
            return refused("release", "operations/release.md was not written by `%s release` for the code as it is "
                           "now. Ask for `%s release` and a fresh request." % (TOOL, TOOL), target)
        problems, _ = release_problems(pj, intent)  # what `request RELEASE` checks: `lean release` would pass now
        if problems:
            return refused("release", "not ready to release: %s. Fix that, then ask for `%s release` and a fresh "
                           "request." % ("; ".join(problems), TOOL), target)
        missing = release_missing(pj, intent)
        if missing:
            return refused("release", "operations/release.md does not list %s: its Approvals table is out of date. "
                           "Ask for `%s release` and a fresh request." % (missing_text(missing), TOOL), target)
    if kind in ("REQUIREMENTS", "INCEPTION"):  # Ideation in use: its hand-off comes before the requirements
        idea = requirements_ideation_problem(pj, intent)
        if idea:
            return refused("ideation", "%s; the requirements are approved after the Ideation hand-off." % idea[0],
                           target)
    if kind == "IDEATION" and ideation_undone(pj, intent):  # the stages Ideation needs are done, not skipped
        return refused("target", "%s." % ideation_undone_text(pj, intent), target)
    ident = pj.identity()
    for key in approver_keys(target):
        allowed = (pj.cfg.get("approvers") or {}).get(key)
        if allowed and ident.get("git_email") not in allowed:
            return refused("approvers", "%s is not in approvers for %s." % (ident.get("git_email"), key), target)
    data = dict(target_data(target), session=session, words=mask(words)[:500])
    if kind.startswith("CR-"):
        f = pj.cr_fields(os.path.join(pj.root, target["path"]))
        if pj.cfg.get("multi_team") and f["Owner team"] and ident.get("team") != f["Owner team"]:
            return refused("team", "it needs someone from team %s (this clone is team %s)."
                           % (f["Owner team"], ident.get("team") or "not set"), target)
        data["owner_team"] = f["Owner team"]
    if kind in ("REQUIREMENTS", "INCEPTION"):
        data["protected_baseline"] = pj.protected_files()
    via = re.search(r"\(via\s+([^)]{1,200})\)", words)
    if via:
        data["claimed_channel"] = via.group(1)
    pj.append("APPROVED", data, intent)
    if kind == "RELEASE" and intent:  # the approval completes the Release stage (`lean release` started it)
        pj.append("STAGE_COMPLETED", {"stage": "release", "unit": None, "note": "RELEASE approved (sha %s)" % digest[:8],
                                      "outputs": {target["path"]: digest}}, intent)
    what = ""
    if kind == "INCEPTION":
        what = ": " + " and ".join(pj.short(intent, p) for p in target["paths"])
    elif kind == "IDEATION":
        what = ": the Ideation pages (%s)" % ", ".join(os.path.basename(p) for p in target["paths"])
    elif kind == "PLAN":
        what = ": the code-generation plan of unit %s" % target["unit"]
    return ("Recorded: %s approved (sha %s) by %s%s." % (kind, digest[:8], ident.get("git_email") or ident["os_user"],
                                                         what)), True


def block(pj, gate, msg, intent, detail):
    try:
        pj.append("BLOCKED", dict(detail, gate=gate, reason=msg), intent)
    except Exception:  # noqa: BLE001
        pass
    sys.stderr.write("[AI-DLC Lean] blocked (%s): %s\n" % (gate, msg))
    return 2


def hook_pre_tool(pj, payload):
    if not pj.initialized:
        return 0
    tool = payload.get("tool_name") or ""
    tin = payload.get("tool_input") or {}
    intent = pj.active()
    prompts = dispatched_prompts(tool, tin)
    if prompts:  # a subagent is about to start: its prompt hook must not take the agent's text as the human's
        record_dispatches(pj, payload.get("session_id"), tool, prompts)
    if tool in SHELL_TOOLS or ("command" in tin and not tin.get("path")):
        return guard_shell(pj, intent, str(tin.get("command") or ""))
    path = tin.get("path") or tin.get("file_path") or tin.get("filePath")
    if not path or READ_TOOL_RE.search(tool):
        return 0
    return guard_write(pj, intent, tool, pj.relpath(path))


def guard_write(pj, intent, tool, r):
    cfg = pj.cfg
    d = {"tool": tool, "path": r}
    if r.startswith(DOCS + "/audit/") or r.startswith(".aidlc-lean/") or r == DOCS + "/lean.json" \
            or pj.is_owners_file(r) or r.startswith(KIT_PATHS):
        return block(pj, "records", "%s is maintained by people and the AI-DLC Lean tool, not by the agent "
                     "(audit ledger, local state, config, contract owners, hooks and kit files)." % r, intent, d)
    if pj.is_tool_record(r):
        return block(pj, "records", "%s is written by the AI-DLC Lean tool (`%s verify` writes the build-and-test "
                     "summary and evidence, `%s audit pack` writes audit.md), not by the agent." % (r, TOOL, TOOL),
                     intent, d)
    if matches(r, cfg.get("protected_paths")):
        turn = pj.local_dict("turn.json")
        if not turn.get("allow_protected"):
            return block(pj, "protected", "%s is a protected acceptance file. Do not change it; if the human wants "
                         "it changed they will say 'allow test change'." % r, intent, d)
        pj.append("PROTECTED_CHANGE", d, intent)
        return 0
    # Contracts count as code (fingerprint, commit gate, release), in every mode: after the ownership check they go
    # through the code-write gates below, like any code. In multi-team mode another team's contract needs that
    # team's approved change request first; the team's own contracts and CR-unlocked ones skip only that check.
    contract = pj.is_contract(r)
    if contract and cfg.get("multi_team"):
        owner, me = pj.owner_of(r), pj.team()
        if owner and owner != me and not pj.approved_cr_for(r, owner):
            return block(pj, "contract", "%s belongs to team %s. Open a change request (`%s cr new <slug> --owner %s "
                         "--paths %s`) and wait for that team to approve it." % (r, owner, TOOL, owner, r), intent, d)
    if not contract and (r.startswith(DOCS + "/") or r.startswith(".kiro/") or matches(r, cfg.get("free_paths"))):
        if intent and r == "%s/%s/%s" % (DOCS, intent, STATE_DOC):
            pj.reset_write_count()
        return 0
    # code path
    if intent and not cfg.get("regulated") and pj.released(intent):
        intent = None  # standard mode: a released intent is closed, so code goes as with no active intent
    if not intent:
        if cfg.get("regulated"):
            return block(pj, "intent", "regulated mode: start or select an intent before changing code "
                         "(`%s new <slug>`)." % TOOL, intent, d)
        return 0
    problems = gate_problems(pj, intent, r)  # regulated mode: a released intent blocks (gate released)
    if problems:
        gate, msg, _ = problems[0]
        return block(pj, gate, msg, intent, d)
    pj.count_write()
    return 0


def guard_shell(pj, intent, cmd):
    d = {"command": mask(cmd)[:300]}
    # OWNERS as commands name it: under contracts_dir as configured, and under its resolved target
    owners_files = sorted({pj.cfg["contracts_dir"] + "/OWNERS", pj.contracts_real + "/OWNERS"})
    scan = without_note_values(cmd)  # for the records and mutation checks below; the rest look at cmd
    if re.search(r"aidlc_lean\.py\S*\s+hook\b", scan) or touches_records(scan):
        return block(pj, "records", "commands may not touch %s/audit/, .aidlc-lean/, %s/lean.json or call the hook "
                     "entry point (staging and committing them with plain `git add`/`git commit` is fine)."
                     % (DOCS, DOCS), intent, d)
    for prefix in list(KIT_PATHS) + owners_files:
        if mutates(scan, prefix):
            return block(pj, "records", "commands may not change %s (kit files and contract owners)."
                         % (prefix + "*" if prefix.endswith("-") else prefix), intent, d)
    if mutates_re(scan, TOOL_RECORDS_SHELL):
        return block(pj, "records", "commands may not change the files the tool writes (build-and-test-summary.md, "
                     "build-and-test/evidence/, audit.md); `%s verify` and `%s audit pack` write them." % (TOOL, TOOL),
                     intent, d)
    if not pj.local_dict("turn.json").get("allow_protected"):
        for prefix in [p.split("*")[0] for p in pj.cfg.get("protected_paths") or [] if p.split("*")[0]]:
            if mutates(scan, prefix):
                return block(pj, "protected", "this command would change protected files under %s." % prefix,
                             intent, d)
    for pat in pj.cfg.get("deny_commands") or []:
        try:
            if re.search(pat, cmd):
                return block(pj, "danger", "this command is on the deny list (%s). Ask the human to run it "
                             "themselves if it is really needed." % pat, intent, d)
        except re.error:
            continue
    if re.search(r"\bgit\b[^|;&]*\bcommit\b", cmd) and "--dry-run" not in cmd:
        if not pj.cfg.get("checks"):
            if pj.cfg.get("regulated"):
                return block(pj, "verify", "regulated mode needs checks in %s/lean.json before commits." % DOCS,
                             intent, d)
            return 0
        if only_record_changes(pj):
            return 0
        lv = pj.last_verify()
        if not lv or not lv["data"].get("ok") or lv["data"].get("fingerprint") != pj.fingerprint():
            return block(pj, "verify", "run `%s verify` and get it green on the current code before committing."
                         % TOOL, intent, d)
    return 0


RECORDS_RE = re.compile(r"aidlc-docs/audit(?![\w.-])|\.aidlc-lean\b|aidlc-docs/lean\.json")
SAFE_GIT_RE = re.compile(r"^\s*git\s+(add|commit|status|diff|log|show|ls-files|blame)\b")
# the files only the tool writes, as they appear in a command (any intent folder)
TOOL_RECORDS_SHELL = (r"aidlc-docs/(?:[^/\s'\"|;&<>]+/)?(?:audit\.md|construction/build-and-test"
                      r"(?:/build-and-test-summary\.md|/evidence\b|/?(?=[\s'\"]|$)))(?![\w.-])")


def touches_records(cmd):
    """True unless every command segment that names a record path is a plain git stage/inspect command."""
    for seg in re.split(r"&&|\|\||[;|\n]", cmd):
        if not RECORDS_RE.search(seg):
            continue
        if SAFE_GIT_RE.search(seg) and ">" not in seg and not re.search(r"\s(-f|--force)\b", seg):
            continue
        return True
    return False


NOTE_OPTIONS = ("--note", "--reason", "--title")
TOOL_CALL = (("python3", "python"), (".kiro/aidlc-lean/aidlc_lean.py", "./.kiro/aidlc-lean/aidlc_lean.py"),
             ("stage", "cr"))  # the first three words of a command whose note values are text, not commands


def shell_commands(cmd):
    """The simple commands of a shell command line, read with its quoting: per command, its tokens as
    (start, end, is_word); a redirection operator is a token that is not a word. None when the line holds what
    this reader does not follow exactly: $ or ` outside single quotes, a comment, a here-document, an unclosed
    quote."""
    cmds, toks, start, i, n = [], [], None, 0, len(cmd)
    while i < n:
        c = cmd[i]
        if c in "$`" or (c == "#" and start is None):
            return None
        if c in " \t\n;&|()<>":
            if start is not None:
                toks.append((start, i, True))
                start = None
            if c in "<>" or cmd.startswith("&>", i):  # a redirection: <, >, >>, >&, >|, <>, <&, &>, &>>
                if cmd.startswith("<<", i):
                    return None
                j = i + (2 if c == "&" else 1)
                while j < n and cmd[j] in "<>&|":
                    j += 1
                toks.append((i, j, False))
                i = j
                continue
            if c not in " \t":  # ; & | ( ) and newline end a simple command
                if toks:
                    cmds.append(toks)
                toks = []
            i += 1
            continue
        if start is None:
            start = i
        if c == "\\":
            i += 2
        elif c == "'":
            j = cmd.find("'", i + 1)
            if j < 0:
                return None
            i = j + 1
        elif c == '"':
            j = i + 1
            while j < n and cmd[j] != '"':
                if cmd[j] in "$`":
                    return None
                j += 2 if cmd[j] == "\\" else 1
            if j >= n:
                return None
            i = j + 1
        else:
            i += 1
    if start is not None:
        toks.append((start, n, True))
    if toks:
        cmds.append(toks)
    return cmds


def without_note_values(cmd):
    """cmd without the values of --note, --reason and --title where a simple command runs this tool's `stage` or
    `cr` (`python3 .kiro/aidlc-lean/aidlc_lean.py stage done ... --note "..."`): that text goes into the ledger, so
    a record path named in it is no command. Values count when quoted (--note "...", --note '...') or in the
    --note=... form. Everything else stays, the whole line too when shell_commands cannot read it."""
    cmds = shell_commands(cmd)
    cut = []
    for toks in cmds or []:
        if len(toks) < 3 or not all(toks[k][2] and cmd[toks[k][0]:toks[k][1]] in TOOL_CALL[k] for k in range(3)):
            continue
        k = 3
        while k < len(toks):
            s, e, is_word = toks[k]
            word = cmd[s:e] if is_word else ""
            if word in NOTE_OPTIONS and k + 1 < len(toks) and toks[k + 1][2] and cmd[toks[k + 1][0]] in "'\"":
                cut.append(toks[k + 1][:2])  # --note "<text>" or '<text>'
                k += 2
                continue
            opt = word.split("=", 1)[0]
            if opt in NOTE_OPTIONS and "=" in word:
                cut.append((s + len(opt) + 1, e))  # --note="<text>"
            k += 1
    for s, e in reversed(cut):
        cmd = cmd[:s] + "''" + cmd[e:]
    return cmd


def mutates(cmd, prefix):
    return mutates_re(cmd, re.escape(prefix))


def mutates_re(cmd, p):
    """Does the command look like it writes, moves or deletes something matching the regex p?"""
    return bool(re.search(
        r"(>>?\s*['\"]?(\./)?%s|\bsed\s+-i[^|;&]*%s|\b(mv|cp|rm|tee|truncate|chmod|ln|touch|install)\b[^|;&]*%s"
        r"|\bgit\s+(checkout|restore|rm|mv|apply)\b[^|;&]*%s|\bpython3?\b[^|;&]*%s[^|;&]*open\()" % (p, p, p, p, p), cmd))


def changed_paths(pj, every_untracked=False):
    """Paths in `git status --porcelain -z`, relative to the project root, or None if git fails.
    Output is parsed unstripped (the first entry may start with a space, e.g. ' M path'), and a rename or
    copy lists both its new and its old path. every_untracked: each untracked file, not just its folder."""
    cmd = ["git", "status", "--porcelain", "-z"] + (["--untracked-files=all"] if every_untracked else [])
    try:
        p = subprocess.run(cmd, cwd=pj.root, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    fields, paths, i = p.stdout.split(b"\0"), [], 0
    while i < len(fields):
        f = fields[i]
        i += 1
        if len(f) < 4:
            continue
        paths.append(os.fsdecode(f[3:]))
        if b"R" in f[:2] or b"C" in f[:2]:  # the next field is the source path
            if i < len(fields) and fields[i]:
                paths.append(os.fsdecode(fields[i]))
            i += 1
    # porcelain paths are relative to the git top level; the project may be a subfolder of it (monorepo).
    # Paths outside the project never count as records.
    _, prefix = run(["git", "rev-parse", "--show-prefix"], pj.root)
    if prefix:
        paths = [x[len(prefix):] if x.startswith(prefix) else "../" + x for x in paths]
    return paths


def only_record_changes(pj):
    paths = changed_paths(pj)
    return bool(paths) and all(pj.is_record_path(p) for p in paths)


def uncommitted_product_paths(pj):
    """The product files (the ones the code fingerprint covers) with uncommitted changes, sorted; None if git
    cannot tell."""
    paths = changed_paths(pj, every_untracked=True)
    if paths is None:
        return None
    return sorted({p for p in paths if not p.startswith("../") and not p.startswith(".aidlc-lean/")
                   and not pj.is_record_path(p)})


def tree_text(dirty):
    """The working-tree line of the build-and-test summary and the verify evidence."""
    if dirty is None:
        return "unknown (git status failed)"
    if not dirty:
        return "clean"
    return "%d uncommitted product change%s (the code fingerprint, not the commit, names the verified code)" % (
        len(dirty), "" if len(dirty) == 1 else "s")


def cmd_hook(pj_root, event):
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    root = find_root(payload.get("cwd") or pj_root)
    pj = None
    try:
        pj = Project(root)
        fn = {"SessionStart": hook_session_start, "UserPromptSubmit": hook_prompt,
              "PreToolUse": hook_pre_tool}.get(event)
        return fn(pj, payload) if fn else 0
    except SystemExit as e:
        sys.stderr.write("[AI-DLC Lean] %s\n" % e)
        return 2 if event == "PreToolUse" else 0
    except Exception as e:  # noqa: BLE001 - a broken hook must not silently open the gates in regulated mode
        regulated = bool(pj and pj.cfg.get("regulated"))
        sys.stderr.write("[AI-DLC Lean] hook error in %s: %s: %s\n" % (event, type(e).__name__, e))
        return 2 if (event == "PreToolUse" and regulated) else 0


# ---------------------------------------------------------------- commands
def need_intent(pj):
    intent = pj.active()
    if not intent:
        print("No active intent. Start one with `%s new <slug>` or pick one with `%s use <intent>`." % (TOOL, TOOL))
    return intent


def cmd_init(pj, args):
    cfg_path = os.path.join(pj.docs, "lean.json")
    configured = os.path.exists(cfg_path)  # e.g. a teammate's clone: lean.json comes with the repository
    if not configured:
        try:
            cfg = json.loads(template("lean.json"))
        except ValueError:
            print("The template .kiro/aidlc-lean/templates/lean.json is missing or broken: re-run install.sh.")
            return 1
        cfg["regulated"] = "--regulated" in args
        cfg["multi_team"] = "--multi-team" in args
        write_text(cfg_path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        print("Created %s/lean.json" % DOCS)
    pj = Project(pj.root)
    os.makedirs(pj.ledger_dir(), exist_ok=True)
    if pj.cfg.get("multi_team"):
        cdir = pj.cfg["contracts_dir"].rstrip("/")
        owners = os.path.join(pj.root, cdir, "OWNERS")
        if not os.path.exists(owners):
            write_text(owners, "# <path glob> <team>  (last match wins)\n# %s/payments/** payments\n" % cdir)
        os.makedirs(os.path.join(pj.root, cdir, "changes"), exist_ok=True)
    team = before = None
    if "--team" in args and args.index("--team") + 1 < len(args):
        team = re.sub(r"[^A-Za-z0-9_]", "_", args[args.index("--team") + 1])
        before = pj.local_dict("local.json").get("team")
        pj.local_put("local.json", {"team": team})
    gi = os.path.join(pj.root, ".gitignore")
    if ".aidlc-lean/" not in read_text(gi):
        with open(gi, "a", encoding="utf-8") as f:
            f.write("\n# AI-DLC Lean local state (per clone)\n.aidlc-lean/\n")
    data = {"version": VERSION, "regulated": pj.cfg.get("regulated"), "multi_team": pj.cfg.get("multi_team")}
    if team:
        data["team"] = team
    pj.append("INIT", data)
    unset = [k for k in ("checks", "protected_paths") if not pj.cfg.get(k)]
    advice = (" Edit %s/lean.json: set %s." % (DOCS, " and ".join("`%s`" % k for k in unset))) if unset else ""
    if configured and team:  # a configured clone getting its team: say only what changed
        print("This clone (%s) is now team %s%s.%s" % (pj.clone_id(), team, " (was %s)" % before
                                                       if before and before != team else "", advice))
        return 0
    print("AI-DLC Lean ready (clone %s).%s" % (pj.clone_id(), advice))
    return 0


def cmd_new(pj, args):
    ideation = "--ideation" in args  # a flag without a value: before or after the slug
    args = [a for a in args if a != "--ideation"]
    opts, err = parse_opts(args[1:], ("--title",)) if args and not args[0].startswith("--") else (None, "")
    slug = re.sub(r"[^a-z0-9-]+", "-", args[0].lower()).strip("-") if opts is not None else ""
    if not slug:
        print("usage: new <slug> [--title T] [--ideation]%s" % ("  (%s)" % err if err else ""))
        return 1
    title = opts.get("--title") or slug.replace("-", " ")
    intent = datetime.now().strftime("%y%m%d") + "-" + slug
    if os.path.exists(pj.doc(intent)):
        print("Intent exists: %s/%s" % (DOCS, intent))
        return 1
    first = STAGE_BY_ID["intent-capture" if ideation else "requirements"]  # the stage the intent starts with
    files = (STATE_DOC, DECISIONS_DOC, first.doc)
    owner = pj.team() if pj.cfg.get("multi_team") else None  # multi-team: the creating clone's team releases it
    for name in files:
        st = first if name == first.doc else None
        text = template(st.template if st else os.path.basename(name), **dict(doc_vars(pj, intent, st), TITLE=title))
        if name == STATE_DOC and owner:
            text = with_owner_line(text, owner)
        if name == STATE_DOC and ideation:
            text = ideation_session_notes(text)
        write_text(pj.doc(intent, name), text)
    pj.local_put("active.json", {"intent": intent})
    pj.append("INTENT_CREATED", {"title": title, "ideation": ideation}, intent)
    if not ideation:  # developers' flow as before: the whole Ideation phase is recorded as skipped
        pj.append("PHASE_SKIPPED", {"phase": "ideation", "stages": list(IDEATION_IDS), "reason": NOT_REQUESTED},
                  intent)
    pj.append("STAGE_STARTED", {"stage": first.id, "unit": None, "path": "%s/%s/%s" % (DOCS, intent, first.doc),
                                "created": True}, intent)
    refresh_state_doc(pj, intent)
    if ideation:
        print("Created %s/%s (%s). It is now the active intent. Next: Ideation (skill aidlc-lean-ideation): fill in "
              "%s, then `%s stage done intent-capture --note ...`." % (DOCS, intent, ", ".join(files), first.doc, TOOL))
    else:
        print("Created %s/%s (%s). It is now the active intent. Next: clarify (one batch of questions), then write "
              "%s." % (DOCS, intent, ", ".join(files), REQ_DOC))
        print("Ideation is recorded as skipped (not requested); `%s stage start intent-capture` re-opens it until the "
              "requirements are approved." % TOOL)
    if pj.cfg.get("multi_team"):
        print("Multi-team: list the units, their owner teams and paths in %s (`%s stage start units`)."
              % (UNITS_DOC, TOOL))
        if owner:
            print("Owner team: %s (in the header of %s): this team reviews and releases the intent."
                  % (owner, STATE_DOC))
    return 0


IDEATION_NEXT = ("1. Fill in ideation/intent-capture/intent-statement.md with the product owner (skill aidlc-lean-ideation), "
                 "then `lean stage done intent-capture --note ...`.\n"
                 "2. Scope Definition and Approval Handoff are required, the other Ideation stages optional; then "
                 "`lean request IDEATION` and wait for the approval before Inception.\n")


def ideation_session_notes(text):
    """aidlc-state.md for a `new --ideation` intent: the template's Status and Next describe the Inception start."""
    text = text.replace("Status: Inception: starting", "Status: Ideation: starting", 1)
    return re.sub(r"(### Next\n)(?:\d+\..*\n)+", lambda m: m.group(1) + IDEATION_NEXT, text, count=1)


def with_owner_line(text, team):
    """aidlc-state.md with `Owner team: <team>` in its header: after the `Intent:` line, else after the title."""
    lines = text.split("\n")
    head_end = next((k for k, l in enumerate(lines) if l.startswith("## ") or BEGIN_MARK in l), len(lines))
    at = next((k + 1 for k, l in enumerate(lines[:head_end]) if l.startswith("Intent:")), None)
    if at is None:
        at = 1 if lines and lines[0].startswith("# ") else 0
    return "\n".join(lines[:at] + ["Owner team: %s" % team] + lines[at:])


def resolve_intent(pj, name):
    """An intent folder by full name or by slug (the part after the date), or None if unknown or ambiguous."""
    items = pj.list_intents()
    if not name:
        return None
    if name in items:
        return name
    hit = [i for i in items if i.endswith("-" + name)]
    return hit[0] if len(hit) == 1 else None


def cmd_use(pj, args):
    hit = resolve_intent(pj, args[0] if args else None)
    if not hit:
        print("Pick one of: " + ", ".join(pj.list_intents()))
        return 1
    before = pj.active()
    pj.local_put("active.json", {"intent": hit})
    pj.append("INTENT_SWITCHED", {"from": before, "to": hit}, hit)
    print("Active intent: " + hit)
    return 0


def cmd_status(pj, args):
    print("\n".join(status_lines(pj)))
    if pj.initialized and pj.active():  # bring the page up to date, e.g. after a pull or a merge of it
        refresh_state_doc(pj, pj.active())
    return 0


STAGE_USAGE = ('usage: stage start <id> [--unit U] | stage done <id> [--unit U] --note "<what was done>" | '
               'stage skip <id> [--unit U] --reason "<why>" | stage skip ideation|operations --reason "<why>"\n'
               'stages: ' + ", ".join(s.id for s in STAGES) + "\nphases (stage skip only): " + ", ".join(PHASES))


def pick_unit(pj, intent, st, given):
    """(unit, None) or (None, error). Per-unit stages default to the only unit."""
    if not st.per_unit:
        return None, ("%s is not a per-unit stage: leave out --unit." % st.id) if given else None
    names, info, ignored = pj.units(intent)
    source = "unit-of-work.md" if info else "no unit-of-work.md, so the only unit is app"
    note = (" (ignored names in unit-of-work.md: %s)" % ", ".join(ignored)) if ignored else ""
    if given:
        if given in names or (st.id == "code-generation" and given in pj.plans(intent)):
            return given, None
        return None, "unknown unit %s. Units: %s (%s)%s." % (given, ", ".join(names), source, note)
    if len(names) == 1:
        return names[0], None
    return None, "%s is per unit: add --unit with one of %s.%s" % (st.id, ", ".join(names), note)


def cmd_stage(pj, args):
    if len(args) < 2 or args[0] not in ("start", "done", "skip"):
        print(STAGE_USAGE)
        return 1
    action, st = args[0], STAGE_BY_ID.get(args[1])
    if args[1] in PHASES:
        if action != "skip":
            print("%s is a phase: `stage skip %s --reason \"<why>\"` skips its stages that have no record yet; start "
                  "and finish its stages one by one (%s)." % (PHASES[args[1]], args[1],
                                                               ", ".join(s.id for s in PHASE_STAGES[args[1]])))
            return 1
        return phase_skip(pj, args[1], args[2:])
    if not st:
        print("unknown stage %s.\n%s" % (args[1], STAGE_USAGE))
        return 1
    allowed = ("--unit", "--note") if action == "done" else ("--unit", "--reason") if action == "skip" else ("--unit",)
    opts, err = parse_opts(args[2:], allowed)
    if err:
        print("%s\n%s" % (err, STAGE_USAGE))
        return 1
    intent = need_intent(pj)
    if not intent:
        return 1
    if pj.released(intent) and st.id not in AFTER_RELEASE_IDS:  # Operations (and ci-pipeline) may come after it
        print("%s is released (RELEASE approved); its record is closed. Start new work with `%s new <slug>`. (After "
              "RELEASE only the Operations stages and ci-pipeline take stage commands.)" % (intent, TOOL))
        return 1
    if action == "skip" and not st.skippable:
        print("%s cannot be skipped (requirements, code-generation, build-and-test and release never are)." % st.name)
        return 1
    reopens = False  # a start or done record that puts Ideation in use again
    if st.phase == "ideation":
        used = pj.ideation_in_use(intent)
        reopens = action in ("start", "done") and not used
        if action == "skip" and st.skippable == "unused" and used:
            print("%s cannot be skipped while Ideation is in use (intent-capture, scope-definition and "
                  "approval-handoff are required then)." % st.name)
            return 1
        req_ok = pj.requirements_approved_event(intent)
        if action in ("start", "done") and not used and req_ok:
            print("Ideation is not in use for %s (%s) and its requirements are approved (%s, %s), so Ideation cannot "
                  "be re-opened. Start a new intent with `%s new <slug> --ideation`." % (
                      intent, ideation_skip_text(pj, intent), req_ok["data"]["kind"], req_ok["ts"][:10], TOOL))
            return 1
    if st.template is None:
        print("%s is recorded by `%s %s`, not by `stage`." % (st.name, TOOL, "verify" if st.id == "build-and-test"
                                                                                     else "release"))
        return 1
    unit, err = pick_unit(pj, intent, st, opts.get("--unit"))
    if err:
        print(err)
        return 1
    path = pj.doc(intent, st.doc.format(unit=unit))
    r = rel(pj.root, path)
    label = st.name + (" (%s)" % unit if unit else "")
    unit_arg = " --unit %s" % unit if unit else ""
    if action == "start":
        created = not os.path.exists(path) and create_new(path, template(st.template, **doc_vars(pj, intent, st, unit)))
        pj.append("STAGE_STARTED", {"stage": st.id, "unit": unit, "path": r, "created": created}, intent)
        refresh_state_doc(pj, intent)
        print("%s %s. %s is in progress. When it is done: `%s stage done %s%s --note \"<what was done: inputs used, "
              "what it produced, key decisions>\"`." % ("Created" if created else "Kept the existing", r, label, TOOL,
                                                        st.id, unit_arg))
        if reopens:
            reopen_note(pj, intent)
        if st.id == "code-generation" and pj.plan_required():
            print("Regulated mode: get the plan approved (`%s request PLAN%s`) before writing its code." % (TOOL, unit_arg))
        return 0
    if action == "done":
        note = (opts.get("--note") or "").strip()
        if not note:
            print('`stage done` needs --note "<what was done: inputs used, what it produced, key decisions>".')
            return 1
        text = read_text(path, None)
        if text is None:
            print("%s does not exist. `%s stage start %s%s` creates it from the template." % (r, TOOL, st.id, unit_arg))
            return 1
        if not text.strip() or is_untouched(text, st.template, doc_vars(pj, intent, st, unit)):
            print("%s is still the template. Fill it in (one page), then run `stage done` again." % r)
            return 1
        steps = plan_steps(path) if st.id == "code-generation" else None
        if steps and steps.open:
            first = ", " + one_line(steps.text, 100) if steps.text else ""
            print("%s has %d unticked step%s of %d (the first: step %d%s). Finish and tick every step, then run "
                  "`stage done` again; a step that is no longer needed is a change of the plan (in regulated mode it "
                  "needs a new PLAN approval)." % (r, steps.open, "" if steps.open == 1 else "s", steps.total,
                                                    steps.first, first))
            return 1
        digest = sha256_file(path)
        data = {"stage": st.id, "unit": unit, "note": mask(note)[:NOTE_MAX], "outputs": {r: digest}}
        if st.id == "code-generation":
            data["fingerprint"] = pj.fingerprint()
            data["plan_sha256"] = plan_sha256(path)  # what "(edited since)" compares: ticking a box is no edit
        pj.append("STAGE_COMPLETED", data, intent)
        refresh_state_doc(pj, intent)
        print("Recorded: %s done (%s, sha %s)." % (label, r, digest[:8]))
        if reopens:
            reopen_note(pj, intent)
        if st.id == "units":
            names, info, ignored = pj.units(intent)
            print("Units: %s%s" % (", ".join(names) if info else "app (no unit rows found)",
                                   ("; ignored (not usable as folder names): " + ", ".join(ignored)) if ignored else ""))
        if st.id in ("requirements", "application-design") and pj.approval_state(path)[0] != "approved":
            print("It needs the human's approval: `%s request %s` (or `request INCEPTION` for requirements and design "
                  "together)." % (TOOL, "REQUIREMENTS" if st.id == "requirements" else "DESIGN"))
        if st.id == "approval-handoff" and ideation_state(pj, intent)[0] != "approved":
            print("It needs the human's approval: `%s request IDEATION` (it covers every Ideation page)." % TOOL)
        return 0
    reason = (opts.get("--reason") or "").strip()
    if st.skippable == "small" and not pj.size_small(intent):
        print("Application Design can be skipped only when %s says `Size: small`." % REQ_DOC)
        return 1
    if not reason:
        print('`stage skip` needs --reason "<why>".')
        return 1
    pj.append("STAGE_SKIPPED", {"stage": st.id, "unit": unit, "reason": mask(reason)[:NOTE_MAX]}, intent)
    refresh_state_doc(pj, intent)
    print("Recorded: %s skipped (%s)." % (label, one_line(reason, 200)))
    return 0


def reopen_note(pj, intent):
    """What `stage start|done` says when it puts Ideation in use again while a stage Ideation needs has its own skip
    from before: that skip no longer counts (stage_event)."""
    names = [STAGE_BY_ID[s].name for s in IDEATION_REQUIRED
             if (pj.last_stage_event(intent, s) or {}).get("event") == "STAGE_SKIPPED"]
    if names:
        print("Ideation is in use again: %s %s skipped before and %s required now (those skips no longer count). "
              "Write %s and record %s with `%s stage done <id> --note ...` before `request IDEATION`." % (
                  ", ".join(names), "was" if len(names) == 1 else "were", "is" if len(names) == 1 else "are",
                  "its page" if len(names) == 1 else "their pages", "it" if len(names) == 1 else "them", TOOL))


def phase_skip(pj, phase, args):
    """`stage skip ideation|operations --reason "<why>"`: one PHASE_SKIPPED record for every stage of the phase that
    has no record yet (done or skipped). Operations does not include ci-pipeline. Ideation in use can be dropped
    this way until IDEATION is requested: once the request is out (or answered), the human decides it."""
    opts, err = parse_opts(args, ("--reason",))
    if err:
        print("%s\n%s" % (err, STAGE_USAGE))
        return 1
    intent = need_intent(pj)
    if not intent:
        return 1
    name = PHASES[phase]
    if phase == "ideation" and pj.released(intent):
        print("%s is released (RELEASE approved); its record is closed. Start new work with `%s new <slug>`. (After "
              "RELEASE only the Operations stages and ci-pipeline take stage commands.)" % (intent, TOOL))
        return 1
    reason = (opts.get("--reason") or "").strip()
    if not reason:
        print('`stage skip %s` needs --reason "<why>".' % phase)
        return 1
    if phase == "ideation" and pj.ideation_in_use(intent):
        asked = ideation_asked(pj, intent)
        if asked:
            print("Ideation is in use for %s and IDEATION was requested (%s), so the human decides it: Ideation can no "
                  "longer be skipped. Skip an optional Ideation stage on its own (`%s stage skip <id> --reason ...`), "
                  "or start the work as a new intent (`%s new <slug>`)." % (intent, asked["ts"][:10], TOOL, TOOL))
            return 1
    stages = [st.id for st in PHASE_STAGES[phase] if not stage_recorded(pj, intent, st)]  # by the records
    if not stages:
        print("Every stage of %s already has a record (done or skipped); nothing to skip." % name)
        return 0
    pj.append("PHASE_SKIPPED", {"phase": phase, "stages": stages, "reason": mask(reason)[:NOTE_MAX]}, intent)
    refresh_state_doc(pj, intent)
    print("Recorded: %s skipped (%s): %s." % (name, one_line(reason, 200),
                                               ", ".join(STAGE_BY_ID[s].name for s in stages)))
    return 0


def cmd_request(pj, args):
    usage = "usage: request IDEATION|REQUIREMENTS|DESIGN|INCEPTION|PLAN [--unit U]|RELEASE|CR-<team>-<n>"
    if not args:
        print(usage)
        return 1
    kind = norm_kind(args[0])
    opts, err = parse_opts(args[1:], ("--unit",))
    if err or (opts.get("--unit") and kind != "PLAN"):
        print("%s\n%s" % (err or "--unit goes with PLAN only", usage))
        return 1
    if kind == "SPEC":
        print("There is no SPEC any more: request REQUIREMENTS, DESIGN, or both together as INCEPTION.\n" + usage)
        return 1
    intent = pj.active()
    target, err = approval_target(pj, intent, kind, unit=opts.get("--unit"))
    if not target:
        print("Cannot request %s: %s." % (kind, err))
        return 1
    if kind == "RELEASE":  # the release record must be the one `lean release` wrote for this code
        problems, _ = release_problems(pj, intent)
        written = last_release_write(pj, intent)
        if not problems and not (written and written["data"].get("fingerprint") == pj.fingerprint()):
            problems.append("operations/release.md was not written by `%s release` for the current code (run it "
                            "again)" % TOOL)
        elif not problems and release_missing(pj, intent):
            problems.append("operations/release.md does not list %s (run `%s release` again)" % (
                missing_text(release_missing(pj, intent)), TOOL))
        if problems:
            print("Cannot request RELEASE: not ready to release: %s." % "; ".join(problems))
            return 1
    if kind in ("REQUIREMENTS", "INCEPTION"):  # Ideation in use: the approval would be refused until IDEATION
        idea = requirements_ideation_problem(pj, intent)
        if idea:
            print("Cannot request %s: %s; the requirements are approved after the Ideation hand-off." % (kind, idea[0]))
            return 1
    if kind == "IDEATION" and ideation_undone(pj, intent):
        print("Cannot request IDEATION: %s." % ideation_undone_text(pj, intent))
        return 1
    digest = target["sha256"]
    pj.append("APPROVAL_REQUESTED", target_data(target), intent)
    who = "the human"
    if kind.startswith("CR-"):
        who = "someone from team %s" % (pj.cr_fields(os.path.join(pj.root, target["path"]))["Owner team"] or "?")
    files = target.get("paths") or [target["path"]]
    reject = "reject PLAN %s <reason>" % digest[:8] if kind == "PLAN" else "reject %s <reason>" % kind
    if kind == "PLAN":
        voids = "Ticking its steps keeps the approval; any other change to the file voids it."
    elif kind == "IDEATION":
        voids = "Any later change to these pages, or a new Ideation page, voids the approval."
    else:
        voids = "Any later change to %s voids the approval." % ("either file" if len(files) > 1 else "the file")
    print("Ask %s to read %s and, if they agree, type exactly:\n\n    approve %s %s\n\nor `%s`. %s" % (
        who, " and ".join(files), kind, digest[:8], reject, voids))
    if intent and not kind.startswith("CR-"):
        if session_notes_untouched(pj, intent):
            print("Reminder: the Session notes in %s/%s/%s are still the template: update the Session notes before "
                  "you stop (Status, Next)." % (DOCS, intent, STATE_DOC))
        refresh_state_doc(pj, intent)
    return 0


def protected_baseline(pj, intent):
    base = None
    for e in pj.events():
        if e.get("event") == "APPROVED" and e["data"].get("kind") in ("REQUIREMENTS", "INCEPTION") \
                and e.get("intent") == intent:
            base = e["data"].get("protected_baseline")
    return base


def protected_drift(pj, intent):
    base = protected_baseline(pj, intent)
    if base is None:
        return []
    allowed = {e["data"].get("path") for e in pj.events() if e.get("event") == "PROTECTED_CHANGE"}
    now_files = pj.protected_files()
    changed = [p for p in sorted(set(base) | set(now_files)) if base.get(p) != now_files.get(p)]
    return [p for p in changed if p not in allowed]


def git_head(pj):
    """(commit, branch); empty strings where git has none (e.g. no commit yet)."""
    code, head = run(["git", "rev-parse", "HEAD"], pj.root)
    bcode, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], pj.root)
    return (head if code == 0 else ""), (branch if bcode == 0 else "")


def code_span(text):
    text = text.replace("|", "\\|")
    return "`` %s ``" % text if "`" in text else "`%s`" % text


def cmd_verify(pj, args):
    checks = pj.cfg.get("checks") or []
    intent = pj.active()
    if not checks:
        print("No checks configured. Add commands to `checks` in %s/lean.json (build, tests, lint, probes)." % DOCS)
        return 1
    results, ok = [], True
    for c in checks:
        t0 = time.time()
        try:
            p = subprocess.run(c, shell=True, cwd=pj.root, capture_output=True, text=True,
                               timeout=pj.cfg.get("check_timeout_sec", 1800))
            code, out = p.returncode, (p.stdout + p.stderr)
        except subprocess.TimeoutExpired as e:
            partial = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            code, out = 124, "TIMEOUT after %ss\n%s" % (e.timeout, partial)
        secs = round(time.time() - t0, 1)
        ok = ok and code == 0
        shown = mask(out).strip().splitlines()  # mask before cutting, so a cut-off secret block is still masked
        results.append({"cmd": mask(c), "exit": code, "secs": secs, "output_sha256": sha256_bytes(out.encode()),
                        "tail": "\n".join(shown[-30:])})
        print("%s  %s  (%ss)" % ("PASS" if code == 0 else "FAIL", mask(c), secs))
        if code != 0:
            print("\n".join("    " + l for l in shown[-15:]))
    drift = protected_drift(pj, intent) if intent else []
    if drift:
        ok = False
        print("FAIL  protected files changed without the human's permission: " + ", ".join(drift))
    fp = pj.fingerprint()
    ts = now()
    head, branch = git_head(pj)
    dirty = uncommitted_product_paths(pj)
    # a released intent's records are closed: the run is still logged (the commit gate needs it), not filed there
    target = intent if intent and not pj.released(intent) else None
    if intent and not target:
        print("Note: %s is released, so its build-and-test summary was left as it is." % intent)
    evidence = summary = None
    data = {"ok": ok, "fingerprint": fp, "evidence": None, "protected_drift": drift,
            "results": [{k: r[k] for k in ("cmd", "exit", "secs", "output_sha256")} for r in results],
            "base_commit": head or None, "branch": branch or None,
            "uncommitted": len(dirty) if dirty is not None else None}
    if pj.cfg.get("regulated") and target:
        evidence = "%s/%s/%s/verify-%s.md" % (DOCS, target, EVIDENCE_DIR, ts.replace(":", "").replace(".", "-"))
        body = ["# Verify evidence", "", "- time: %s" % ts, "- fingerprint: %s" % fp,
                "- base commit (HEAD at verify time): %s (%s)" % (head[:12] or "none yet", branch or "-"),
                "- working tree: %s" % tree_text(dirty), "- result: %s" % ("PASS" if ok else "FAIL"), ""]
        for r in results:
            body += ["## `%s`" % r["cmd"], "", "exit %s, %ss, output sha256 %s" % (r["exit"], r["secs"],
                                                                                 r["output_sha256"]),
                     "", "```", r["tail"], "```", ""]
        if drift:
            body += ["## Protected files changed", ""] + ["- " + x for x in drift]
        write_text(os.path.join(pj.root, evidence), "\n".join(body) + "\n")
        data["evidence"] = evidence
        data["evidence_sha256"] = sha256_file(os.path.join(pj.root, evidence))
    if target:
        summary = "%s/%s/%s" % (DOCS, target, SUMMARY_DOC)
        write_text(os.path.join(pj.root, summary), build_summary(pj, target, ts, ok, fp, results, drift, data, dirty))
        data["summary"] = summary
        data["summary_sha256"] = sha256_file(os.path.join(pj.root, summary))
    pj.append("VERIFY", data, target)
    if ok and target:
        pj.append("STAGE_COMPLETED", {"stage": "build-and-test", "unit": None, "fingerprint": fp,
                                      "note": "verify PASS: %d check%s on code fingerprint %s" % (
                                          len(results), "" if len(results) == 1 else "s", (fp or "")[:8]),
                                      "outputs": {summary: data["summary_sha256"]}}, target)
    if target:
        refresh_state_doc(pj, target)
    print("verify: %s%s%s" % ("PASS" if ok else "FAIL", (" — summary " + summary) if summary else "",
                              (" — evidence " + evidence) if evidence else ""))
    return 0 if ok else 1


def build_summary(pj, intent, ts, ok, fp, results, drift, data, dirty):
    head, branch = data.get("base_commit") or "", data.get("branch") or ""
    lines = ["# Build and Test Summary: %s" % intent_title(pj, intent), "",
             "Intent: %s · written by `lean verify`; the next verify replaces it (do not edit)." % intent, "",
             "- time: %s" % ts, "- result: %s" % ("PASS" if ok else "FAIL"), "- code fingerprint: %s" % fp,
             "- base commit (HEAD at verify time): %s (%s)" % (head[:12] or "none yet", branch or "-"),
             "- working tree: %s" % tree_text(dirty)]
    if data.get("evidence"):
        lines.append("- evidence: %s (sha256 %s)" % (pj.short(intent, data["evidence"]), data["evidence_sha256"][:12]))
    lines += ["", "## Checks", "", "| # | Command | Exit | Seconds | Output sha256 |", "|---|---|---|---|---|"]
    lines += ["| %d | %s | %s | %s | %s |" % (n, code_span(r["cmd"]), r["exit"], r["secs"], r["output_sha256"][:12])
              for n, r in enumerate(results, 1)]
    lines += ["", "## Protected files", ""]
    if not pj.cfg.get("protected_paths"):
        lines.append("- none configured")
    elif drift:
        lines.append("- changed without the human's permission: " + ", ".join(drift))
    elif protected_baseline(pj, intent) is None:
        lines.append("- no baseline yet (it is taken when the requirements are approved)")
    else:
        lines.append("- unchanged since the requirements were approved (changes a human allowed do not count)")
    return "\n".join(lines) + "\n"


def cmd_cr(pj, args):
    usage = 'usage: cr new <slug> --owner TEAM --paths path1,path2 | cr close <CR-id> --reason "<why>"'
    if args and args[0] == "close":
        return cr_close(pj, args[1:], usage)
    opts, err = parse_opts(args[2:], ("--owner", "--paths")) if len(args) >= 2 and args[0] == "new" else (None, "")
    if not opts or not opts.get("--owner") or not opts.get("--paths"):
        print(usage + ("  (%s)" % err if err else ""))
        return 1
    me = re.sub(r"[^A-Za-z0-9_]", "_", pj.team() or "unknown")
    owner, paths = opts["--owner"], opts["--paths"]
    d = os.path.join(pj.root, pj.cfg["contracts_dir"], "changes")
    os.makedirs(d, exist_ok=True)
    n = 1 + max([int(m.group(1)) for x in os.listdir(d) for m in [re.match(r"CR-%s-(\d+)" % re.escape(me), x)] if m] or [0])
    cid = "CR-%s-%d" % (me, n)
    slug = re.sub(r"[^a-z0-9-]+", "-", args[1].lower()).strip("-") or "change"
    path = os.path.join(d, "%s-%s.md" % (cid, slug))
    write_text(path, template("cr.md", ID=cid, TITLE=slug.replace("-", " "), FROM=me, OWNER=owner, PATHS=paths,
                              DATE=now()[:10]))
    pj.append("CR_OPENED", {"id": cid, "owner_team": owner, "paths": paths.split(",")}, pj.active())
    print("Created %s. Fill it in, then `%s request %s` for team %s." % (rel(pj.root, path), TOOL, cid, owner))
    return 0


def cr_close(pj, args, usage):
    """`cr close <CR-id> --reason "<why>"`: the change request no longer unlocks the owner's contract paths.
    Either team may close it: the one that requested it or the one that owns the contract."""
    opts, err = parse_opts(args[1:], ("--reason",)) if args and not args[0].startswith("--") else (None, "")
    reason = ((opts or {}).get("--reason") or "").strip()
    if not opts or not reason:
        print(usage + ("  (%s)" % err if err else "  (`cr close` needs --reason)"))
        return 1
    cid = norm_kind(args[0])
    path = pj.cr_path(cid) if cid.startswith("CR-") else None
    if not path:
        print("There is no %s file in %s/changes/." % (args[0], pj.cfg["contracts_dir"].rstrip("/")))
        return 1
    f = pj.cr_fields(path)
    cid = f["id"]
    closed = pj.cr_closed(cid)
    if closed:
        print("%s is already closed (%s: %s)." % (cid, closed["ts"][:10], one_line(closed["data"].get("reason"), 200)))
        return 1
    teams = [t for t in (f["Requested by team"], f["Owner team"]) if t]
    if pj.cfg.get("multi_team") and teams and team_key(pj.team()) not in [team_key(t) for t in teams]:
        print("Only team %s can close %s (this clone is team %s)." % (" or team ".join(teams), cid,
                                                                       pj.team() or "not set"))
        return 1
    pj.append("CR_CLOSED", {"id": cid, "path": rel(pj.root, path), "reason": mask(reason)[:NOTE_MAX],
                            "owner_team": f["Owner team"], "requested_by": f["Requested by team"]}, pj.active())
    print("Closed %s: it no longer unlocks %s for team %s. A further change needs a new change request." % (
        cid, ", ".join(f["paths"]) or "any path", f["Requested by team"] or "?"))
    return 0


def release_problems(pj, intent, local=True):
    """(problems, last verify): what stops a release of the intent (`release`, `request RELEASE` and the approval).
    local=False leaves out what depends on this clone (its own last verify): for the committed aidlc-state.md,
    which every clone renders the same way."""
    problems = [short for _, _, short in gate_problems(pj, intent, strict=True)]
    lv = pj.last_verify()
    checks = pj.cfg.get("checks")
    if not checks and pj.cfg.get("regulated"):
        problems.append("no checks configured in %s/lean.json (regulated mode releases only verified code)" % DOCS)
    if local and checks and (not lv or not lv["data"].get("ok") or lv["data"].get("fingerprint") != pj.fingerprint()):
        problems.append("no passing verify on the current code")
    return problems, lv


def cmd_release(pj, args):
    intent = need_intent(pj)
    if not intent:
        return 1
    problems, lv = release_problems(pj, intent)
    fp = pj.fingerprint()
    checks = pj.cfg.get("checks")
    if problems:
        print("Not ready to release: " + "; ".join(problems))
        return 1
    dirty = uncommitted_product_paths(pj)
    if dirty:  # release.md names a commit: it must hold the verified code
        print("Not ready to release: commit the verified code first, then run `%s release` (%d uncommitted product "
              "change%s: %s%s)." % (TOOL, len(dirty), "" if len(dirty) == 1 else "s", ", ".join(dirty[:5]),
                                    " and %d more" % (len(dirty) - 5) if len(dirty) > 5 else ""))
        print("Build output (e.g. __pycache__/, dist/) does not belong in a commit: add it to .gitignore instead.")
        return 1
    head, branch = git_head(pj)
    rows = [row for _, row in release_rows(pj, intent)]
    if checks:
        summary = lv["data"].get("summary")
        verified = "- verify: PASS at %s%s%s" % (lv["ts"], (" — " + summary) if summary else "",
                                                 (" — evidence " + lv["data"]["evidence"]) if lv["data"].get("evidence")
                                                 else "")
    else:
        verified = "- checks: none configured (nothing was verified)"
    body = ["# Release: %s" % intent_title(pj, intent), "",
            "Intent: %s · written by `lean release` on %s" % (intent, now()[:10]), "",
            "- commit: %s (%s)" % (head or "uncommitted", branch or "-"), "- code fingerprint: %s" % fp, verified,
            "", "## Stages", ""] + progress_lines(pj, intent, {"release": (
                "-", "this page; next: `request RELEASE` and the human's approval")}) + [
            "", "## Approvals", "", "| what | file | sha256 | by (team) | when |", "|---|---|---|---|---|"] + rows + [
            "", "## Open items", "", "(copy unresolved questions, known gaps and follow-ups from aidlc-state.md)", ""]
    path = pj.doc(intent, RELEASE_DOC)
    write_text(path, "\n".join(body) + "\n")
    pj.append("STAGE_STARTED", {"stage": "release", "unit": None, "path": rel(pj.root, path),
                                "sha256": sha256_file(path), "fingerprint": fp, "head": head}, intent)
    refresh_state_doc(pj, intent)
    if not checks:
        print("Warning: no checks are configured in %s/lean.json, so nothing was verified; release.md says so." % DOCS)
    print("Wrote %s. Fill in Open items, then `%s request RELEASE`." % (rel(pj.root, path), TOOL))
    return 0


def superseded_note(pj, intent, e, later):
    """' (superseded)' when newer approvals cover every file an approval covered (' (superseded for <files>)'
    when they cover only some of an INCEPTION approval's files), else ''. IDEATION is one approval over the whole
    set of Ideation pages: a newer IDEATION approval of the intent supersedes it as a whole."""
    d = e.get("data") or {}
    if d.get("kind") == "IDEATION":
        return " (superseded)" if any((x.get("data") or {}).get("kind") == "IDEATION" and x.get("intent") ==
                                      e.get("intent") for x in later) else ""
    files = sorted(d["files"]) if isinstance(d.get("files"), dict) else [d.get("path")]
    newer = [f for f in files if f and any(covers(x, f) for x in later)]
    if not newer:
        return ""
    if len(newer) == len(files):
        return " (superseded)"
    return " (superseded for %s)" % ", ".join(pj.short(intent, f) for f in newer)


def chain_check(pj):
    report, ok = [], True
    d = pj.ledger_dir()
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not name.endswith(".jsonl"):
            continue
        prev, seq, bad = "GENESIS", 0, None
        for i, line in enumerate(read_text(os.path.join(d, name)).splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                h = rec.pop("hash")
                if rec["prev"] != prev or rec["seq"] != seq + 1 or \
                        sha256_bytes(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode()) != h:
                    bad = i
                    break
                prev, seq = h, rec["seq"]
            except (ValueError, KeyError):
                bad = i
                break
        ok = ok and bad is None
        report.append("%s  %s: %s" % ("OK  " if bad is None else "BROKEN", name,
                                      "%d records" % seq if bad is None else "chain breaks at line %d" % bad))
    if not report and pj.initialized:  # init always writes a first record, so the trail has gone missing
        return False, ["MISSING  %s/audit/: no ledger files (restore them from git, e.g. "
                       "`git checkout -- %s/audit`)" % (DOCS, DOCS)]
    return ok, report


def audit_desc(pj, e):
    a, dd = e.get("actor", {}), e.get("data", {})
    if e["event"] == "VERIFY":
        base = ""
        if "base_commit" in dd:
            n = dd.get("uncommitted")
            base = " · base commit %s%s" % ((dd.get("base_commit") or "none")[:12],
                                            "" if n == 0 else " + %s uncommitted product change(s)" % (
                                                "?" if n is None else n))
        return "%s fingerprint %s %s%s%s" % ("PASS" if dd.get("ok") else "FAIL", (dd.get("fingerprint") or "")[:12],
                                             dd.get("evidence") or dd.get("summary") or "",
                                             " (sha256 %s)" % dd["evidence_sha256"][:12] if dd.get("evidence_sha256")
                                             else "", base)
    if e["event"] == "INTENT_SWITCHED":
        return "from %s to %s" % (dd.get("from") or "(none)", dd.get("to"))
    if e["event"] == "BLOCKED":
        return "%s: %s" % (dd.get("gate"), dd.get("path") or dd.get("command"))
    if e["event"] in ("SESSION_START", "SUBAGENT_START"):
        agents = ", ".join(dd.get("agents") or [])
        return "branch %s head %s%s" % (dd.get("branch"), dd.get("head"), (" · subagent " + agents) if agents else "")
    if e["event"] in ("HUMAN_TURN", "SUBAGENT_PROMPT", "HOST_TURN"):
        return "%s%s chars, sha256 %s%s" % ("turn %s, " % dd["turn"] if dd.get("turn") else "", dd.get("chars", "?"),
                                           (dd.get("sha256") or "")[:12],
                                           " · subagent %s (matched by %s)" % (dd.get("agent") or "?", dd.get("match"))
                                           if e["event"] == "SUBAGENT_PROMPT" else "")
    if e["event"] == "APPROVAL_REFUSED":
        return "%s refused (%s) — %s — %s" % (kind_label(dd), ("typed " + dd["given"][:8]) if dd.get("given")
                                              else "no hash typed", one_line(dd.get("reason"), 300),
                                              one_line(dd.get("words"), 200))
    if e["event"] == "CR_CLOSED":
        return "%s closed — %s" % (dd.get("id"), one_line(dd.get("reason"), 300))
    if e["event"] == "CR_OPENED":
        return "%s opened for team %s: %s" % (dd.get("id"), dd.get("owner_team"), ", ".join(dd.get("paths") or []))
    if e["event"] == "INTENT_CREATED":
        return "intent created: %s%s" % (one_line(dd.get("title"), 200),
                                         " (with Ideation)" if dd.get("ideation") else "")
    if e["event"] == "PHASE_SKIPPED":
        covered = phase_skip_stages(dd)
        return "%s skipped — %s%s" % (PHASES.get(dd.get("phase")) or dd.get("phase"), one_line(dd.get("reason"), 300),
                                      " (stages: %s)" % covered if covered else "")
    if e["event"] in STAGE_EVENTS:
        st = STAGE_BY_ID.get(dd.get("stage"))
        name = (st.name if st else str(dd.get("stage"))) + (" (%s)" % dd["unit"] if dd.get("unit") else "")
        if e["event"] == "STAGE_SKIPPED":
            return "%s skipped — %s" % (name, one_line(dd.get("reason"), 300))
        if e["event"] == "STAGE_STARTED":
            return "%s started%s" % (name, (" — " + dd["path"]) if dd.get("path") else "")
        outs = ", ".join("%s (%s)" % (p, (h or "missing")[:12]) for p, h in sorted((dd.get("outputs") or {}).items()))
        return "%s done — %s%s" % (name, one_line(dd.get("note"), 300), ("; outputs " + outs) if outs else "")
    return "%s %s %s %s" % (dd.get("kind") or dd.get("id") or "", event_paths(dd),
                            (dd.get("sha256") or "")[:12], ("— " + dd["words"]) if dd.get("words") else "")


SESSION_EVENTS = ("SESSION_START", "SUBAGENT_START", "SUBAGENT_PROMPT")


def intent_window(pj, intent):
    """(first, last) ledger times of an intent: its INTENT_CREATED (else its first event) and its RELEASE
    approval (None while it is not released)."""
    first = next((e.get("ts") for e in pj.events() if e.get("event") == "INTENT_CREATED" and e.get("intent") == intent),
                 None) or next((e.get("ts") for e in pj.events() if e.get("intent") == intent), None)
    done = pj.released(intent)
    return first, (done or {}).get("ts")


def in_window(e, window):
    first, last = window or (None, None)
    ts = e.get("ts") or ""
    return (not first or ts >= first) and (not last or ts <= last)


def cmd_audit(pj, args):
    if not args or args[0] not in ("verify", "pack"):
        print("usage: audit verify | audit pack [intent]")
        return 1
    intent = pj.active()
    if args[0] == "pack" and len(args) > 1:
        intent = resolve_intent(pj, args[1])
        if not intent:
            print("Unknown intent %s. Pick one of: %s" % (args[1], ", ".join(pj.list_intents()) or "(none)"))
            return 1
    ok, report = chain_check(pj)
    if args[0] == "verify":
        if not report:
            print("no ledger files: AI-DLC Lean is not initialized here (run `%s init`)" % TOOL)
            return 1
        print("\n".join(report))
        return 0 if ok else 1

    window = intent_window(pj, intent) if intent else None

    def wanted(e):
        """All intents: everything. One intent: its own events, contract change request events, its `use`
        switches, and the sessions and subagents between its creation and its RELEASE approval (inclusive)."""
        if not intent:
            return True
        if e.get("event") in SESSION_EVENTS:
            return in_window(e, window)
        dd = e.get("data") or {}
        if e.get("intent") == intent and window and window[1] and (e.get("ts") or "") > window[1]:
            # after the RELEASE approval: keep the Release record that approval writes, the Operations (and
            # ci-pipeline) records that may follow it, and `use` switches; other events still tagged with the
            # released intent are later work, not this intent's trail
            return ((e.get("event") == "STAGE_COMPLETED" and dd.get("stage") == "release")
                    or (e.get("event") in STAGE_EVENTS and dd.get("stage") in AFTER_RELEASE_IDS)
                    or (e.get("event") == "PHASE_SKIPPED" and dd.get("phase") == "operations")
                    or (e.get("event") == "INTENT_SWITCHED" and intent in (dd.get("from"), dd.get("to"))))
        return (e.get("intent") == intent or str(e.get("event")).startswith("CR_")
                or str(dd.get("kind", "")).startswith("CR-")
                or (e.get("event") == "INTENT_SWITCHED" and intent in (dd.get("from"), dd.get("to"))))
    evs = [e for e in pj.events() if wanted(e)]
    out = ["# Audit trail: %s" % (intent or "all intents"), "",
           "Generated %s by `lean audit pack` (AI-DLC Lean %s) from the ledger in %s/audit/; do not edit."
           % (now(), VERSION, DOCS), "", "## Ledger integrity", ""] + ["- " + r for r in report] + [
           "", "Hash chains detect edits inside a ledger file; they do not stop someone rewriting a whole file. "
           "Pair them with a protected branch and merge-request approvals in your Git server.", "",
           "Each entry names who recorded it: `human (prompt)` for what the prompt hook took from the human's own "
           "message, `via CLI` for the tool's commands (run by the agent or a person in that clone), `hook (...)` for "
           "the other hook entries.", ""]
    sections = [("Stages", ("INTENT_CREATED",) + STAGE_EVENTS + ("PHASE_SKIPPED",)),
                ("Approvals and rejections", ("APPROVED", "REJECTED", "APPROVAL_REQUESTED", "APPROVAL_REFUSED")),
                ("Verification runs", ("VERIFY",)), ("Blocked attempts", ("BLOCKED",)),
                ("Protected-file changes allowed by a human", ("PROTECTED_CHANGE",)),
                ("Contract change requests", ("CR_OPENED", "CR_CLOSED")),
                ("Intent switches (`use`)", ("INTENT_SWITCHED",)), ("Sessions", ("SESSION_START",)),
                ("Human turns", ("HUMAN_TURN",)),
                ("Subagents and host prompts (not the human)", ("SUBAGENT_START", "SUBAGENT_PROMPT", "HOST_TURN"))]
    for title, kinds in sections:
        rows = [e for e in evs if e["event"] in kinds]
        out += ["## %s (%d)" % (title, len(rows)), ""]
        if "CR_OPENED" in kinds and pj.cr_files():
            out += ["- State now: " + "; ".join("%s %s" % (pj.cr_fields(p)["id"], pj.cr_state(p))
                                               for p in pj.cr_files()), ""]
        for e in rows:
            out.append("- %s · %s · %s · %s · %s" % (e["ts"], e["event"], actor_text(e, " (%s)"), source_label(e),
                                                     audit_desc(pj, e).strip()))
        out.append("")
    target = pj.doc(intent, AUDIT_DOC) if intent else os.path.join(pj.docs, AUDIT_DOC)
    write_text(target, "\n".join(out) + "\n")
    print("Wrote %s (ledger %s)." % (rel(pj.root, target), "OK" if ok else "BROKEN"))
    return 0 if ok else 1


def cmd_doctor(pj, args):
    problems = []
    if sys.version_info < (3, 8):
        problems.append("Python 3.8+ needed")
    for f in ("aidlc-lean-session-start.json", "aidlc-lean-prompt.json", "aidlc-lean-guard.json"):
        if not os.path.exists(os.path.join(pj.root, ".kiro", "hooks", f)):
            problems.append("missing .kiro/hooks/" + f)
    if not os.path.exists(os.path.join(pj.root, ".kiro", "steering", "aidlc-lean.md")):
        problems.append("missing .kiro/steering/aidlc-lean.md")
    missing = [n for n in TEMPLATE_NAMES if not os.path.exists(os.path.join(TEMPLATES, n))]
    if missing:
        problems.append("missing templates in .kiro/aidlc-lean/templates/: " + ", ".join(missing))
    if os.path.exists(os.path.join(pj.root, "aidlc", "lean.json")):
        problems.append("found aidlc/ from AI-DLC Lean 0.1: AI-DLC Lean %s reads only %s/ (lean.json, audit/, "
                        "contracts/ and one folder per intent)" % (VERSION, DOCS))
    last_start = None
    if not pj.initialized:
        problems.append("not initialized (run init)")
    else:
        if pj.contracts_dir_problem:
            problems.append(pj.contracts_dir_problem)
        if str(pj.cfg.get("contracts_dir") or "").strip("/") == "aidlc/contracts":
            problems.append("contracts_dir in %s/lean.json is the 0.1 path aidlc/contracts; AI-DLC Lean %s uses "
                            "%s/contracts" % (DOCS, VERSION, DOCS))
        if not pj.cfg.get("checks"):
            problems.append("no checks configured (verify and the commit gate do nothing)")
        if pj.cfg.get("multi_team") and not pj.team():
            problems.append("multi-team mode but this clone has no team (init --team NAME or AIDLC_LEAN_TEAM)")
        here = os.path.basename(pj.ledger_file())  # teammates' committed ledgers do not count
        # a person's chats only: a subagent's start is logged as SUBAGENT_START and does not count
        starts = [e for e in pj.events() if e.get("event") == "SESSION_START" and e.get("_file") == here]
        if starts:
            last_start = starts[-1].get("ts")
        else:
            problems.append("hooks have never run here: start `kiro-cli --v3` in this folder and trust the workspace")
        ok, _ = chain_check(pj)
        if not ok:
            problems.append("audit ledger is missing or its chain is broken (run `audit verify`)")
    print("doctor: " + ("OK" if not problems else "\n  - " + "\n  - ".join(problems)))
    if last_start:
        print("  hooks last ran in this clone at %s (SessionStart)" % last_start)
    return 0 if not problems else 1


COMMANDS = {"init": cmd_init, "new": cmd_new, "use": cmd_use, "status": cmd_status, "stage": cmd_stage,
            "request": cmd_request, "verify": cmd_verify, "cr": cmd_cr, "release": cmd_release, "audit": cmd_audit,
            "doctor": cmd_doctor}


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if argv[0] == "hook":
        return cmd_hook(os.getcwd(), argv[1] if len(argv) > 1 else "")
    if argv[0] == "--version":
        print(VERSION)
        return 0
    fn = COMMANDS.get(argv[0])
    if not fn:
        print("unknown command %s\n%s" % (argv[0], __doc__))
        return 1
    return fn(Project(find_root()), argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
