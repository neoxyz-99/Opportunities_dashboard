# 国际会议与学术机会雷达

这是一个面向个人机会拓展的监测项目，用来及时发现国际会议、国际组织青年机会、fellowship、internship、summer school、policy school、学术年会、CFP 和 workshop。

项目目标不是替你过度筛选，而是先尽量全面收集与你关心议题相关的机会，再用结构化字段帮你快速判断是否值得报名、投稿或长期关注。

## 基本定位

- 核心形式：表格数据库 + 网页仪表盘
- 默认语言：全球中英双语
- 收集策略：信息覆盖优先，轻分类，保留原网页链接
- 重点议题：可持续发展、发展、不平等、AI 治理、气候治理、金融、债务、全球治理、国际组织
- 重点机会：国际会议、青年项目、学术 CFP、fellowship、policy fellowship、visiting fellowship、internship、summer school
- 低优先级议题：粮食安全、人口、公共卫生等，除非它们明确连接到发展、不平等、气候、债务、金融或全球治理

## 第一版包含什么

- `04-数据库/机会数据库.csv`：机会主数据库。
- `00-自动化/collect_opportunities.py`：联网搜索、结构化提取、去重入库、生成极简摘要邮件。
- `00-自动化/generate_dashboard.py`：生成 `docs/index.html` 网页仪表盘。
- `00-自动化/send_email.py`：仅用于发送可选的极简邮件提醒。
- `00-自动化/validate_opportunities.py`：用 40 条以上样例验证字段、链接、相关度、仪表盘分类和 internship 筛选逻辑。
- `.github/workflows/opportunity-radar.yml`：支持定时监测、手动运行和每周汇总。

## 去重机制

系统已经有去重机制：

- 优先使用 `原网页链接` 生成链接指纹。
- 如果原网页链接缺失，则使用 `申请/投稿链接`。
- 如果两个链接都缺失，才用 `主办方 + 机会名称` 作为兜底指纹。
- 已入库机会再次出现时，不重复新增，只更新最近核查日期和更完整的信息。
- 已提醒过的机会会进入 `05-历史记录/已提醒链接.csv`，即时提醒不会重复发送同一条。

## 邮件展示原则

网页仪表盘是主入口。它会优先突出：

- 主题
- 截止时间
- 项目/会议日期
- 地点/形式
- 材料
- 要求
- 个人匹配度
- 投入判断

费用和资助信息仍保留在数据库中，但不作为主视图的主要展示模块。邮件默认不发送长列表，只在手动勾选时发送极简摘要和仪表盘链接。

## Internship 监测规则

Internship 已作为核心机会类型加入监测。

重点来源：

- UN Careers
- UNDP
- UNESCO
- UNIDO
- UNEP
- UNCTAD
- UN-Habitat
- OECD
- World Bank
- ADB

保留方向：

- 政策研究
- 项目支持
- 可持续发展
- 治理
- 发展融资
- 气候
- AI/数字治理
- 传播倡导
- 伙伴关系
- 战略研究

默认排除或降级：

- 城市规划
- 法律
- HR/人力资源
- IT/软件/数据工程
- 财务/会计
- 采购
- 行政后勤
- 医学
- 工程技术

## 数据字段

每条机会至少记录：

- 机会名称
- 机会类型
- 主办方
- 议题标签
- 相关度
- 截止日期
- 会议日期
- 地点/线上
- 原网页链接
- 申请/投稿链接
- 参加条件
- 费用
- 是否有资助
- 资助说明链接
- 需要准备的材料
- 机会类型分组
- 主题分区
- 岗位类型
- 岗位职能
- 排除原因
- 行动优先级
- 状态
- 备注

系统会额外维护：

- 发现日期
- 最近核查日期
- 链接指纹

## 运行方式

安装依赖：

```bash
pip install -r requirements.txt
```

生成一次机会提醒：

```bash
python3 00-自动化/collect_opportunities.py --mode instant
```

生成网页仪表盘：

```bash
python3 00-自动化/generate_dashboard.py
```

生成每周汇总：

```bash
python3 00-自动化/collect_opportunities.py --mode weekly
```

发送生成的 HTML 邮件：

```bash
python3 00-自动化/send_email.py 06-邮件输出/生成的文件.html
```

验证样例：

```bash
python3 00-自动化/validate_opportunities.py 04-模板/30条样例机会.csv
```

## 配置

复制配置样例并填写：

- `07-配置/api.env.example` -> `07-配置/api.env`
- `07-配置/email.env.example` -> `07-配置/email.env`

真实密钥不要上传到公开仓库。GitHub Actions 运行时需要配置 Secrets：

- `OPENAI_API_KEY`
- `RESEND_API_KEY`
- `MAIL_FROM`
- `MAIL_TO`

可选：

- `MAIL_REPLY_TO`
- `OPENAI_MODEL`
- `DASHBOARD_URL`：GitHub Pages 仪表盘地址，用于极简邮件里的跳转链接

GitHub Pages 建议设置为从 `docs/` 目录发布。
