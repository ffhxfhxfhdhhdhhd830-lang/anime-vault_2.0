from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from anime_bot import main


def _update(user_id=123, args=()):
    message = SimpleNamespace(reply_text=AsyncMock())
    user = SimpleNamespace(id=user_id)
    return SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=user_id),
        effective_message=message,
        message=message,
    )


def _context(db, user_id=123, args=()):
    settings = SimpleNamespace(owner_telegram_id=999)
    return SimpleNamespace(
        args=list(args),
        effective_user=SimpleNamespace(id=user_id),
        application=SimpleNamespace(
            bot_data={"db": db, "settings": settings}
        ),
    )


@pytest.mark.asyncio
async def test_totalrequests_counts_statuses_and_is_owner_only(monkeypatch):
    db = SimpleNamespace(
        access_requests=SimpleNamespace(
            count_documents=AsyncMock(side_effect=[4, 2, 1, 1])
        )
    )
    monkeypatch.setattr(main, "allowed", AsyncMock(return_value=True))
    update = _update(999)
    context = _context(db, 999)

    await main.totalrequests_cmd(update, context)

    assert db.access_requests.count_documents.await_count == 4
    assert "Total: 4" in update.message.reply_text.await_args.args[0]
    assert "Pending: 2" in update.message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_purgerequests_requires_confirmation_and_audits_deletion(monkeypatch):
    db = SimpleNamespace(
        access_requests=SimpleNamespace(
            count_documents=AsyncMock(return_value=3),
            delete_many=AsyncMock(return_value=SimpleNamespace(deleted_count=3)),
        ),
        audit=SimpleNamespace(insert_one=AsyncMock()),
    )
    monkeypatch.setattr(main, "allowed", AsyncMock(return_value=True))
    update = _update(999)
    context = _context(db, 999, args=())

    await main.purgerequests_cmd(update, context)

    db.access_requests.delete_many.assert_not_awaited()
    assert "CONFIRM" in update.message.reply_text.await_args.args[0]

    context.args = ["CONFIRM"]
    await main.purgerequests_cmd(update, context)

    db.access_requests.delete_many.assert_awaited_once_with({})
    db.audit.insert_one.assert_awaited_once()
    audit = db.audit.insert_one.await_args.args[0]
    assert audit["action"] == "purge_access_requests"
    assert audit["deleted_count"] == 3
    assert isinstance(audit["at"], datetime)
    assert audit["at"].tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_purgerequests_denies_non_owner(monkeypatch):
    db = SimpleNamespace(
        access_requests=SimpleNamespace(
            count_documents=AsyncMock(return_value=3),
            delete_many=AsyncMock(),
        ),
        audit=SimpleNamespace(insert_one=AsyncMock()),
    )
    monkeypatch.setattr(main, "allowed", AsyncMock(return_value=False))
    update = _update(123)
    context = _context(db, 123, args=("CONFIRM",))

    await main.purgerequests_cmd(update, context)

    db.access_requests.delete_many.assert_not_awaited()
    db.audit.insert_one.assert_not_awaited()
