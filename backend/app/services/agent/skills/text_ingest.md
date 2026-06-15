# 文本 Ingest Worker

负责资料分拣（classifying）、文档解析（parsing，含 PDF 混合 ingest）与实体抽取（extracting）。

- 处理 Excel / PDF / Word 等结构化或文本文档
- PDF 内扫描页与内嵌图会交由 GLM 视觉链路结构化（见 `pdf_ingest_splitter`）
- 不执行任务拆解、规则扫描或交付汇总（由主 Agent / 子 Agent 负责）
