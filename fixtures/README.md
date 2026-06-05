# 测试样例说明

上传以下文件到同一项目，可验证跨文件比对：

| 文件 | 预期风险 |
|------|---------|
| sample_expense.csv | 大额缺发票、招待费无票 |
| sample_invoice_list.csv | 重复发票 INV001、B公司金额与费用不匹配 |
| sample_bank_statement.csv | 个人账户收款、超大额、摘要空 |
| sample_contract.docx | 合同与发票累计金额不一致 |
| sample_trial_balance.xlsx | 科目余额检查 |

跨期：`sample_expense.csv` 第6行业务日期2024-12-20，入账2025-01-10。
