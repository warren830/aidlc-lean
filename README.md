# AI-DLC Lean

AI-DLC 的轻量版，给 **Kiro CLI（v3 引擎）** 用。版本 0.3.1（只修问题，见设计说明 §10）。

它保留 AI-DLC 的样子：

- 阶段的顺序和名字照 AI-DLC；
- 文件名和目录也照 AI-DLC（`aidlc-docs/`、`aidlc-state.md`、`requirements.md`……）；
- 每一步做了什么，都有记录；
- 能追溯：验收标准一路对到测试。

去掉的是繁琐的部分：

- 人只批 3 处：需求、设计（这两处可以一次批）、发布。受监管模式下，每个单元的代码计划再批一次；用了构想阶段，开头再批一次 IDEATION；
- 不再每个阶段一份问题文件，开头一次问完；
- 没有角色扮演；
- 每份文档一页。

v0.3 加回了 AI-DLC 的两段，都是**可选的**，默认不开：

- **构想**（Ideation，7 个阶段）：写给产品经理用，从一个想法写到一份批过的立项简报。用 `lean new <名字> --ideation` 打开，最后由人批一次 IDEATION；
- **部署和运维**（Operations，7 个阶段），加上构建段里的 CI 流水线（ci-pipeline）：发布前后都能写。规则是 **AI 只写文档和配置，不部署**，部署交给团队自己的 CI/CD。这条是写给 AI 的规则，工具不能保证它做到（见 1a）。

照样能用在**受监管、多团队、跨多天**的项目上。

**什么时候用 Lean**（2026-11-10 定的）：
- 小而清楚的需求，直接用 Kiro（vibe），不走 Lean。Kiro v3 + Kimi K3 每题跑 3 次的对比里，小题上 Lean 花的积分约是 vibe 的 5.6 倍、时间约 4 倍，质量一样。
- 需求有空白、要跨团队、或者受监管的工作，用 Lean。vibe 和 Lean 的对比结果见报告。
- 对比报告：`ai-native-dev/k3-cli-compare/报告-vibe对比Lean-K3-3轮汇总-20261110.md`。

体量（2026-11-10 用 `wc` 数的）：

- **每轮常驻说明**：999 词（装 pstack 包再加 144 词）。2.11.3 的 Kiro 发行版约 1.6 万词，能跑 v3 的 kiro-ide 发行版约 1.8 万词。
- **代码**：一个 Python 脚本，4,434 行，只用标准库。2.11.3 的引擎约 24 万行。

详细对比见 [COMPARISON.md](COMPARISON.md)，设计说明见 [docs/design-v0.2.md](docs/design-v0.2.md)。

## 先说清楚：这是护栏，不是安全边界

- Lean 的关卡是**护栏**：防的是 AI 图省事、跳步骤、走捷径。
- 它**不是安全边界**。AI 能跑命令（有 shell）时，还是能绕开其中一些检查。
- 受监管项目真正的控制在 **Git 服务器**：GitLab 的保护分支、MR（合并请求）审批、签名提交。
- 安全加固会另做一个工具，结合 AWS Continuum 来做，细节还没定。

## 从 AI-DLC 保留了什么

### 1. 阶段：顺序和名字照 AI-DLC

一件要做的事叫一个 intent，一个 intent 一个目录：`aidlc-docs/<日期>-<名字>/`，比如 `aidlc-docs/261108-refunds/`。下表的文件都在这个目录里。

`<unit>` 是单元名。单元是能单独交付的一块代码，比如 `api`、`web`。没拆单元时只有一个，叫 `app`。

| # | 阶段（AI-DLC 的名字） | 命令里的 id | 文件 | 能跳过吗 | 人批 |
|---|---|---|---|---|---|
| 1 | Reverse Engineering 逆向工程 | `reverse-engineering` | `inception/reverse-engineering/architecture.md` | 能（新项目） | – |
| 2 | Requirements Analysis 需求分析 | `requirements` | `inception/requirements/requirements.md` | 不能 | **REQUIREMENTS**（或 INCEPTION） |
| 3 | User Stories 用户故事 | `user-stories` | `inception/user-stories/stories.md` | 能 | – |
| 4 | Application Design 应用设计 | `application-design` | `inception/application-design/application-design.md` | 只有需求页写着 `Size: small` 才能跳 | **DESIGN**（或 INCEPTION） |
| 5 | Units Generation 拆分单元 | `units` | `inception/application-design/unit-of-work.md` | 能（只有一个单元时） | – |
| 6 | Functional Design 功能设计（每个单元） | `functional-design` | `construction/<unit>/functional-design/functional-design.md` | 能 | – |
| 7 | NFR Requirements + Design 非功能需求和设计（每个单元） | `nfr-design` | `construction/<unit>/nfr-design/nfr-design.md` | 能 | – |
| 8 | Infrastructure Design 基础设施设计（每个单元） | `infrastructure-design` | `construction/<unit>/infrastructure-design/infrastructure-design.md` | 能 | – |
| 9 | Code Generation 代码生成（每个单元） | `code-generation` | `construction/plans/<unit>-code-generation-plan.md`，然后写代码 | 不能 | 只在受监管模式：**PLAN** |
| 10 | Build and Test 构建测试 | `build-and-test` | `construction/build-and-test/build-and-test-summary.md`（工具写） | 不能 | –（只在失败时停） |
| 11 | CI Pipeline CI 流水线（v0.3，可选，见 1a） | `ci-pipeline` | `construction/ci-pipeline/ci-config.md` | 能 | – |
| 12 | Release 发布 | `release` | `operations/release.md`（工具写，AI 补 Open items：未完事项） | 不能 | **RELEASE** |

- 1-5 属于 Inception（想清楚做什么、为什么），6-11 属于 Construction（怎么做），12 自成一段 Release（发布；文件放在 `operations/` 下）。可选的构想段在 1 前面，运维段在 12 后面（见 1a）。
- 6-9 一个单元一个单元地做：先做完一个单元的设计、计划和代码，再做下一个。
- 跳过阶段要写理由：`lean stage skip <id> --reason "..."`，理由会记下来。括号里是常见的跳过场合；跳不跳由 AI 按规则判断。工具只查这几条：需求、代码生成、构建测试、发布不让跳；应用设计要需求页写着 `Size: small` 才能跳；用了构想，意图、范围、交接审批 3 个不让跳；发布以后只有运维阶段和 ci-pipeline 还能跳；没写理由不让跳。
- 和 AI-DLC v1（aidlc-workflows 1.0.1）的几处不同：
  - Workspace Detection（看工作区）和 Workflow Planning（定流程）不单列，并进"先读代码"和"跳过要写理由"；
  - NFR Requirements 和 NFR Design 合成一页；
  - 多了一层 intent 目录（v1 直接放在 `aidlc-docs/` 下）；
  - v1 的 Operations 还是空的占位；这里另设一段 Release：写发布记录、人批发布。v0.3 另有可选的构想段和运维段（见下一节），运维段也只写文档和配置，不部署。

### 1a. 可选的两段：构想、部署运维（v0.3）

阶段的 id 照 AI-DLC main（`d12d620`）的构想 7 个阶段、运维 7 个阶段和构建段的 CI 流水线。显示的名字用短写，不全和 main 一样：比如 main 的 Intent Capture & Framing、Feasibility & Constraints、Approval & Handoff、Feedback & Optimization，这里叫 Intent Capture、Feasibility、Approval Handoff、Feedback Optimization。每个阶段一页，文件名大多用 AI-DLC main 这个阶段的主要产物名；`market-research.md` 和 `observability.md` 是 Lean 起的名字（main 分成 `competitive-analysis.md`、`dashboards.md`、`alarms.md` 等几份）。

**构想**（Ideation）：写给产品经理（PM）的。PM 回答问题、读每一页、自己打审批口令；AI 提问、起草页面、跑 `lean`。技能卡 `aidlc-lean-ideation`。

| 阶段 | 命令里的 id | 文件 | 能跳过吗 |
|---|---|---|---|
| Intent Capture 意图 | `intent-capture` | `ideation/intent-capture/intent-statement.md`（问题、客户、成功指标、为什么现在做、干系人） | 用了构想就不能跳 |
| Market Research 市场调研 | `market-research` | `ideation/market-research/market-research.md`（替代方案、趋势、自建还是买） | 能 |
| Feasibility 可行性 | `feasibility` | `ideation/feasibility/feasibility-assessment.md`（约束、RAID） | 能 |
| Scope Definition 范围 | `scope-definition` | `ideation/scope-definition/scope-document.md`（做什么、不做什么、排好序的待办） | 用了构想就不能跳 |
| Team Formation 组队 | `team-formation` | `ideation/team-formation/team-assessment.md`（人手、技能缺口、RACI） | 能 |
| Rough Mockups 草图 | `rough-mockups` | `ideation/rough-mockups/wireframes.md`（用户流程、文字草图或链接） | 能 |
| Approval Handoff 交接审批 | `approval-handoff` | `ideation/approval-handoff/initiative-brief.md`（立项简报、做不做的建议、决策记录） | 用了构想就不能跳；人批 **IDEATION** |

- **怎么开**：`lean new <名字> --ideation`（`--ideation` 写在名字前面也行），从 Intent Capture 开始。不带 `--ideation` 时，整段记成跳过（理由 "not requested (lean new without --ideation)"），开发者的流程和 v0.2 一样。需求批准之前，`lean stage start intent-capture`（或别的构想阶段）还能把它重新打开。重新打开以后，意图、范围、交接审批这 3 个阶段以前跳过的也不再算数，要写完再用 `lean stage done` 记下。
- **怎么跳**：`lean stage skip ideation --reason "..."`，把还没有记录（没做完也没跳过）的构想阶段一次跳过。IDEATION 请求过以后（不管还在等、批了还是驳回了），就不能整段跳了，由人来定。
- **IDEATION 审批**：简报写完，`lean stage done approval-handoff`，再 `lean request IDEATION`。意图、范围、交接审批 3 个阶段都要用 `lean stage done` 记成做完（只有页面不算），才给口令；人打的 `approve IDEATION` 也要这样才算数。请求以后又 `stage start` 了这 3 个阶段之一，口令先收回（阶段进度不给口令，比如交接审批那一行写 "IDEATION also needs Scope Definition done"；"下一步"写 "finish <阶段>"），等它再 `stage done` 才回来。一个哈希管全部构想页面（存在的那几页，按阶段顺序）；之后改了、加了或删了一页，审批就过期，要重新批。用了构想，IDEATION 没批（或被驳回）时：需求和 INCEPTION 批不了，代码写不了（关卡 `ideation`），`lean release` 也会拒绝。批过又改了的（过期），普通模式下照样能批需求、写代码（`lean status` 标成过期），受监管模式都拦住；发布在哪种模式下都要求它对得上现在的文件：`lean release`、`lean request RELEASE` 和 RELEASE 审批都会拒绝。`approvers` 可以只让 PM 批 IDEATION，比如 `"approvers": {"IDEATION": ["pm@corp.com"]}`。
- **请求过 IDEATION 以后**（在等、批了或被驳回）：`lean status` 的"下一步"不再提没开始过的可选构想阶段，因为新加一页，请求就作废，审批就过期。已经开了头的，还是先写完，批了以后也一样（发布前的"下一步"会提它）。过期了就重新请求；被驳回了，就照人的意见改，再请求。改的时候又 `stage start approval-handoff` 了，要先 `stage done approval-handoff`，`request IDEATION` 才给口令。
- 批完以后，开发团队从简报接着做起步段：需求的目标、不做什么、验收标准都从构想页来，只问构想没答的问题。

**CI 流水线和运维**：技能卡 `aidlc-lean-operations`。

| 阶段 | 命令里的 id | 文件 | 什么时候做 |
|---|---|---|---|
| CI Pipeline CI 流水线（构建段，在构建测试之后） | `ci-pipeline` | `construction/ci-pipeline/ci-config.md`（CI 的步骤、质量门、产物） | CI 新建或要改 |
| Deployment Pipeline 部署流水线 | `deployment-pipeline` | `operations/deployment-pipeline/deployment-strategy.md`（CD 配置、发布策略、环境晋级、回滚步骤） | 发布方式新建或要改 |
| Environment Provisioning 环境 | `environment-provisioning` | `operations/environment-provisioning/environment-inventory.md` | 环境有变化 |
| Deployment Execution 部署执行 | `deployment-execution` | `operations/deployment-execution/deployment-log.md`（版本、环境、时间、冒烟测试、健康检查、结果） | 团队的流水线**真的部署过以后** |
| Observability Setup 可观测性 | `observability-setup` | `operations/observability-setup/observability.md`（日志、指标、看板、告警、SLO） | 监控有变化 |
| Incident Response 事故响应 | `incident-response` | `operations/incident-response/runbooks.md`（每个告警的处理步骤、升级路径） | 值班需要步骤 |
| Performance Validation 性能验证 | `performance-validation` | `operations/performance-validation/load-test-plan.md`（先写计划，再填结果，对照非功能指标） | 指标要靠压测证明 |
| Feedback Optimization 反馈优化 | `feedback-optimization` | `operations/feedback-optimization/feedback-loop.md`（SLO 结果、成本、后续的 intent） | 上线几周以后 |

- **AI 不部署**：AI 写文档和配置，部署、建环境、回滚、对共享环境压测都由团队的 CI/CD（比如 GitLab 再到 Argo CD）或人来做。这是常驻说明和技能卡写给 AI 的规则，工具不能保证。禁止名单（关卡 `danger`）只是一份很短的默认名单，有 `terraform apply`、`kubectl apply` 等几条，挡不住所有部署命令；团队自己用的部署命令，由人加进 `aidlc-docs/lean.json` 的 `deny_commands`。真正管住部署的是团队的流水线和权限，比如 AI 跑命令用的账号没有部署权限（和上面"护栏，不是安全边界"一样）。部署记录只在真部署过以后，按流水线和看着部署的人给的事实填。
- **配置就是代码**：CI 文件、K8s 清单、Helm 值、IaC、写成代码的告警和看板，都算产品文件：写代码的关卡照样管，改完要重新 `lean verify`。`aidlc-docs/` 里的页面只是记录。
- **发布前后都能写**：任何模式都可选。发布前写计划类的页面（CI、部署流水线、环境、可观测性、事故响应、压测计划），配置提交并 verify 过，再 `lean release`。RELEASE 的哈希只管 release.md：里面有提交、代码指纹、verify 结果、审批表、Open items，和 `lean release` 那一刻的阶段进度（每个运维阶段当时是做完、跳过还是没开始）；运维页面本身的内容不在里面。所以批完以后再改或新加运维页面，RELEASE 不会作废，这些页面只是记录。但在 `lean release` 和 RELEASE 批准之间记下的阶段记录（`stage start/done/skip`，包括整段跳过运维）会让 release.md 作废，和少了一条审批一样，要重新 `lean release`、重新请求（v0.3.1；按日志里的记录比，不按时间）。所以运维阶段要么在 `lean release` 之前记好，要么等 RELEASE 批了再记。运维的配置文件算在代码指纹里：`lean release` 之后改了，要重新 verify、`lean release`、批。RELEASE 也不等运维页面。发布以后，只有运维阶段和 ci-pipeline 还接受阶段命令，intent 仍然是已发布；`lean status` 的"下一步"会提示 "optional: record deployment and operations ..."，只是提示。
- **发布后只写页面**：要改产品配置（CI 或部署任务、清单、告警阈值），开新 intent。普通模式下小改动可以直接改，但要在阶段说明（`--note`）里写明改了什么，再跑 `lean verify`（这次 verify 记在日志里，不算进已发布 intent 的阶段日志）。受监管模式一律开新 intent。
- **怎么跳**：`lean stage skip operations --reason "..."` 一次跳过还没有记录的运维阶段（不含 ci-pipeline）；ci-pipeline 要单独跳：`lean stage skip ci-pipeline --reason "..."`。

阶段进度列表的顺序：构想 7 个、起步 5 个、构建（每个单元 4 个，然后构建测试、CI 流水线）、发布、运维 7 个。一共 26 个阶段（每个单元的 4 个只算一次）。一段被一次整段跳过时，只显示一行，比如 `- [S] Ideation — skipped: not requested (lean new without --ideation)`、`- [S] Operations — skipped: platform team deploys`。

和 AI-DLC main 的不同：

- main 每个阶段好几份文件，外加一份问题文件，每个阶段做完都请人批；这里每个阶段一页，构想段只在交接时批一次 IDEATION，运维段不批；
- main 的部署执行阶段由 AI 推流水线、跑冒烟测试和数据库迁移，环境阶段由 AI 应用 IaC，性能阶段由 AI 跑压测；这里这些都由团队的流水线或人来做，AI 只写计划和记录；
- main 的运维目录叫 `operation/`，这里沿用 Lean 已有的 `operations/`（`release.md` 也在里面）；
- main 没有 Release 这一步，这里发布审批夹在构建和运维之间。

### 2. 三个审批点

1. **需求**：`approve REQUIREMENTS <哈希>`
2. **设计**：`approve DESIGN <哈希>`。需求和设计可以一次批：`approve INCEPTION <哈希>`，一个哈希管两页。
3. **发布**：`approve RELEASE <哈希>`

另外三种：

- 构想（只在用了构想阶段时）：`approve IDEATION <哈希>`，一个哈希管全部构想页面，要在需求之前批（见 1a）。
- 受监管模式：每个单元的代码计划批一次，`approve PLAN <哈希>`。哈希能认出是哪个单元的计划：一个 intent 有两个以上的计划时，批 PLAN 必须带哈希（普通模式也一样）。批过的计划照样能勾步骤（`- [x]`），审批不会失效；改了步骤的文字、加了或删了步骤，就要重批。
- 多团队：改别的团队的契约，要对方团队的人批 CR（变更申请），`approve CR-<团队>-<编号> <哈希>`。批过的 CR 只给提出申请的那个团队放行，而且只到 CR 关闭为止（`lean cr close <编号> --reason "..."`，对方改完契约后关）。

口令由 AI 跑 `lean request ...` 打出来，比如：

```
Ask the human to read aidlc-docs/261108-refunds/inception/requirements/requirements.md and aidlc-docs/261108-refunds/inception/application-design/application-design.md and, if they agree, type exactly:

    approve INCEPTION 8cf2cbce

or `reject INCEPTION <reason>`. Any later change to either file voids the approval.
```

规则：

- **你自己把这一行单独打出来**，才算批准。"看着行，开干吧"不算；AI 说的话、Kiro 的系统消息也不算。
- 子代理收到的任务说明也不算。Kiro 3.1.0 启动子代理时，会用主对话的会话号再触发一次会话开始和发言的 hook；Lean 把这种任务说明单独记下，不当成人的发言，里面的审批口令也不认。
- 口令没被接受时（比如没带哈希、哈希对不上、批准人不在白名单里、批 RELEASE 时 `lean release` 现在过不了），日志里会记一条 APPROVAL_REFUSED，写明原因，audit.md 里也看得到。
- 中文也行：`批准 INCEPTION 8cf2cbce`、`同意 INCEPTION 8cf2cbce`。不同意就打 `reject INCEPTION <理由>`（或 `驳回`、`拒绝`）。
- 哈希是文件内容的指纹（sha256 的前 8 位）。批完以后文件再改，这次审批就作废。代码计划例外：算哈希时，行首 `-` 或 `*` 后面的勾选框 `[x]`、`[X]` 都当成 `[ ]`，所以只勾步骤不算改。
- 受监管模式必须带哈希；普通模式不带也算，批的是当时的文件。
- 你的消息里只要有一行单独是这句话，就算批准。所以别把 `lean request` 的输出或 AI 的回复原样贴回来提问。

### 3. 每一步做了什么：aidlc-state.md

每做完一个阶段，AI 跑 `lean stage done <id> --note "用了什么、产出什么、关键决定"`。工具把它记进审计日志，再重新生成 `aidlc-state.md` 里两条标记之间的那一段。标记下面的 Session notes（交接说明）归 AI 写。

真实例子（2026-11-08 用脚本模拟跑出来的，阶段日志只留了 4 条）：

```
# AI-DLC State: Refunds within 14 days
Intent: 261108-refunds · Mode: standard · Created: 2026-11-08
<!-- lean:begin progress -->
## Stage progress
- [x] Reverse Engineering — done · 2026-11-08
- [x] Requirements Analysis — approved via INCEPTION (sha 8cf2cbce) · 2026-11-08
- [S] User Stories — skipped: one persona (buyer), one action
- [x] Application Design — approved via INCEPTION (sha 8cf2cbce) · 2026-11-08
- [S] Units Generation — skipped: one unit: a single Python package
- [x] Functional Design (app) — done · 2026-11-08
- [S] NFR Requirements + Design (app) — skipped: no new NFR targets
- [S] Infrastructure Design (app) — skipped: in-process library, no infrastructure
- [x] Code Generation (app) — done · 2026-11-08
- [x] Build and Test — verify PASS · 2026-11-08 04:15 UTC (code fingerprint 99bff36f)
- [x] Release — released: approved (sha dedf0bf7) · 2026-11-08

## Stage log

### Requirements Analysis · 2026-11-08 04:15 UTC · by dev@example.com (team -)
- Did: Inputs: request, 3 answers, architecture.md. Output: Size large, AC-1..3, A-1.
- Outputs: inception/requirements/requirements.md (sha 64d5b2f5)

### User Stories · 2026-11-08 04:15 UTC · by dev@example.com (team -)
- Skipped: one persona (buyer), one action

### Code Generation (app) · 2026-11-08 04:15 UTC · by dev@example.com (team -)
- Did: Inputs: plan, BR-1/BR-2. Output: src/refunds.py, tests/test_refunds.py (AC-1..3).
- Outputs: construction/plans/app-code-generation-plan.md (sha 26f12321)

### Build and Test · 2026-11-08 04:15 UTC · by dev@example.com (team -)
- Did: verify PASS: 1 check on code fingerprint 99bff36f
- Outputs: construction/build-and-test/build-and-test-summary.md (sha 5294818b)
<!-- lean:end progress -->
## Session notes
Status: released (RELEASE approved)
### Next
### Open questions and blockers
### Notes for the next session
```

- 上面是 v0.2 跑出来的。v0.3 的列表多几行：没开构想时，开头多一行 `- [S] Ideation — skipped: not requested (lean new without --ideation)`；Build and Test 后面多一行 CI Pipeline；Release 后面多 7 行运维阶段，整段跳过时只显示一行 `- [S] Operations — skipped: <理由>`。
- 标记：`[x]` 做完，`[S]` 跳过，`[-]` 进行中，`[ ]` 没开始，`[A]` 等人批（口令已经打出来，还没批）。等人批时那一行是这样：`- [A] Requirements Analysis — waiting for approval: approve INCEPTION 8cf2cbce`。人这时打了口令也不会被接受的请求，不给口令，显示成 `[-] ... <种类> requested; the approval waits: <原因>`。比如：用了构想、IDEATION 还没批时的需求请求；`lean release` 现在过不了时的 RELEASE 请求。IDEATION 请求以后又重开了必做的构想阶段，也不给口令（见 1a）；`lean release` 之后又记下别的审批、驳回或阶段记录，RELEASE 也不给口令（见"命令"）。
- 标记之间这一段进 git，所以只看每个 clone 都一样的东西（审计日志和文件），不看这个 clone 自己的状态：同一个提交、同一份日志，哪个 clone 写出来都一样。比如配了 checks、自己却没跑过 verify 的 clone，照样写出 `[A] Release — waiting for approval: approve RELEASE <哈希>`；但在那个 clone 里打这个口令不算（没有对当前代码通过的 verify），它的 `lean status` 会让你先跑 verify。构建测试和发布两行认两种代码：这个 clone 工作区里的，和已经提交的。所以 verify 完马上提交，提交里的这一段就写着 verify 过；某个 clone 多了没提交的文件（比如 Finder 的 .DS_Store）或改动，这一段也不变。工作区有没提交的产品改动时，`lean status` 在这一段外面另起一行 `Working tree: N uncommitted product change(s) (…)`，因为 verify 和 RELEASE 审批只看工作区（提交关卡看的是这次提交带了什么，见下面第 6 步）。
- 审批、驳回和 verify 的结果会自动出现在列表里。阶段日志里也会列出每次审批、驳回和没被接受的口令（哪种、哈希、谁、什么时候）。阶段日志的每一条都写明来源：人在对话里打的标 `human (prompt)`，跑命令记下的标 `via CLI`。
- 做完的阶段后来又改了（页面变了；代码生成阶段只比较计划，勾选不算。代码本身变了会显示在“构建测试”那一行：上次 verify 之后代码又改过），那一行后面会标 `(edited since)`。AI 应该重新跑一次 `lean stage done`，在说明里写改了什么。
- 还有单元的代码生成没做完时，verify 通过了，Build and Test 也只显示为进行中（`[-] ... verify PASS on partial code`）。
- 代码计划做到一半时，`lean status` 的"下一步"会写"continue the code-generation plan of unit <单元>: step N of M"（继续这个单元的计划，第 N 步，共 M 步）。
- 标记之间的内容 AI 改了也没用：下次跑阶段命令、`lean request`、`lean verify`、`lean release`，或者记下一条审批时，这一段会按日志重新生成。`lean status` 也会顺手更新它，比如 git pull 之后。

### 4. 能追溯

- 编号：需求里的验收标准叫 AC-n，用户故事叫 US-n，功能设计里的业务规则叫 BR-n。
- 每个单元的代码计划里有一张表：每条 AC、BR 由哪个测试来证明。
- `build-and-test-summary.md` 记下跑了哪些命令、退出码、耗时、输出的哈希、代码指纹，以及 verify 时所在的提交和工作区状态。verify 常常在提交之前跑，这时会写明"有未提交的改动"：认代码的是指纹，不是提交号。
- 不另装检测工具。

## 去掉了什么

| AI-DLC 原来 | Lean |
|---|---|
| 每个阶段做完都等人确认（v1 的 core-workflow.md 里有 12 处，其中 5 处每个单元都要各过一遍） | 人只在 3 个审批点批（受监管模式加每个单元的 PLAN，用了构想加 IDEATION）；另外开头回答一批问题，失败时停下来问 |
| 每个阶段一份问题文件，在文件里填 `[Answer]:` | 开头把问题一次问完，每题带推荐答案；问答抄进 requirements.md；之后只问卡住的问题 |
| 一个阶段好几份文件（v1 的逆向工程 8 份加一个时间戳文件，应用设计 5 份） | 每个阶段一页 |
| 14 个角色（2.11.3 的产品、架构、开发、测试等智能体） | 没有角色 |
| 每个阶段的评审和总结确认（2.11.3） | 发布前评审一次，由新对话或没写这份代码的子代理来做 |
| 构想、运维每个阶段好几份文件，每个阶段等人批；部署执行由 AI 来做（main） | 两段都可选，每个阶段一页；构想只在交接时批一次 IDEATION，运维不批；AI 不部署 |

## 安装

```bash
./install.sh <你的项目目录>                         # 普通模式
./install.sh <项目> --regulated                     # 受监管
./install.sh <项目> --multi-team --team payments    # 多团队（每个 clone 设自己的团队）
./install.sh <项目> --with-pstack                   # 加装 pstack 质量包（可以和上面的选项一起用）
```

`<项目目录>` 要写在最前面。选项写错（比如 `--regulate`）会直接报错退出，什么都不改；`--team` 后面必须跟团队名；`--help` 看用法。

装完后：

1. 改 `aidlc-docs/lean.json`：
   - `checks`：必须全部通过的命令，比如 `["pytest -q", "ruff check ."]`；
   - `protected_paths`：AI 不能改的验收测试，比如 `["tests/acceptance/**"]`。
2. 把 `.kiro/`、`aidlc-docs/` 和 `.gitignore` 提交进 git。`.aidlc-lean/` 是本机状态，已经自动加进 .gitignore。`.gitignore` 算产品文件：不提交的话，`lean release` 会因为有未提交的改动而拒绝。
3. 在项目目录里运行 `kiro-cli --v3`，问是否信任这个工作区时选信任。
4. Kiro 第一次要运行 `python3 .kiro/aidlc-lean/aidlc_lean.py` 时，选"总是允许"。

依赖：python3（3.8 以上）和 git，macOS 或 Linux。不需要 bun、node，也不需要联网。

`lean.json` 由人改（hook 不让 AI 改）。里面还有：`plan`（每个单元的代码计划要不要批：默认 `auto`，只有受监管模式要批；`always` 是所有模式都要批）、`approvers`（审批人白名单，按审批种类：IDEATION、REQUIREMENTS、DESIGN、INCEPTION、PLAN、RELEASE、CR）、`deny_commands`（禁止的命令，正则；写了就替换默认名单，所以要把 `aidlc_lean.py` 里 `DEFAULT_CONFIG` 的默认几条一起抄上）、`fingerprint_exclude`（不算进代码指纹的路径，比如 `["dist/**"]`；加在默认的 `aidlc-docs/**` 和 `.kiro/**` 之上，这两条总是不算，契约除外）。

**重装和升级**：

- 重跑 install.sh 会更新 kit 文件，`aidlc-docs/`（包括 lean.json）原样保留。脚本、hook、常驻说明和 8 张技能卡是 kit 的，每次整份换新，改了也会被换掉。
- **模板可以改**：`.kiro/aidlc-lean/templates/` 里的模板由人改（hook 不让 AI 改 `.kiro/`），也可以加团队自己的。install.sh 把它装进去的每个模板的 sha256 记在 `.kiro/aidlc-lean/kit-templates.sha256`（下面叫清单），和 `.kiro/` 一起提交。重装时：
  - 没改过的模板换成新版；
  - 人改过的留着，kit 的新版写在旁边的 `<名字>.kit-new`，并打出 "Kept …"。由人对比、合并，再删掉 `.kit-new`。同一个 kit 版本只给一次，清单里记着给过的版本：删掉以后，用同一个 kit 重装不再提；kit 出了这个模板的新版，才再给一次。`.kit-new` 没删之前，每次重装都会重写它；
  - 团队自己加的也留着，打出 "Kept …: the kit does not ship it"；
  - 只差大小写的名字：在不分大小写的文件系统（比如 macOS）上，团队自己的 `CR.md` 和 kit 的 `cr.md` 是同一个文件。`CR.md` 留着，不会被盖掉，kit 的版本写进 `cr.md.kit-new`，也是同一个 kit 版本只给一次（别的只差大小写的名字也一样）；
  - kit 不再发的老模板，没改过的才删（打出 "Removed old kit templates …"）。
- install.sh 先只读、不改：读完模板和清单，定好怎么做，再查它要写的每个文件都写得了（kit 的脚本和模板、hook、常驻说明、技能卡、pstack 包、`aidlc-docs/audit/` 和 `.aidlc-lean/`；还缺 `.aidlc-lean/` 那一行时的 `.gitignore`；多团队时的契约目录）。还没有的文件和目录，查的是离它最近的已有目录能不能写；`aidlc-docs/lean.json` 也要是合法的 JSON。有一条不行，安装就停下，打出 "…; nothing was changed."，真的什么都没改：`git init` 和建目录都还没做。
- 查过以后才动文件。万一后面还是出错（比如磁盘满了，或者 `lean init` 失败），会打出 "install.sh: stopped part way …"：有些 kit 文件可能已经换成新的。把问题修好再跑一次就行，重跑是安全的。
- 清单不是 UTF-8，或者有认不出的行，install.sh 打一条 `note:`，照样读里面的记录，再把清单重写一遍。
- 已经有 lean.json 时再加 `--regulated` 或 `--multi-team`，模式**不会变**，安装脚本会打出 WARNING（直接跑 `lean init --regulated` 也一样）。要改模式，由人改 lean.json 里的 `"regulated"` / `"multi_team"` 并提交；改成多团队后，再带 `--team 名字` 重跑一次，生成 `aidlc-docs/contracts/OWNERS`。
- **从 v0.2 升级**：重跑 install.sh 就行，lean.json 不用改。v0.2 没有 `kit-templates.sha256`，install.sh 认得 v0.2.0 原样的模板；和它不一样的，当成人改过的留着，新版写进 `.kit-new`。v0.2 开的 intent 照常接着做：阶段进度开头多一行 `- [S] Ideation — not used (no Ideation record: the intent was started before AI-DLC Lean 0.3)`，后面多出 CI 流水线和运维几行，用不上就跳过。v0.2 里叫 `ci-pipeline` 的单元照常能用，不用改名：它的页面在 `construction/ci-pipeline/` 下的子目录里，计划在 `construction/plans/` 里，和 CI 流水线阶段的 `construction/ci-pipeline/ci-config.md` 不冲突；受监管模式下，它的 PLAN 关卡也和 v0.2 一样。
- **从 v0.1 升级**（v0.1 的东西都在 `aidlc/` 下）：
  1. install.sh 看到 `aidlc/lean.json` 会停下，什么都不改。
  2. 由人挪配置：`mkdir -p aidlc-docs && git mv aidlc/lean.json aidlc-docs/lean.json`。v0.1 的配置里写着 `"contracts_dir": "aidlc/contracts"`，改成 `aidlc-docs/contracts`（多团队的话把 `aidlc/contracts/` 也挪过去）；自己改过 `fingerprint_exclude` 的，也改成新路径。提交，再跑 install.sh。
  3. install.sh 按 v0.1 才有的模板名认出 v0.1 的安装：没有清单；`templates/` 里至少有一个 v0.1 的名字，大小写也一样（`SPEC.md`、`PLAN.md`、`STATE.md`、`REVIEW.md`、`UNITS.md`、`DECISIONS.md`、`RELEASE.md`、`AUDIT-PACK.md`、`CR.md`）；除了 `lean.json`（v0.1 也有），没有后来版本的名字。认出来以后，这些 v0.1 模板都删掉，`lean.json` 模板换成新版。后来的安装里，叫这些名字的文件算团队自己的，留着。新模板叫 `cr.md`、`decisions.md`，和 v0.1 的 `CR.md`、`DECISIONS.md` 只差大小写。在 macOS 这种不分大小写的文件系统上，git 会接着用旧名字记，Linux 上的同事拿到旧名字，`lean doctor` 会报模板缺失。所以 install.sh 这次删掉的 kit 旧文件里，git 还记着、磁盘上却没有这个名字（大小写也要一样）的，它会从索引里去掉（`git rm --cached`，磁盘上的文件不动），并打出 "Dropped from the git index …"。之后 `git add -A` 就会记成新名字。团队自己加的文件它不删，也不从索引里去掉。
  4. 跑一次 `lean doctor` 和 `lean verify`。v0.1 的 intent、审批和 verify 记录都留在 `aidlc/` 里，v0.2 和 v0.3 都不读；没做完的工作用 `lean new` 重新开。
  5. lean.json 挪走以后，旧的 `aidlc/` 目录不再受保护（AI 能改），而且算进代码指纹（改了它，要重新 verify 才能提交）。要留的东西挪进 `aidlc-docs/`，核对过后删掉旧目录：`git rm -r aidlc`。

**装在大仓库的子目录里**（monorepo）：项目就是放 `.kiro/` 的那个目录。`aidlc-docs/`、审计日志和 .gitignore 里那一行都放在这个目录；kiro-cli 也要在这个目录里启动（v3 引擎只读工作区里的 `.kiro/hooks`）。`checks` 在这个目录里跑，`protected_paths` 和 `contracts_dir` 都相对这个目录写。`contracts_dir` 照写的认，只按字面整理（`./`、多余的斜杠）；可以带 `..`，指到项目旁边共用的契约目录，比如 `../../shared-contracts`。是软链接的目录，链接名和它指向的目录都算契约目录；macOS 上大小写不同也算同一个。`lean doctor` 只在值说不清时报错：空的、`.`（项目目录本身），或者一个不存在的绝对路径（那就当成项目里的路径来读）。

## 一个功能怎么走

`lean` 是 `python3 .kiro/aidlc-lean/aidlc_lean.py` 的简称。人和 AI 都能用 `lean status` 看进度和下一步。

1. 你说要做什么。AI 先读代码，用 `lean new <名字>` 开一个 intent（目录是 `aidlc-docs/<yymmdd>-<名字>/`，日期按 UTC，和页面里的 Created 一样）。老代码先做逆向工程，新项目跳过。产品经理要先把想法理清楚的，用 `lean new <名字> --ideation`：先走构想，批了 IDEATION 再到这一步（见 1a）。
2. AI 把问题**一次**问完，每题带推荐答案。你可以回"都按推荐"，或者只改几条。问答抄进 requirements.md；AI 猜的部分写成"假设"（A-1……），你让 AI 自己定的也写成假设，不算你的回答。
3. AI 写 requirements.md：大小（把模板里占位的 `Size: <small|large>` 改成 `small` 或 `large`；新的公开模块或接口、新的数据模型、改 schema 或接口、跨好几个模块，都算 `large`）、目标、不做什么、验收标准（AC-1……）、非功能指标、假设。需要时再写用户故事、应用设计、拆分单元。每做完一个阶段跑 `lean stage done`，用不上的阶段跑 `lean stage skip`。这些都不停下来问你。
4. AI 跑 `lean request INCEPTION`，把口令给你，比如 `approve INCEPTION 8cf2cbce`。你读需求和设计两页，同意就自己打这一行。想先定需求，就先批 REQUIREMENTS，设计写完再批 DESIGN。每次停下来等你之前（问问题、要审批），AI 都要先更新 Session notes；Session notes 还是模板原样时，`lean request` 会提醒它。
5. 一个单元一个单元地做（没拆单元就只有 `app`）：
   - 按需写功能设计、非功能设计、基础设施设计，用不上就跳过并写理由；
   - `lean stage start code-generation` 生成代码计划：第 1 步是一条最细的、能从头跑到尾的路（带一个能过的测试），每一步写清覆盖哪些 AC/BR、怎样算做完；
   - 受监管模式：`lean request PLAN --unit <单元>`，你批了才能写这个单元的代码；
   - 按计划一步步写代码和测试，每做完一步就在计划里勾上（`[x]`，批过的计划也照样勾）。步骤全勾完才能跑 `lean stage done code-generation`，还有没勾的它会拒绝。
6. AI 跑 `lean verify`：执行 `checks` 里的命令，写 build-and-test-summary.md。配了 checks 时，没有对当前代码通过的 verify，`git commit` 会被拦住。verify 要单独跑一条命令，别和 `git commit` 串在一起。只带 `aidlc-docs/` 或 `.kiro/` 下文件的提交不用 verify（契约文件除外，它们算在代码指纹里），工作区里还有没暂存的产品改动也一样：比如代码做到一半，先 `git add aidlc-docs/ && git commit -m ...` 提交 Session notes。hook 看这次提交带了什么：已经暂存的，加上同一行里 `git add <路径>` 要加的。看不准时（`git commit -a`、`git add -A`、命令行里有 `cd` 或 `$(...)`），按整个工作区算。
7. 评审要由没写这份代码的上下文来做：新开一个对话（`/chat new`），或者交给没写代码的子代理（pstack 的多模型评审也是子代理）。用 `--resume` 接着聊的老对话不算新的上下文。结果写进 `construction/build-and-test/review.md`。review.md 比最近一次 verify 和代码改动都新时，`lean status` 的"下一步"就指向 `lean release`；所以修完评审意见、重新 verify 之后，要在 review.md 里补上修了什么。
8. AI 跑 `lean release` 写 operations/release.md（审批表里，被后来的审批取代的旧审批会标出来），补上"Open items"（没解决的问题、已知缺口、后续工作），再跑 `lean request RELEASE`。还有没提交的产品代码改动时，`lean release` 会拒绝，要先提交。你打 `approve RELEASE <哈希>`。release.md 的审批表里少了一条它该列的审批（按表里每一行的格子比，空格多少不算；注释里、表外面写的不算），这份 release.md 就作废了：该列的是这个 intent 的审批和所有 CR 的审批，比如需求改了又重新批了，或者别的团队批了一个 CR（不管批的时候哪个 intent 是当前的、在哪个 clone 里批的、那台机器的时钟准不准）。这时要重新 `lean release`、重新请求，旧口令不再算。这一条按审批表的内容比，不按时间。批完这个 intent 就关了：只有它的运维页面和 ci-pipeline 还能改、还接受阶段命令；之后的设计改动、后续工作和修 bug 都用 `lean new` 开新的。`lean status` 和会话开头注入的状态都会写明它已发布（RELEASED）。
9. 可选：CI 流水线和运维的页面（见 1a），在 `lean release` 之前记好，或者等 RELEASE 批了以后再记，AI 不部署。用不上就 `lean stage skip ci-pipeline --reason "..."`、`lean stage skip operations --reason "..."`。

小改动（改错别字、改一个配置值、一个文件里的小修）不用开 intent，直接改；当前 intent 已经发布时也一样。受监管模式除外。

## 命令

```
lean init [--regulated] [--multi-team] [--team NAME]  在项目里建 aidlc-docs/（install.sh 会调用它）
lean new <slug> [--title T] [--ideation]             开一个 intent，并设为当前 intent（--ideation：先走构想）
lean use <intent>                                    切换当前 intent（记进日志）
lean status                                          当前进度和下一步（顺手更新 aidlc-state.md 里生成的那段）
lean stage start <id> [--unit U]                     按模板生成这个阶段的文档，标成进行中
lean stage done <id> [--unit U] --note "<内容>"      记下这个阶段做了什么
lean stage skip <id> [--unit U] --reason "<理由>"    记下为什么跳过
lean stage skip ideation|operations --reason "<理由>"
                                                     整段跳过还没有记录的构想或运维阶段（运维不含 ci-pipeline）
lean request IDEATION|REQUIREMENTS|DESIGN|INCEPTION|PLAN [--unit U]|RELEASE|CR-<team>-<n>
                                                     打出给人的审批口令
lean verify                                          跑 checks，写 build-and-test-summary.md（受监管模式另写证据文件）
lean cr new <slug> --owner TEAM --paths a,b          开一个契约变更申请（CR）
lean cr close <id> --reason "<理由>"                 关闭一个 CR（申请方或契约方都能关），之后它不再放行任何改动
lean release                                         审批和 verify 都齐了，写 operations/release.md
lean audit verify | lean audit pack [intent]         查审计日志的哈希链 / 写 aidlc-docs/<intent>/audit.md
lean doctor                                          检查安装
```

- `stage done` 在文档还没写、或者还是模板原样时会拒绝。
- 发布以后，只有运维阶段和 ci-pipeline 还接受 `stage` 命令。
- `request RELEASE` 只在 `lean release` 现在能通过、release.md 是 `lean release` 为当前代码写的、而且写完以后没有再记下别的审批或驳回（RELEASE 自己的不算）、也没有再记下阶段记录（构建测试和发布自己的不算）时才给口令。人打的 `approve RELEASE` 也按同样的条件查：比如这时 IDEATION 或需求过期了、被驳回了，或者又重新批过了，这条审批不算，日志里记一条 APPROVAL_REFUSED。这时阶段进度里那一行不给口令：过期或驳回时是 `[-] Release — RELEASE requested; the approval waits: not ready to release: ...`；重新批过以后是 ``[-] Release — release.md (written <日期>) does not list <种类> approved: run `release` again``，要重新 `lean release`（新的 release.md 会列上新的审批），再请求。记下了新的阶段记录时是 ``[-] Release — release.md (written <日期>) is older than <阶段> <skipped|done|started>: run `release` again``，同样要重新 `lean release`。RELEASE 自己被驳回不算：没改代码的话，同一份 release.md 照人的意见改好，就能再请求。

## hook 会拦的事

hook 是 Kiro 在会话开始、你发消息、AI 调用工具前自动跑的脚本。下面这些情况它会查，查到就拦下，并告诉 AI 原因（`[AI-DLC Lean] blocked (<关卡>): ...`）：

| 情况 | 结果 | 关卡 |
|---|---|---|
| 用了构想阶段，IDEATION 还没批（或被驳回）就写代码；受监管模式下，批过的构想页又改了也算 | 拦住 | ideation |
| 有当前 intent，需求还没批就写代码 | 拦住 | requirements |
| 设计没批，也没按 `Size: small` 跳过，就写代码 | 拦住 | design |
| 受监管模式：这个单元的代码计划没批，就写它的代码 | 拦住 | plan |
| 受监管模式：批过的页面后来又改了（在批过的计划里只勾步骤不算改，改步骤的文字算） | 拦住，要重新批 | requirements / design / plan / ideation |
| 受监管模式：没有当前 intent 就改代码 | 拦住 | intent |
| 受监管模式：当前 intent 已经发布，还要改代码 | 拦住，要开新 intent | released |
| 改验收测试（`protected_paths`） | 拦住；你打出 `allow test change` 后放行，直到你下一次发言（同一个 clone 里的所有会话和子代理都放行） | protected |
| 配了 checks，但没有对当前代码通过的 verify，还要提交 | 拦住 | verify |
| 受监管模式：没配 checks 就提交 | 拦住 | verify |
| 禁止名单里的命令：默认只有几条（`git push --force`、`rm -rf /`、`terraform apply`、`kubectl apply`、`kubectl delete`、删表等），团队在 lean.json 的 `deny_commands` 里加 | 拦住，需要的话由人自己执行。名单很短，管不住所有部署："AI 不部署"靠的是规则和团队的权限（见 1a） | danger |
| AI 改审计日志、本机状态、`aidlc-docs/lean.json`、契约 OWNERS、`.kiro` 里的 kit，或者改工具写的文件（build-and-test-summary.md、证据文件、audit.md）。只读的不拦：读文件工具，和只做读的 shell 命令（见表下第一条） | 拦住 | records |
| 多团队：改别的团队的契约，但没有对方批过、还没关闭、由你们团队提的 CR | 拦住 | contract |

- 只读的 shell 命令读审计日志、本机状态和 `aidlc-docs/lean.json`，不拦（v0.3.1 修的误拦：2026-11-09 的对比测试里，几乎每次都有一次 `cat aidlc-docs/lean.json` 被拦，AI 也就看不到审批人名单）。条件是这一行里每一段命令都只是读：`cat`、`head`、`tail`、`wc`、`ls`、`grep`、`jq`、`stat`、`diff`、`echo`、`cd` 等，除了从文件读入、`2>/dev/null` 和 `2>&1` 没有重定向；或者是 `git status/log/show/diff` 这类只看不改的 git 命令；或者是 `lean` 本身（参数里不写记录的路径）。用别的程序读（`sed`、`awk`、`find`、`python3`），接到别的程序上（`| python3 -c`、`| xargs`、`| tee`），往这些文件里写，或者这一行带 `$(...)`、here-document，照旧拦：改用读文件工具或 `lean status`。
- 普通模式下，批过的页面又改了，写代码不拦，`lean status` 会标成 stale（过期）；但 `lean release` 要求审批都对得上现在的文件。
- 普通模式下，当前 intent 发布以后，就当没有当前 intent：写代码不拦，小改动照常做；新的功能和后续修改用 `lean new` 开新 intent。已经发布的 intent 只有运维阶段和 ci-pipeline 还接受阶段命令，别的阶段命令都拒绝。
- 写 `aidlc-docs/` 里的页面、`*.md` 和 `docs/**` 不受审批限制。契约文件除外（`contracts_dir` 下的文件，默认 `aidlc-docs/contracts/`，不含 OWNERS 和 `changes/` 里的 CR）：它们算代码，和代码一样过上面这些关卡（用了构想先等 IDEATION，再等需求和设计；受监管模式下要有 intent 和所属单元的 PLAN）。多团队时，改别的团队的契约还要先有对方批过的 CR；改自己团队的契约只是不用 CR。
- hook 认不全所有写法：AI 用 shell 或别的工具，还是能绕开其中一些检查。最后兜底的是提交前的 verify、发布前的审批和 verify 检查，以及 Git 服务器上的保护分支和 MR 审批。
- 被拦下的调用一般都会记进审计日志（`aidlc-docs/lean.json` 写坏时例外：照样拦，但记不进去）。子代理用文件工具写代码，同样会被拦（v0.1 实测过）。

## 三种场景

**受监管**（`--regulated`）：

- 改代码前必须先有 intent；当前 intent 发布以后，改代码也会被拦，要先 `lean new`；
- 审批口令必须带哈希；
- 批过的页面再改，审批就失效，写代码会被拦，要重新批；
- 每个单元的代码计划要批（PLAN）。批过的计划照样勾步骤，审批不失效；改了步骤的文字要重新批；
- 用了构想阶段，IDEATION 也要批，而且要对得上现在的构想页面，才能批需求、写代码；运维段在受监管模式下也是可选的；
- 没配 `checks` 时，不能提交，也不能 `lean release`；
- hook 脚本自己出错时，工具调用一律拦下，不放行；
- verify 另写证据文件（`construction/build-and-test/evidence/verify-<时间>.md`），日志里记下它的 sha256；
- 证据里常见的密码和密钥写法会打码：名字里带 password（或 passwd、pwd）、secret、token、api_key、access_key、private_key、credential 的键值（比如 `DB_PASSWORD=…`、`"password": "…"`）、Authorization / Bearer 头、URL 里的 `用户:密码@`、GitHub / AWS（AKIA、ASIA）/ Slack 令牌、私钥块。没有明显名字或前缀的密码打不了码，所以别让 checks 打印密码；
- `lean audit pack` 写 `aidlc-docs/<intent>/audit.md`：日志完整性、各阶段记录、审批和驳回（包括没被接受的口令）、verify（带证据文件哈希的前 12 位）、被拦记录、放行过的验收测试修改、CR、intent 切换、会话。只收这个 intent 自己的事件和 CR；会话和子代理只收它从创建到发布这段时间里的。人在对话里打的审批标成 `human (prompt)`，通过命令行记下的（AI 跑的阶段命令、verify、release 等）标成 `via CLI`，hook 自己记的（会话开始、子代理启动等）标成 `hook (...)`，一眼能分清谁做了什么；
- 受监管模式下，所有改动都要走 intent，人自己的改动也一样（最后由 Git 服务器的 MR 审批把关）。AI 不会建议你"自己直接改一下"，只会提议开一个新 intent。

可以配置审批人白名单（按 git 邮箱），比如 `"approvers": {"RELEASE": ["lead@corp.com"], "IDEATION": ["pm@corp.com"]}`。INCEPTION 除了自己的名单，还要过 REQUIREMENTS 和 DESIGN 的名单；v0.1 写的 `SPEC` 名单仍然管需求和设计的审批。

**多团队**（`--multi-team --team X`）：

- 每个 clone（每人本机的一份仓库）由人设自己的团队：`lean init --team <名字>`，或者环境变量 `AIDLC_LEAN_TEAM`。名字照写的保存，可以带 `-`、`.`，也可以用中文；比较团队时 `-`、`.` 和 `_` 算一样（`web-team` 和 `web_team` 是同一个团队），CR 编号里写成 `_`（`CR-web_team-1`）；
- `inception/application-design/unit-of-work.md` 列出每个单元：名字、归哪个团队、代码路径、依赖谁、用到哪些契约。每个团队在自己的 clone 里做自己的单元。`lean status` 的"下一步"只提本团队的单元，轮到别的团队时会说在等哪个单元；
- `aidlc-docs/contracts/OWNERS` 写明每个契约归哪个团队，由人维护；
- 每个 intent 有一个归属团队（Owner team，就是发起它的团队），写在 aidlc-state.md 开头。评审和发布由它来做；别的团队做完自己的单元推上去就行。产品经理用 `--ideation` 开的 intent，由人把那一行改成负责发布的团队；
- Session notes 每个团队一段：`### Next (team <名字>)`，里面是这个团队的状态、下一步和卡点，各改各的，不会互相覆盖。新开对话时，hook 先注入本团队那一段；
- 要改别的团队的契约，先 `lean cr new`，填好推上去；对方团队在**自己的 clone** 里跑 `lean request CR-...` 并批准；你 pull 下来之后，hook 才放行改那个契约。只放行提出申请的团队，只放行 CR 里列的文件，只到 CR 关闭为止：对方把改动做完后，用 `lean cr close <编号> --reason "..."` 关掉（两个团队都能关）。改自己团队的契约不用 CR；
- 契约文件算代码：和代码一样要等审批才能写（受监管模式下还要所属单元的 PLAN），所以在 unit-of-work.md 里把契约路径写进所属单元的 Paths 列；审批前的契约草稿写在 application-design.md 里。改了契约，要重新 verify 才能提交和发布；
- 两个 clone 合并时，工具生成的内容（aidlc-state.md 里生成的那段、build-and-test-summary.md）可能冲突。跑一次 `lean verify` 会把两处都按日志重写；冲突跨到生成段外面（Session notes）的，外面那部分留成一块完整的冲突（`<<<<<<<` 到 `>>>>>>>`），手工合并、删掉标记再提交。冲突标记对不上（比如只剩 `=======` 和 `>>>>>>>`）时，工具不改这个文件，只提示先手工修好。审计日志每个 clone 一个文件，不会冲突；
- 代码归属和合并审批交给 GitLab 的 CODEOWNERS 和 MR 审批，kit 只管契约。

**跨多天**：

- `aidlc-state.md` 进 git，是交接单：上半段是工具生成的阶段进度和阶段日志，下半段是 AI 写的 Session notes（现在的状态、下一步、卡在哪、给下次会话的提醒）；
- 新开会话时，hook 会把 Session notes 里"下一步"的头几条和阶段进度注入给 AI（"下一步"在前，太长时先截掉阶段进度）。最多 40 行、4,000 字符，再多就截断，并提示用 `lean status` 看全；
- 同一个对话隔了 4 小时以上再说话，会重新注入一次，提醒先 pull。按对话算，别的对话在忙不影响；
- 回到老对话：`kiro-cli chat --resume` 打开的是这个目录里**最新**的对话。要回到更早的一个，用 `kiro-cli chat --resume-id <会话号>`（`kiro-cli chat --list-sessions` 能列出会话号）。接着用的老对话记得自己写过的代码，不算新的上下文，不能拿来做发布前的评审；
- AI 改了 25 次代码还没更新 aidlc-state.md，hook 会提醒它更新；Session notes 还是模板原样时，`lean request` 打出口令时也会提醒它先更新；
- 换人或换团队接手（包括产品经理批完 IDEATION 后交给开发团队）：对方运行 `lean use <intent>`（写目录全名或日期后面的名字都行，会记进日志）就能接着做。审批、阶段记录和 verify 结果都随 git 里的审计日志一起过去。提交前要在自己的 clone 里重跑一次 verify，因为 verify 的结果只对当时那份代码有效。

## 可选：pstack 质量包（`--with-pstack`）

`./install.sh <项目> --with-pstack` 会多装一套"代码质量"卡片。它改编自 Lauren Tan 的 [pstack](https://github.com/cursor/plugins/tree/main/pstack) 0.15.32（MIT 协议，署名保留在每张卡末尾和 `.kiro/aidlc-lean/LICENSE-pstack`；以后不带 `--with-pstack` 重装，这个许可文件也会留着）。Lean 管流程和关卡，这套卡管代码写得好不好、验证做得实不实。

- **8 张原则卡和工具卡**：
  - 做完前先在真东西上跑一遍；
  - 测试测行为，不测实现；
  - 校验和权限放在系统边界；
  - 修根因；
  - 拆成能单独验证的小步；
  - 先把数据模型想清楚；
  - 改之前查清会影响到哪（blast-radius）；
  - 同一类错误出现两次，就改成工具强制拦住（correct）。
- **`pstack-interrogate`（多模型对抗评审）**：同时派 `lean-reviewer-opus`（Claude Opus 5.5）和 `lean-reviewer-k3`（Kimi K3）两个评审，主代理汇总进 `construction/build-and-test/review.md`，分成"必须改 / 可以考虑 / 记下 / 驳回"四类，另有一节"Out-of-design changes"：主代理自己对照设计，列出设计里没有的接口、字段或行为改动（有没有对应的决策记录），没有就写 none。
  - 派单只写一次：主代理把意图、完整 diff、验收标准表、评审要点（rubric）和代码质量要点写进 `construction/build-and-test/review-brief.md`，再在**一条消息**里给两个评审各发一句短提示，指向这个文件。这样两个评审应该能同时开始（还没在 Kiro 里重跑验证），派单内容也留了记录（和 review.md 一起提交）。
  - 两个评审是**只读的**：卡片里写的是 `tools: ["read"]`，只能读和搜文件，不能跑命令，也不能写文件。主代理把 diff 和测试输出写进派单文件；评审要确认什么，就写出命令，由主代理去跑。
- **`pstack-swarm`（并行子代理）**：最多 5 个，用于老代码调研、多模型检查、找茬测试。共用的派单同样写进一个文件（`construction/swarm/brief.md`），每个子代理只收一句短提示：文件路径加上它自己那一块。并行写代码只交给 `lean-worker`，而且要先用 unit-of-work.md 或代码计划给每个 worker 分好不重叠的文件。
- **常驻部分只多一页对照说明**（144 词），告诉 AI 在哪个阶段用哪张卡。其余都是用到才加载：10 张卡 4,498 词，interrogate 的参考文件 2,279 词，3 张子代理卡 470 词。

已在 kiro-cli 3.1.0 上实测（2026-11-07，v0.1，详见 [docs/e2e-2026-11-07.md](docs/e2e-2026-11-07.md)）：

- 子代理会用 `.kiro/agents/*.md` 里 `model:` 指定的模型：探针里 claude-opus-5.5、gpt-5.6-terra、kimi-k3 三个子代理，Kiro 自己的子任务记录里的模型都对得上；
- 一条消息里派出的多个子代理会并行跑，但 Kiro 要等一次调用的内容全部写出来，才启动那个子代理。探针的提示很短，三个几乎同时开始；11-08 那次每个评审的提示里都塞了 37 KB 的派单，第二个评审晚了 69 秒才开始。所以现在派单写进文件，提示只写一句；
- 子代理的工具调用同样会经过工作区的 hook。

多模型评审 v0.1 真跑过一次，用的是 **Opus 5.5 + GPT-5.6 Terra**，两个评审当时还有 shell，自己跑了 git 和测试。两个模型各自独立指出了同一个 bug：金额特别大时 `line_total` 会抛异常（`line_total(10**30, 1)` 报 `decimal.InvalidOperation`）。主代理用 Kimi K3 写的 9 个单元测试没测出这个问题。

现在默认发的是 **Opus 5.5 + Kimi K3**，评审是只读的。2026-11-08 在 Kiro 里真跑过一次（老代码 ShopFlow 加商品评价，见 [docs/e2e-2026-11-08-scenarios.md](docs/e2e-2026-11-08-scenarios.md)）：

- Kiro 的子任务记录里，两个评审的模型分别是 claude-opus-5.5 和 kimi-k3；
- 两个评审只用了读文件和搜索（共 7 次 read_file、6 次 grep_search），没写文件，也没跑命令；
- Opus 提了 10 条，K3 提了 8 条。主代理归出 8 条"必须改"：其中 4 条两个模型都提了，3 条只有 K3 提了。8 条都修掉，重新 verify 后提交；
- 那次派单还是直接塞在提示里，两个评审只重叠了 44 秒；派单写文件是这之后改的，还没在 Kiro 里重跑。

如果主会话也用 K3，K3 评审和写代码的是同一个模型，主要靠 Opus 提供不同视角。

评审模型写在 `.kiro/agents/lean-reviewer-*.md` 里，客户的 Kiro 装了别的模型就由人来改（hook 不让 AI 改这些文件）。重装时，人改过 `model:` 的卡会保留，并打出 "Kept …"；只会删掉旧版的 `lean-reviewer-gpt.md`，团队自己的其他 `.kiro/agents/lean-*.md` 不动。

pstack 升级后，重新生成这套卡：

```bash
python3 tools/vendor_pstack.py                 # 用 ~/.claude/plugins/cache/cursor-plugins/pstack/ 下最新的版本
python3 tools/vendor_pstack.py <pstack 目录>   # 或者指定一个 pstack 目录
```

卡末尾的版本号从那个目录的 plugin.json 读。任何一项检查没过，`kit-pstack/` 保持原样：上游文字变了、改编对不上的地方一次全部列出；这些都对上以后，生成的卡再整体检查一遍，问题也一次列出。

## 测过什么

- **单元测试**：`python3 -W error::ResourceWarning -m unittest discover -s tests`，共 291 个。2026-11-10 在 Python 3.9.6 和 3.12.15 上各跑一遍，290 个全部通过，没有跳过（机器负载很高，各约 53 和 44 分钟）；之后加的 1 个（`fingerprint_exclude` 的默认值）单独跑过。又让依赖 Lean 的 brain-kit 用这份代码跑了它用到 Lean 的 13 个测试文件：py3.12 上 384 个全部通过；py3.9 上 381 个里有 1 个失败（brain-kit 读 `DEFAULT_CONFIG` 里 `fingerprint_exclude` 的默认值，0.3.1 一度把它清空了），改回以后那一组通过。

  | 文件 | 个数 |
  |---|---|
  | `test_aidlc_lean.py` | 30 |
  | `test_fixes_script.py` | 32 |
  | `test_fixes_install.py` | 32 |
  | `test_v02_stages.py` | 34 |
  | `test_v02_integration.py` | 12 |
  | `test_v02_live_fixes.py` | 22 |
  | `test_v03_phases.py`（v0.3 的构想、CI 流水线、运维段） | 25 |
  | `test_v03_qa_fixes.py`（v0.3 四轮 QA 找到的逻辑问题，包括契约算代码） | 46 |
  | `test_v03_install_fixes.py`（重装时留下人改过和团队加的模板，`.kit-new` 只给一次，清单或模板读不了时） | 18 |
  | `test_v031_fixes.py`（v0.3.1：review 第 1 轮 R1-106..120、只读 shell 不再误拦、v0.3 实测后的修复） | 40 |

  覆盖：每道关卡（包括 v0.3 的 ideation）、审批规则（包括 IDEATION 的哈希、过期、驳回、白名单）、阶段命令和阶段记录、整段跳过构想和运维、发布后的运维阶段、每个单元的 PLAN、篡改可检测、多团队的单元和 CR、契约和代码一样等审批、发布流程、pstack 质量包、安装和从 v0.1 升级、重装时留下团队改过和自己加的模板、并行 hook、子目录安装、打码。还查了说明文字本身：常驻说明、技能卡和模板里提到的每条命令、每个关卡名都真的存在，字数没超（常驻说明不超过 1,000 词，8 张核心技能卡每张不超过 600 词；pstack 包的卡不设上限）。本机没有 pstack 0.15.32 源码时，其中 7 个 vendor_pstack 测试会跳过（这次没跳过）。Python 3.8 没有真跑过（本机没有 3.8），只按 3.8 的语法检查过。
- **v0.2 的模拟跑**（2026-11-08）：没开 kiro-cli，也没有真的 AI。脚本按 Kiro v3 hook 的格式，把"AI"的每次写文件、跑命令和"人"发的每条消息都喂给 hook，走完了 4 个场景：普通模式、普通模式加 pstack、受监管（两个单元、每个单元批 PLAN、有一次驳回）、多团队（两个 clone、一个 CR、一次合并冲突）。上面 aidlc-state.md 的例子就是这样跑出来的。
- **真机测试 v0.1**：kiro-cli 3.1.0（v3 引擎）+ Kimi K3，2026-11-07，在沙箱里跑了 8 轮对话。确认了这些：
  - 3 个 hook 都会触发，AI 能看到注入的状态；
  - AI 按流程写需求文档（v0.1 叫 SPEC），并主动交出审批口令；
  - 你说"直接干吧"它不会写代码；让它直接写，hook 当场拦下，记为 BLOCKED；
  - 打出审批口令后：写代码 → verify 通过 → 提交成功；
  - 让它改验收测试，它拒绝了；
  - 子代理写文件也会被拦；
  - 发布审批、审计日志哈希链校验、审计包都正常。

  经过和数字见 [docs/e2e-2026-11-07.md](docs/e2e-2026-11-07.md)。
- **真机测试 v0.2**：kiro-cli 3.1.0 + Kimi K3，2026-11-08，在沙箱里跑了 5 个场景，都走到了 RELEASED，`audit verify` 都是 OK：
  - 普通模式：小需求，人只发了 3 条消息、批了 2 次，见 [docs/e2e-2026-11-08-v0.2.md](docs/e2e-2026-11-08-v0.2.md)；
  - 受监管：不带哈希的批准被拒，每个单元批 PLAN，中途加一条验收标准后重批，verify 写证据文件，`audit pack` 正常；
  - 多团队：两个 clone 通过一个 bare 仓库 push/pull，走完了 CR 流程（开 CR、对方团队批、pull 后放行）；
  - 跨多天：新开对话从计划第 2 步接着做（换了一个人），隔 5 小时再回到老对话做完发布；
  - 老代码 + pstack：先做逆向工程，Opus 5.5 + K3 两个只读评审。

  后四个的经过、发现的问题和这一轮改了哪些，见 [docs/e2e-2026-11-08-scenarios.md](docs/e2e-2026-11-08-scenarios.md)。
- **说清楚**：
  - 这几轮里 K3 从没试过走被拦的捷径（"先写代码，回头再批""发布后不走流程小改一下"都拒绝了），所以大部分关卡在真机上没真正触发过。v0.2 真机上被拦过的只有 verify（普通模式那次把 verify 和 commit 串成一条命令）、protected（改受保护的契约测试，人打 `allow test change` 后放行）、records（一次误拦：用 shell 列审计目录）和 contract（按人的要求故意去改别的团队的契约）。requirements、design、plan、released、intent、danger 这些关卡靠单元测试覆盖。
  - 11-08 实测之后这一轮的修复（子代理的任务说明不再算人的发言、CR 只给申请的团队放行并且能关闭、计划做到一半时的提示、派单写进文件等）只有单元测试，还没在 Kiro 里重跑。
  - **v0.3.1 的修复**（设计说明 §10：review 第 1 轮的 15 条、只读 shell 命令不再误拦、v0.3 实测后的 7 处修复）只有单元测试，还没在 Kiro 里重跑。
  - **v0.3 的构想段（IDEATION 审批、`ideation` 关卡）、CI 流水线和运维段只有单元测试**，没做模拟跑，也没在 Kiro 里真跑过。上面的真机测试都是 v0.2。两张新技能卡写给产品经理和运维用，AI 照着它们能不能把页面写好、会不会编数字，还没验证过。
  - **环境**：这几轮用的是测试人自己的 Kiro 配置。默认 agent 是测试人平时用的那个，它自己的 hook、记忆和全局 steering 也进了会话，K3 评审那次也加载了。沙箱允许 Kiro 读 `~/.kiro`，用户级的 agent、hook 和 MCP 都会加载。要公平地测，请用干净的 Kiro 配置（单独的 HOME），或者指定一个不带用户 hook、记忆和 MCP 的 agent。

## 已知限制（说清楚）

- **验收测试的保护和 verify 的比对都只做了一部分。** hook 认不全所有改文件的写法，verify 的比对也有查不到的情况。
  - 你自己加或改了验收测试，verify 会判失败（它拿需求批准那一刻的验收测试作对照）。确认没问题后，让 AI 跑 `lean request REQUIREMENTS`，你再批一次，verify 就以现在的文件为准。
- **审计日志的哈希链**能查出中间某一行被改或被删。删掉末尾几行、删掉某个 clone 的整份日志或者整份重写，它查不出来，要靠 git 历史和保护分支。`audit verify` 不重算证据文件的哈希（日志里记着它的 sha256，可以人工比对）。
- **审批人身份是本机自报的**（git 邮箱、系统用户、主机名）。真正的身份要靠 Git 服务器和公司账号。
- **经过 KiroCrew 或 Brain 桥接时**，桥接注入的文字会被当成人说的话。所以受监管模式要求审批带哈希。桥接方要自己核实是谁批的，并在审批行后面带上 `(via 飞书 张三 msg-123)`，Lean 会把它记成"声称的渠道"。
- **`Size` 是 AI 填的。** 需求页模板里是占位的 `Size: <small|large>`，AI 按规则改成 `small` 或 `large`；还是占位时就当不是 small，应用设计不能跳。你批需求时看一眼这一行。
- **阶段顺序和阶段记录不强制。** hook 只管审批、verify 和受保护的文件。漏记一个阶段不会被拦，只会在 `lean status` 和 release.md 里显示 `[ ]`；`lean status` 的"下一步"会按 AI-DLC 的顺序提醒。
- **运维段只是记录。** 发布不等运维页面，RELEASE 也不管它们的内容；部署记录、压测结果、SLO 结果是 AI 照人和流水线给的事实填的，工具不核对真部署过没有。"AI 不部署"是写给 AI 的规则，禁止名单很短，挡不住所有部署命令。真正部署和回滚的控制在团队的 CI/CD 和权限上。
- **代码计划只认一种勾选框**：PLAN 的哈希只把行首 `-` 或 `*` 后面的 `[x]`、`[X]` 当成 `[ ]`。别的写法（比如 `1. [x]`）勾了也算改，PLAN 审批会失效。
- **RELEASE 只认 `lean release` 为当前代码写的 release.md。** 代码一改，要重新 verify、重新 `lean release`、重新批；`lean release` 之后（RELEASE 批准以前）又记下别的审批、驳回或阶段记录，也要重新 `lean release`、重新批。在另一个 clone 里批 RELEASE，那边的代码要完全一样（同一个提交，没有本地改动）；配了 checks 时，那边还要先跑通一次 verify（verify 只在跑它的那个 clone 里算数）。那边的阶段进度照样显示 `[A]`（见第 3 节），`lean status` 会提示先跑 verify。
- **契约文件和代码一样等审批。** 不管单团队还是多团队，`aidlc-docs/contracts/` 下的契约（OWNERS 和 `changes/` 里的 CR 除外）都算代码：要等 IDEATION（用了构想时）、需求和设计批了才能写，受监管模式下还要有 intent 和所属单元的 PLAN；没写进任何单元 Paths 的契约，受监管模式下要等所有 PLAN 都批了。审批前想先起草契约，写在 application-design.md 里。
- **阶段日志按记录的先后排。** 多团队时两个团队的条目会穿插在一起；上面的阶段进度列表按 AI-DLC 的顺序排。
- **单元别叫 `swarm`**：pstack 的并行子代理把报告写在 `construction/swarm/` 下，会和这个单元的目录混在一起。
- **会误拦的情况**：
  - Kiro 的 `code` 工具（查符号这类读操作）和写到仓库外面的文件（比如 `/tmp` 里），在需求和设计批准前可能被当成写代码拦下；
  - 用 `sed`、`awk`、`find`、`python3` 这类程序读记录文件，或者把读到的内容接给别的程序（比如 `| python3 -c`），还是会被拦，改用读文件工具或 `lean status`。`cat`、`head`、`tail`、`grep`、`jq`、`ls` 这类只读的命令从 v0.3.1 起不拦（见"hook 会拦的事"）；
  - `aidlc-docs/lean.json` 写坏了（不是合法 JSON）时，所有工具调用都会被拦，而且记不进日志。
- **只在 Kiro CLI 的 v3 引擎上测过**（用 `kiro-cli --v3` 启动）。v2 引擎用的是另一套 hook 配置（agent JSON），这里没有适配。
- **Windows 还不支持**：那里的关卡可能悄悄失效。请用 macOS 或 Linux，或者在 WSL 里用 Linux 版的 Kiro。
- **还没实测的**：
  - 多台机器（11-08 的多团队测试是同一台机器上的两个 clone）；
  - 大型老系统（11-08 的老代码场景是一个小的 FastAPI 应用）；
  - 大部分关卡在真机上被触发的情况（见上面"说清楚"）；
  - 11-08 实测之后这一轮的修复，包括派单写进文件后两个评审是不是真的同时开始；
  - v0.3 的构想、CI 流水线和运维段；
  - v0.3.1 的修复。
- **大仓库**：算代码指纹时借用 git 的索引缓存，只重读改过的文件；没进 git 的文件，第一次要整个读一遍。2026-11-08 在 5 万个文件的仓库上测 v0.2（Apple M3 Pro，机器同时在跑别的任务）：有当前 intent 时会话开始约 0.6 秒，提交检查约 0.3 秒；删掉 `.aidlc-lean/` 里的指纹缓存后，第一次会话开始约 0.8 秒。

## 目录

```
install.sh                                安装到项目
kit/.kiro/steering/aidlc-lean.md          常驻规则（999 词）
kit/.kiro/skills/aidlc-lean-*/            8 张按需加载的技能卡：ideation、inception、construction、release、operations、resume、multi-team、regulated（共 4,784 词）
kit/.kiro/hooks/aidlc-lean-*.json         3 个 v3 hook
kit/.kiro/aidlc-lean/aidlc_lean.py        唯一的脚本（4,434 行）
kit/.kiro/aidlc-lean/templates/           28 个模板（共 5,484 词）：24 个阶段文档（v0.2 的 9 个，加 v0.3 构想 7 个、CI 流水线 1 个、运维 7 个），加 aidlc-state.md、decisions.md、cr.md、lean.json
tests/                                    单元测试（10 个文件，291 个）
docs/design-v0.2.md                       v0.2 的设计说明（§9 是 v0.3 的构想、CI 流水线和运维段，§10 是 v0.3.1 的修复）
docs/e2e-2026-11-07.md                    v0.1 的真机测试记录（摘要）
docs/e2e-2026-11-08-v0.2.md               v0.2 的真机测试：普通模式
docs/e2e-2026-11-08-scenarios.md          v0.2 的真机测试：受监管、多团队、跨多天、老代码 + pstack
COMPARISON.md                             和 2.11.3 Express / Enterprise 的对比
kit-pstack/                               可选的 pstack 质量包（10 张卡、3 个子代理、MIT 许可）
tools/vendor_pstack.py                    从 pstack 源码重新生成 kit-pstack/
```
