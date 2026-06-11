import pytest
import pytest_asyncio
from sqlalchemy import select, text

from findleaks.models import Alert, Exam, Leak, Question, ScannerStatus, User


@pytest.mark.asyncio
async def test_all_six_tables_created(async_engine):
    expected = {"exams", "questions", "leaks", "alerts", "scanner_status", "users"}
    async with async_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tables = {row[0] for row in result.fetchall()}
    assert expected.issubset(tables)


@pytest.mark.asyncio
async def test_create_exam(db_session):
    exam = Exam(
        name="NEET 2024",
        slug="neet-2024",
        description="National Eligibility cum Entrance Test",
        keywords=["biology", "chemistry", "physics"],
        alert_config={"recipients": ["admin@nta.ac.in"], "webhooks": [], "sms": []},
    )
    db_session.add(exam)
    await db_session.commit()
    await db_session.refresh(exam)

    assert exam.id is not None
    assert exam.name == "NEET 2024"
    assert exam.slug == "neet-2024"
    assert exam.question_count == 0
    assert exam.last_indexed_at is None
    assert exam.status if hasattr(exam, "status") else True


@pytest.mark.asyncio
async def test_exam_slug_is_unique(db_session):
    from sqlalchemy.exc import IntegrityError

    db_session.add(Exam(name="Exam A", slug="dup-slug"))
    await db_session.commit()

    db_session.add(Exam(name="Exam B", slug="dup-slug"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_create_question_linked_to_exam(db_session):
    exam = Exam(name="JEE 2024", slug="jee-2024")
    db_session.add(exam)
    await db_session.commit()
    await db_session.refresh(exam)

    q = Question(
        exam_id=exam.id,
        question_text="What is the velocity of light?",
        cleaned_text="what is the velocity of light",
        page_number=1,
        question_number="Q1",
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)

    assert q.id is not None
    assert q.exam_id == exam.id


@pytest.mark.asyncio
async def test_create_leak_linked_to_exam(db_session):
    exam = Exam(name="CBSE 2024", slug="cbse-2024")
    db_session.add(exam)
    await db_session.commit()
    await db_session.refresh(exam)

    leak = Leak(
        exam_id=exam.id,
        platform="twitter",
        platform_post_id="tweet_123",
        confidence=0.87,
        confidence_label="high",
        matched_question_ids=[1, 2],
        matched_excerpts=[{"question_id": 1, "text": "sample", "score": 0.9}],
        status="new",
        alert_sent=False,
    )
    db_session.add(leak)
    await db_session.commit()
    await db_session.refresh(leak)

    assert leak.id is not None
    assert leak.confidence == 0.87
    assert leak.status == "new"
    assert leak.alert_sent is False


@pytest.mark.asyncio
async def test_create_alert_linked_to_leak(db_session):
    exam = Exam(name="GATE 2024", slug="gate-2024")
    db_session.add(exam)
    await db_session.commit()
    await db_session.refresh(exam)

    leak = Leak(
        exam_id=exam.id,
        platform="telegram",
        confidence=0.75,
        confidence_label="medium",
        status="new",
        alert_sent=False,
    )
    db_session.add(leak)
    await db_session.commit()
    await db_session.refresh(leak)

    alert = Alert(
        leak_id=leak.id,
        sent_to="admin@example.com",
        method="email",
        status="sent",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    assert alert.id is not None
    assert alert.method == "email"
    assert alert.status == "sent"


@pytest.mark.asyncio
async def test_scanner_status_unique_constraint(db_session):
    from sqlalchemy.exc import IntegrityError

    exam = Exam(name="Unique Exam", slug="unique-exam")
    db_session.add(exam)
    await db_session.commit()
    await db_session.refresh(exam)

    db_session.add(ScannerStatus(exam_id=exam.id, platform="twitter"))
    await db_session.commit()

    db_session.add(ScannerStatus(exam_id=exam.id, platform="twitter"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_create_user(db_session):
    user = User(
        username="admin",
        password_hash="$2b$12$fakehash",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.username == "admin"
    assert user.role == "admin"


@pytest.mark.asyncio
async def test_cascade_delete_exam_deletes_questions(db_session):
    exam = Exam(name="Cascade Exam", slug="cascade-exam")
    db_session.add(exam)
    await db_session.commit()
    await db_session.refresh(exam)

    q = Question(
        exam_id=exam.id,
        question_text="Test question",
        cleaned_text="test question",
    )
    db_session.add(q)
    await db_session.commit()

    await db_session.delete(exam)
    await db_session.commit()

    result = await db_session.execute(select(Question).where(Question.exam_id == exam.id))
    assert result.scalars().all() == []
