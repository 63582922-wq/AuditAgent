import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Rule


def seed_rules(db: Session) -> None:
    rules_dir = Path(__file__).resolve().parents[2] / "rules"
    all_items: list[dict] = []
    for path in sorted(rules_dir.glob("*_rules.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            all_items.extend(data)

    existing = {r.rule_id for r in db.query(Rule.rule_id).all()}
    for item in all_items:
        if item["rule_id"] in existing:
            continue
        db.add(
            Rule(
                rule_id=item["rule_id"],
                rule_name=item["rule_name"],
                risk_category=item["risk_category"],
                risk_level=item["risk_level"],
                applicable_document_type=item["applicable_document_type"],
                condition_json=item["condition"],
                evidence_fields=item.get("evidence_fields", []),
                suggestion_template=item["suggestion_template"],
                manual_review_required=item.get("manual_review_required", False),
                priority=item.get("priority", 100),
            )
        )
    db.commit()


def seed_memories(db: Session) -> None:
    from app.models import Memory
    from app.services.embedding_service import embed_memory_content

    rules_dir = Path(__file__).resolve().parents[2] / "rules"
    knowledge_path = rules_dir / "knowledge_seed.json"
    extra: list[dict] = []
    if knowledge_path.exists():
        extra = json.loads(knowledge_path.read_text(encoding="utf-8"))

    existing_contents = {m.content for m in db.query(Memory.content).all()}
    defaults = [
        {
            "memory_type": "user_preference",
            "content": "用户偏好报告简洁、实务导向，高风险问题优先展示。",
            "tags": ["report_style"],
        },
        {
            "memory_type": "risk_policy",
            "content": "咨询服务费金额超过10000元时，原则上需要合同、发票、付款记录三方匹配。",
            "tags": ["expense", "consulting_fee", "税务风险"],
        },
        {
            "memory_type": "report_template",
            "content": "PDF 报告应包含：项目概况、资料清单、风险汇总、主要问题、详细风险清单、整改建议、补充资料清单。",
            "tags": ["pdf_report"],
        },
        {
            "memory_type": "accounting_knowledge",
            "content": "费用税前扣除通常需要真实、合法、有效的凭证作为支持。",
            "tags": ["税务风险", "expense"],
        },
        {
            "memory_type": "accounting_knowledge",
            "content": "增值税专用发票需关注购买方名称、税号与本公司是否一致。",
            "tags": ["票据风险", "invoice_list"],
        },
        {
            "memory_type": "case_example",
            "content": "某项目中，个人账户收取客户款项被判定为高风险，建议补充代收说明并调整账务处理。",
            "tags": ["银行流水风险", "bank_statement"],
        },
    ]
    for m in defaults + extra:
        if m["content"] in existing_contents:
            continue
        tags = m.get("tags", [])
        db.add(
            Memory(
                memory_type=m["memory_type"],
                content=m["content"],
                tags=tags,
                embedding_json=embed_memory_content(m["content"], tags),
            )
        )
    db.commit()

    for mem in db.query(Memory).filter(Memory.embedding_json.is_(None)).all():
        mem.embedding_json = embed_memory_content(mem.content, mem.tags or [])
    db.commit()
    reindex_memory_vectors(db)


def sync_pgvector_from_json(db: Session) -> None:
    from app.models import Memory
    from app.services.vector_store import ensure_pgvector_extension, sync_memory_vector

    if not ensure_pgvector_extension(db):
        return
    for mem in db.query(Memory).filter(Memory.embedding_json.isnot(None)).all():
        sync_memory_vector(db, mem.id, mem.embedding_json)
    db.commit()


def reindex_memory_vectors(db: Session) -> int:
    from app.models import Memory
    from app.services.embedding_service import embed_memory_content
    from app.services.vector_store import ensure_pgvector_extension, sync_memory_vector

    ensure_pgvector_extension(db)
    count = 0
    for mem in db.query(Memory).all():
        mem.embedding_json = embed_memory_content(mem.content, mem.tags or [])
        count += 1
    db.commit()
    for mem in db.query(Memory).all():
        if mem.embedding_json:
            sync_memory_vector(db, mem.id, mem.embedding_json)
    db.commit()
    return count
