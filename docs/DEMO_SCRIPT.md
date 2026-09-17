# CareerPilot AI — 两分钟演示脚本

使用 README 中的合成账号运行 Docker Demo。浏览器建议保持 1440×1000 左右，可将 `docs/images/` 中的截图作为补充画面。

## 0:00–0:15 — 问题

“Many LLM job matchers return an impressive score but cannot show which resume evidence supports a
claim. CareerPilot separates verified evidence, deterministic requirements, semantic relevance,
and hard eligibility risks.”

## 0:15–0:35 — 简历证据

打开 **简历** 和匿名 Demo 简历，展示结构化状态、不可变版本和字段级证据。说明真实环境可使用 OpenAI-compatible DeepSeek Provider，公开 Docker Demo 使用 Mock 模式。

## 0:35–0:50 — 结构化岗位输入

打开 **岗位** 并选择 **AI Product Intern**。指出匹配路径消费的是结构化岗位表示：必需技能、加分技能、学历、语言和任职资格。生产路径不依赖 AI Job Parser。

## 0:50–1:15 — 匹配流程

选择已确认的简历版本和 **混合匹配**。启动流程并展示 LangGraph 节点：输入校验、确定性匹配、语义检索、阻断风险检查、报告保存和人工确认。说明冻结的 70/30 策略：规则是主信号，语义相关性只是辅助信号。

## 1:15–1:45 — 可解释报告

打开报告并依次展示：

1. 综合匹配度与推荐上限。
2. 规则分、语义分和综合分。
3. 证据覆盖率与语义辅助证据。
4. 六个评分维度。
5. 带来源证据的已匹配技能与技能缺口。
6. 与普通技能缺口分开呈现的阻断风险。

Use the sentence: “A semantic hit can prioritize a requirement, but it cannot prove a capability
or override a blocking conflict.”

## 1:45–2:00 — 收尾

“The project is intentionally honest about scope: the core is real resume parsing, structured job
input, deterministic and hybrid matching, explainable reports, and application tracking. Dify is
optional, evaluation data is synthetic, and the holdout limitations remain visible.”

作品集演示不要展示 `.env`、API Key、私有上传文件、调试日志、隐藏实验模块或 Docker 安装细节。
