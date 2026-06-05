import pytest

from app.services.embedding_service import cosine_similarity, embed_text
from app.services.memory_rag import retrieve_memories
from app.models import Memory
from app.database import SessionLocal, init_db


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


def test_embed_and_cosine_similarity():
    a = embed_text("增值税专用发票购买方名称不一致")
    b = embed_text("发票购买方税号与本公司不符")
    c = embed_text("今天天气很好")
    assert len(a) > 0
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


def test_retrieve_memories_vector_ranking(db):
    db.query(Memory).delete()
    db.commit()

    m1 = Memory(
        memory_type="accounting_knowledge",
        content="增值税专用发票需关注购买方名称、税号与本公司是否一致。",
        tags=["票据风险", "invoice_list"],
        embedding_json=embed_text("增值税专用发票需关注购买方名称、税号与本公司是否一致。"),
    )
    m2 = Memory(
        memory_type="accounting_knowledge",
        content="固定资产折旧年限应符合企业所得税法规定。",
        tags=["会计核算风险"],
        embedding_json=embed_text("固定资产折旧年限应符合企业所得税法规定。"),
    )
    db.add_all([m1, m2])
    db.commit()

    results = retrieve_memories(
        db,
        risk_category="票据风险",
        query_text="发票购买方名称与本公司不一致",
        limit=2,
    )
    assert len(results) >= 1
    assert results[0].id == m1.id
