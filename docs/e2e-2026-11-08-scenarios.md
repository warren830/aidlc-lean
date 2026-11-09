# v0.2 实测：四个场景（2026-11-08）

同一天先跑了普通模式（见 [e2e-2026-11-08-v0.2.md](e2e-2026-11-08-v0.2.md)），之后又跑了这四个：受监管、多团队、跨多天、老代码 + pstack。四个场景同时在跑，各用各的沙箱。

## 共同的环境

- kiro-cli 3.1.0（v3 引擎），主模型 Kimi K3。每个场景一个沙箱和一个新项目，都在测试机的 `/private/tmp/lean-live/` 下（临时目录，可能已经清掉）。
- 由测试代理按脚本扮演"人"发消息、查结果，不改 kit。测的是这一轮修复之前的 v0.2。
- 环境有干扰：用的是测试人自己的 Kiro 配置，默认 agent 是测试人平时用的那个。它自己的 hook、记忆和全局 steering 也进了会话，子代理也加载了。沙箱允许 Kiro 读 `~/.kiro`，用户级的 agent、hook 和 MCP 都会加载。下次测要用干净的配置（单独的 HOME，或者指定一个不带这些的 agent）。

下面"本轮"一列：**已改** 是这一轮（实测之后）的修改，分三种：脚本、文档（常驻说明、技能卡、README）、质量包。这些修改都只有单元测试，还没在 Kiro 里重跑。**没改** 是还留着的问题。

## 1. 受监管（`--regulated`）

**准备**：一个小 Python 包，给 `src/pricing.py` 加 `apply_coupon(total_cents, coupon)`：百分比券四舍五入到分，满减券不让总价变负，无效的券报 ValueError。checks 是 unittest，`protected_paths` 是 `tests/acceptance/**`。

**对话和审批**：人发了 9 条消息，都在同一个对话里（第 1 条新开，后面 `--resume`）。

- 先打了一条不带哈希的 `approve INCEPTION`，被拒，AI 没写代码；
- 然后批了 INCEPTION 和 PLAN；
- 只让做计划第 1 步，做完再加一条验收标准（券面值为 0 也算无效）。AI 自己改了需求、功能设计、计划和决策，重新申请 INCEPTION 和 PLAN，人在一条消息里两个一起批；
- 最后批 RELEASE。
- 一共批了 5 次：INCEPTION 2 次，PLAN 2 次，RELEASE 1 次。

**走通的**：

- 不带哈希的批准被拒；带哈希的都记下了，一条消息两行口令也行。
- 写代码前先批 PLAN；勾步骤不影响 PLAN，改了步骤文字就过期。改了批过的需求，审批就过期（用 kit 自己的检查确认，写代码会被拦）。
- verify 写了证据文件，sha256 记进日志、summary 和 audit.md。verify 和提交分开跑，提交检查一次过。
- 发布、RELEASE 审批、`audit verify`、`audit pack` 都正常。最后 4 个提交，14 个测试全过，日志 41 条，链完好。
- AI 三次拒绝走捷径：没带哈希的批准、"先写代码，回头再批"、发布后"小改一下不用走流程"。

**被拦**：0 次。AI 从没试过被禁止的写法，所以写代码的关卡在真机上没触发。

**问题和本轮**：

| 问题 | 本轮 |
|---|---|
| Kiro 内置的评审子代理启动时，会用父对话的会话号再触发会话开始和发言的 hook。kit 把 AI 写给子代理的任务说明（1,717 个字符）记成了人的发言，还重置了轮次和 `allow test change`；里面要是有审批口令，也会被当成人批的 | 已改（脚本）：子代理的任务说明不再算人的发言 |
| 被拒的批准（没带哈希等）在日志里没有记录 | 已改（脚本）：记 APPROVAL_REFUSED，带原因 |
| 需求过期时，关卡提示没管"审批申请已经发出去了"，可能让 AI 重复申请 | 没改（脚本）；construction 技能卡加了一句"申请已经发出就等" |
| build-and-test-summary.md 的 commit 行是 verify 时的 HEAD，那时代码还没提交 | 已改（脚本）：写基准提交和工作区状态 |
| release.md 的审批表里，被取代的旧审批没标出来 | 已改（脚本） |
| 做完的功能设计后来改了，只显示 `(edited since)`，没人提醒重新记录 | 已改（文档）：construction 技能卡写明要重新 `stage done`，写清改了什么 |
| 人让 AI 把推荐答案写成假设，AI 却在问答里写"A: as recommended"，像是人回答过 | 已改（文档）：inception 技能卡写明只记人给的答案，交给 AI 定的算假设 |
| 发布后 AI 拒绝了不走流程的小改，却建议人"自己直接改" | 已改（文档）：regulated 技能卡写明不建议绕开流程，只提议开新 intent |
| 三步合在一次提交里；申请 INCEPTION 时 decisions.md 还是模板 | 没改（模型问题） |
| 金额特别大时 `apply_coupon` 抛 `decimal.InvalidOperation`，不是 ValueError；评审只把它记成 Info | 已改（文档）：release 技能卡的检查表加了"边界值和特别大的输入" |

**时间**：9 轮 Kiro 合计约 12 分钟（139、14、90、40、69、14、250、54、23 秒）。整个测试（含准备和检查）约 31 分钟。

## 2. 多团队（`--multi-team`）

**准备**：一个 bare 仓库，两个 clone：clone-catalog（team catalog）和 clone-payments（team payments）。OWNERS：`contracts/payments/**` 归 payments，`contracts/catalog/**` 归 catalog。需求是商品上显示"可退款"标志，要在 payments 的收据契约里加 `refundable` 字段，所以要走 CR。

**对话和审批**：9 轮，catalog 5 轮，payments 4 轮（含发布后 1 轮额外探针）。

- catalog 批 INCEPTION；
- payments 的人批 CR-catalog-1；
- payments 那边的人打了一次 `allow test change`；
- catalog 批 RELEASE。

**走通的**：

- 每个 clone 有自己的团队和自己的日志文件；每次 pull 都是快进，日志不冲突。
- unit-of-work.md 拆出 payments、catalog 两个单元，各归各的团队。"下一步"只提本团队的单元，轮到别人时会说在等哪个单元。
- CR 全流程：catalog 用 `lean cr new` 开 CR；payments pull 后 `lean status` 显示有 CR 在等；payments 的 AI 审了 CR 并打出口令，人批准，日志记下批准人的团队；catalog pull 后再改 payments 的契约就不拦了。
- 验收测试保护：payments 改受保护的契约测试被拦，AI 停下来要 `allow test change`，人打了才放行，记 PROTECTED_CHANGE。
- 契约关卡（探针）：payments 去改 catalog 的契约被拦，提示里有完整的 `cr new` 命令，AI 没有绕。
- 发布后两个 clone 都显示 RELEASED；两边 `audit verify` 都 OK（3 个日志文件）。
- AI 拒绝了"CR 批之前先改对方的契约"；发布前的评审子代理发现了一处超出 CR 范围的契约改动。

**被拦**：3 次，都对：protected（验收测试）、records（用 shell `ls` 审计目录，已知的误拦）、contract（探针）。

**问题和本轮**：

| 问题 | 本轮 |
|---|---|
| 子代理的任务说明被记成人的发言（同受监管第 1 条） | 已改（脚本） |
| 批过的 CR 对整个契约文件永久放行：不看是不是申请的团队，也没法关闭。catalog 后来在 payments 的契约里加了一节 CR 里没有的内容，没被拦，只有评审发现了 | 已改（脚本）：只给申请的团队放行，`lean cr close <编号> --reason` 关掉后失效（两个团队都能关）。已改（文档）：multi-team 技能卡写明只改 CR 里写的内容 |
| 两个团队共用一段 Session notes，互相覆盖，交接内容丢了 | 已改（脚本、文档）：每个团队一段 `### Next (team <名字>)`，只改自己的，会话开始先注入本团队的 |
| pull 之后，阶段进度里 Build and Test 因为另一个 clone 的 verify 显示 [x]，"下一步"却让跑 verify | 没改 |
| audit pack 把 intent 开始前的事件（准备时的 verify）也算进来 | 已改（脚本）：audit pack 只取这个 intent 自己的事件，会话只取它从创建到发布这段时间的 |
| "下一步"没说哪个团队发布，两个 clone 都被指向 `lean release` | 已改（脚本、文档）：aidlc-state.md 开头写 Owner team，由它发布 |
| 只改记录的提交本来不用 verify，常驻说明却写每次提交都要。AI 在只改文档的提交前跑了 verify，还没写代码就记了一条 Build and Test 完成 | 已改（文档）：常驻说明和 construction 技能卡写明只改 `aidlc-docs/` 或 `.kiro/`（契约除外）的提交不用 verify。已改（脚本）：代码生成没做完时，Build and Test 只显示为进行中 |
| `lean release` 在有未提交改动时照样把 HEAD 写成 commit，AI 只好提交后再跑一次 | 已改（脚本）：有未提交的产品代码改动时拒绝 |
| 已经配好的 clone 再跑 `lean init --team X`，还是提示去设 checks | 已修：`init` 只确认团队切换；checks 或 protected_paths 还空着时才提醒。install.sh 自己的提示没改 |
| payments 的 AI 说"CR 批准放开了我们自己契约的关卡"，其实自己团队的契约从来不用 CR | 已改（文档）：multi-team 技能卡写明了 |
| 问问题前没更新 Session notes；K3 往 architecture.md 里写了多余的 `</content>`（自己发现并删了） | Session notes：已改（脚本、文档），inception 技能卡写明每次停下前更新，`lean request` 也会提醒。`</content>`：没改 |

**时间**：9 轮 Kiro 合计约 25 分钟（每轮 24-403 秒）。整个测试约 43 分钟。

## 3. 跨多天（普通模式）

**准备**：一个小 Python 包，新写 `src/cart.py`：加、删、改数量、合计（按行四舍五入，整单百分比折扣），金额用整数分，非法输入报 ValueError。对话 1 做 Inception 和计划第 1 步；新开对话 2，git 身份换成第二个人，接着做；再把对话 1 的时间往回调 5 小时，用 `--resume-id` 回到对话 1 做完发布（直接 `--resume` 会打开对话 2）。

**对话和审批**：8 轮。对话 1 做了 4 轮，对话 2 做了 1 轮，回到对话 1 又做了 3 轮。

- INCEPTION 先驳回一次（新的公开类和数据模型，AI 却写了 Size: small），改好后批准；
- RELEASE 先驳回一次（金额特别大时 `Cart.totals` 抛 `decimal.InvalidOperation`），修好后批准。

**走通的**：

- 对话 1 停下前把交接说明写具体了。新对话开头注入了状态，"下一步"在前；对话 2 从计划第 2 步接着做，没重做 Inception，也没要审批。
- 回到对话 1 时注入了"Resumed after 5 h"，AI 发现第二个人已经做完第 2、3 步。
- 两次驳回都记下了。Size 改成 large 后，应用设计不能再跳过，要写出来重新申请。
- 发布被驳回后：修 bug、加测试、重新 verify、重新 `lean release`、新哈希，再批。
- Code Generation 和它的 verify 记在第二个人名下，其余记在第一个人名下。
- `audit verify` OK（46 条），`doctor` OK，最后 10 个测试全过。

**被拦**：0 次（没有触发关卡，也没有误拦）。

**问题和本轮**：

| 问题 | 本轮 |
|---|---|
| 计划只做了第 1 步、verify 通过后，"下一步"就说去记 Code Generation、准备发布；`stage done code-generation` 也接受还有没勾步骤的计划 | 已改（脚本）：做到一半时提示"step N of M"，还有没勾的步骤时 `stage done code-generation` 拒绝；代码生成没做完时，Build and Test 只显示为进行中（verify PASS on partial code）。已改（文档）：construction 技能卡写明每做完一步就勾，全勾完才 `stage done` |
| 子代理的任务说明被记成人的发言（同上） | 已改（脚本） |
| 发布被驳回、计划和代码都改了以后，Code Generation 那一行没显示 `(edited since)` | 已改（脚本） |
| 回到老对话的 AI 把"在新会话里评审"理解成"我现在就是新会话"（后来自己纠正，改用子代理） | 已改（脚本、文档）：措辞改成"在新对话里，或由没写这份代码的子代理评审"；resume 和 release 技能卡写明接着用的老对话不算新的上下文 |
| 阶段日志里还留着被驳回的旧需求记录；审批和驳回不出现在阶段日志里 | 已改（脚本）：阶段日志列出审批、驳回和没被接受的口令 |
| 回到老对话要用 `--resume-id`，直接 `--resume` 会打开最新的对话；文档没写 | 已改（文档）：resume 技能卡和 README |
| 只有一行太长被截短时，也显示"(truncated; …)" | 没改 |
| 新的公开模块和数据模型，AI 却写了 Size: small | 已改（文档）：inception 技能卡写明新的公开模块或接口、新数据模型、改 schema 或接口、跨好几个模块都算 large |
| Inception 期间 Session notes 和 decisions.md 一直是模板 | Session notes：已改（脚本、文档）。decisions.md：没改 |
| 新对话没看 git log 就开始写，两步合一次提交；回到老对话时没 pull | 部分改（文档）：resume 技能卡写明可能有人推过就先 pull |
| 评审子代理没发现大金额时 `Cart.totals` 崩溃 | 已改（文档）：release 检查表加了边界值和特别大的输入 |

**时间**：8 轮 Kiro 合计约 13 分钟（每轮 38-208 秒）。整个测试约 35 分钟。

## 4. 老代码 + pstack 质量包（`--with-pstack`）

**准备**：复制 ShopFlow 的 `main.py` 和 `static/`（FastAPI 后端 + 单页前端），原样不改；加了 README、`pytest.ini` 和 5 个冒烟测试（`tests/acceptance/`，受保护）。系统自带的 python3 3.9.6 已经有 fastapi、httpx、uvicorn、pytest。checks 是 pytest。需求是商品评价：买过的客户打 1-5 星，可以写评论；商品列表显示平均分和条数；运营可以隐藏评价。

**对话和审批**：6 轮，2 个对话（第 4 轮新开对话做评审）。批了 INCEPTION 和 RELEASE 各 1 次。

**走通的**：

- 老代码先做逆向工程，architecture.md 写了真实路径和风险（受保护的冒烟测试意味着接口只能加字段）。
- 一批问题带推荐答案；Size: large，写了用户故事和应用设计。
- 功能设计；非功能和基础设施设计跳过并写了理由；6 步计划，第 1 步是骨架；14 个新测试。verify 都单独跑，提交检查没拦过。
- pstack：在对应阶段加载了 5 张原则卡（model-the-domain、sequence-verifiable-units、boundary-discipline、test-behavior-not-implementation、prove-it-works）。
- 多模型评审：Kiro 的子任务记录里，两个评审的模型是 claude-opus-5.5 和 kimi-k3。两个评审只用了读文件和搜索（7 次 read_file、6 次 grep_search），没写文件，也没跑命令。Opus 提了 10 条，K3 提了 8 条；主代理归出 8 条"必须改"，其中 4 条两个模型都提了，3 条只有 K3 提了。8 条都修掉，重新 verify 后提交。
- 批完 RELEASE，intent 关闭，工作区干净。`audit verify` OK（36 条）。AI 起的本地服务只绑在 127.0.0.1。

**被拦**：0 次。

**问题和本轮**：

| 问题 | 本轮 |
|---|---|
| pstack-interrogate 让主代理在一条消息里派两个评审，但每个提示里都塞了 37 KB 的派单。Kiro 要等一次调用的内容全部写出来才启动子代理，结果 K3 晚了 69 秒才开始，两个只重叠了 44 秒 | 已改（质量包）：派单只写一次，存成 `construction/build-and-test/review-brief.md`，两个评审各收一句指向它的短提示；pstack-swarm 也一样（`construction/swarm/brief.md`） |
| 写完 review.md 以后，`lean status` 还让去评审 | 已改（脚本）：有 review.md 后提示 `lean release` |
| build-and-test-summary.md 的 commit 行（同受监管第 4 条） | 已改（脚本） |
| Inception 期间 Session notes 一直是模板（同上） | 已改（脚本、文档） |
| 写代码的 AI 在公开接口里加了设计里没有的 `can_review` 字段，也没记决策；两个评审和主代理都没发现 | 已改（质量包）：review.md 要有一节"Out-of-design changes"，主代理对照设计逐条列出 |
| review.md 写的测试数（15）不对，实际 19 个 | 没改（小问题） |
| aidlc-lean-inception 和 pstack-blast-radius 两张卡没被加载 | 没改 |
| 阶段日志和 audit.md 里，AI 记的阶段、verify、发布和人打的审批是同一个身份，分不清谁做了什么 | 已改（脚本）：分别标 `human (prompt)` 和 `via CLI` |
| `lean new` 先记了一次 requirements 开始，AI 后来又记了一次 | 没改（小问题） |
| 沙箱允许 AI 写 `/tmp`（它在那里放了一个脚本和日志） | 测试环境的事，不在 kit 里改 |
| README 的"还没实测"还列着 K3 评审和只读评审 | 已改（文档） |

**时间**：6 轮 Kiro 合计约 29 分钟（62、127、504、927、71、37 秒；第 4 轮多模型评审加修复最长，约 15 分钟）。整个测试约 45 分钟。

## 小结

- 四个场景（加上之前的普通模式）都走到了 RELEASED，`audit verify` 全部 OK。
- K3 很守规矩：没试过任何被禁止的捷径。所以多数关卡没在真机上触发：受监管、跨多天、老代码三个场景都是 0 次被拦；多团队 3 次（protected、一次 records 误拦、一次按要求故意试的 contract）。关卡本身靠单元测试覆盖。
- 最大的问题是 Kiro 3.1.0 对子代理也触发会话开始和发言的 hook。受监管、多团队、跨多天三个场景都碰到了，用的都是 Kiro 内置的评审子代理；老代码场景用的是 pstack 的两个评审子代理，日志里没有多出来的记录。本轮已改，但还没在 Kiro 里重跑。
