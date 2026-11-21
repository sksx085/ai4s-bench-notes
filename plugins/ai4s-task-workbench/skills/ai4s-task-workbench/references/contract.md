# 本地命令和题目规格

运行 `python3 -B scripts/workbench.py --help`。换成 skill 下脚本的实际路径。读写 JSON 均为 UTF-8。科学和作答条件还在确定时，先生成骨架，再按实际进度逐次填写。

| 命令 | 产物 |
| --- | --- |
| `init DIR --id NAME --title TITLE` | 新目录内的 `challenge.json`、组织方 `review.json` 和三栏草稿预览 |
| `init DIR --id NAME --title TITLE --legacy-brief PATH --root ROOT` | 新审题规格，指向共同根目录内已有的 Markdown |
| `brief SPEC` | 生成三栏选手题面。加 `--add background` 或 `--add diagnostics` 展开对应内容 |
| `audit SPEC` | JSON 核查记录，包含约束缺口、评分方式、来源摘要和科学待核项 |
| `freeze SPEC NEW_DIR` | 独立 `participant/` 和摘要文件 `snapshot.json` |
| `check-submission ANSWER_DIR --spec SPEC` | 按当前规格检查答卷。也可用 `--snapshot FROZEN_DIR` 检查同一份冻结输入 |
| `replay SPEC ANSWER_DIR` | 显式调用已审阅的本地 Python 评分器，记录真实输出和相关摘要 |
| `judge-packet SPEC ANSWER.md [...]` | 把明确指定的文本提交改用序号标记，和公开题面、量表封存在同一份 JSON |
| `judge-template PACKET --id TAG --kind human` | 生成一份独立评阅表，`--kind model` 表示模型评阅 |
| `reconcile PACKET FIRST SECOND` | 按项核对两个评审的分歧和一致率 |

默认以规格所在目录解析材料路径。审旧题时，用 `--root` 指定包含新目录和旧材料的共同根目录，从 `init` 到后续命令都传这个值。旧题模式的 `init` 未指定根时，以当前目录为共同根目录。参数 `SPEC` 仍指向实际规格。来源路径写相对于根目录的文件名。`init` 和 `freeze` 创建指定的新目录，已有目录必须另选名字。`brief` 可将标准输出保存到任意文件。新题中 `participant/challenge.md` 是初始预览，编辑 `challenge.json` 再生成预览。

## challenge.json 的最小字段

`schema_version` 为 1。`task_id` 是稳定 ID，`revision` 由作者确定。`sections` 的字段按需填写。生成题面时，`goal` 和 `input` 进入「问题」，`output` 和 `completion` 进入「解答」，`constraints` 和 `scoring` 进入「约束」。提交精度写入交付契约。实验或算法容差写入评分正文。`overview`、`background` 用于解释性背景，必须知道的术语定义写入 `goal` 或 `input`。

生成版默认展示主评分，诊断项可用 `--add diagnostics` 展开。`brief`、`audit`、`freeze`、`judge-packet` 都接受同样的 `--add` 选项。对照试测只改一项补充内容，发卷用相应选项分别冻结并比较材料清单。接入的旧 Markdown 可直接复用原文。要对照其精简版，先把必需内容登记到同一组契约字段，再让 `public.brief` 留空以生成新版。

- `public.brief` 留空时生成题面，有值时以已有 Markdown 为准。`public.files` 将选手看到的相对路径映射到原材料路径，每个文件明确登记。包括各轮实际公开的数据和代码。旧版还要人工核对小标题、结论提示、文件引用以及字段约束是否与规格一致。
- `constraints.network` 取 `offline`、`allowed` 或 `undecided`，`allowed`、`forbidden` 列出可用和禁用的工具与证据。时间、内存或硬件限制只写任务确实采用的额度，放进正文。
- `submission` 每项给 `path`、`description`、布尔 `required`、`format`。支持 `file`（检查可读与非空）、`json`（验证 JSON 可解析）和 `csv`。CSV 另给有序 `columns`（`name`、`description`、`type`；数值列另给 `unit`，可带 `min` 和 `max`）、文本 `key` 列和可选 `keys_from`。数值列可用 `decimal_places` 明确最多几位小数。键对应公开 CSV 时，程序核对整张题单的覆盖、重复和未知项。任务特有的结构、格式版本及跨列约束可沿用已有校验器实现。
- `assessment.criteria` 每项给 `id`、`description` 和 `role`（`primary` 或 `diagnostic`）。`method: rule` 另给 `rule`、`unit`、`direction`（`min`、`max` 或 `report`）；`method: rubric` 另给 `levels`，用等级 ID 对应具体可观察的描述。整体和主指标的评分方式分别报告。
- `assessment.scorer` 可关联已有 Python 文件，`score_args` 逐项写原工作流参数，用 `{submission}` 指明答卷目录。脚本和数据依赖可以补在 `score_dependencies`。`replay` 先校验提交，再按原评分器接口读 JSON。它记录已登记的公开和私有输入摘要，并检查运行期间的变化。运行外部文件前确认它是已审阅的本地评分器，评测环境需落实题面的文件和网络隔离。

## 组织方记录

`review` 指向组织方 JSON。`reference_policy: measured-only` 用于真实实验任务，`declared` 用于任务明确允许其他参考的情况。`evidence` 每条含 `id`、`kind`（`measured`、`derived`、`simulation`、`document`）、`path`、`locator`，`derived` 给出 `parents`。`target_evidence` 指向定义实际评分参考的条目。实测限定的参考必须最终追到测量记录。

`claims` 分别记录 `id`、`claim`、`verdict`（`supported`、`limited`、`open`、`refuted`）、`evidence`、`reason`，后三种另填 `next_check`。`baselines` 引用实际留下的运行，以 `name`、`method`、`criterion`、`value`、`evidence` 登记。可用 `value_from` 给出 JSON 原记录的证据 ID 和有序键，启用数值对照。`checks` 记录实际读表、评分复放或评审等核查，包含 `area`（`science`、`scorer`、`rubric`、`isolation`）、`result`、`description`、`evidence`。`private_files` 列出隐藏答案等文件，工具会对比它们与公开文件的摘要。

## 作答及盲评

冻结输出使用明确登记的文件。评测进程仅可读其 `participant/`、指定工具与可写答卷目录。带授权的署名文件可随分发物提供，实际盲测评估其公开范围。哈希可核对文件字节一致性，数据本身是否能指认已发表答案仍要审查。

盲评前查看选定文本中的模型姓名、路径或自我介绍，按协议处理可识别信息。评审各自领取同一份 JSON，独立填等级、理由和答卷中的原句。对证据缺失的判断可用 `quote: null`，并写明检查结果。程序要求两份记录对应同一摘要、覆盖相同题卷和判据，且引用能从提交中找到。遇到分歧交给预先指定的评审流程。若需验证量表的准确性，使用独立专家判定的典型与边界案例。
