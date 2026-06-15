# AuditAgent · 设计假设（原型阶段）

> 采集日期：2026-06-09  
> 场景：B2B 会议合规远程观察 · 子会议工作台（分析运行中）  
> 用户诉求：流线型科技风，去掉「假赛博」装饰

## 核心资产

- Logo：原型内用 SVG 流线透镜 mark（待产品定稿后可替换 `/favicon.svg`）
- UI 参考：现有 FXPG 信息架构（侧栏 → 项目 → 子会议 → 资料/Finding/交付）

## 气质关键词

- 专业 · 可信 · 流线 · 克制 · 实时

## 禁区

- 扫描线 / Glitch / 切角 bracket / 霓虹脉冲 / 六边形 HUD
- 紫粉 AI 渐变 · emoji 图标 · 三列等宽卡片套路

## 当前主题 · 沉降（已落地）

- CSS：`globals.css` token + `settling-theme.css` 全站覆盖
- 字体：Syne + IBM Plex Mono
- 会议概览：`SettlingStage` 大字阶进度
- 会议子页：`MeetingRunStrip` + `PageTop` 标题
- 侧栏：`ProjectRail` 四步流程 + 子页导航
- 已移除：`streamline-theme.css`、HUD 顶栏挂载

原型参考：`design/auditagent-aesthetic.html` · I · 沉降
