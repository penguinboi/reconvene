# ABOUTME: Tests for journal model — grouping, splitting, and ranking sessions.
# ABOUTME: Verifies project aggregation, real vs bot classification, and recency ranking.
from datetime import datetime

from reconvene.config import Config
from reconvene.db import Session
from reconvene.journal import build_journal, recency_bucket


def S(sid, path, updated, message_count=10):
    return Session(sid, path, updated, updated, message_count, None, None)


def test_build_journal_groups_ranks_and_splits():
    config = Config(bot_names={"scoutbot"})
    sessions = [
        S("a", "/Users/x/Code/acme/myproject", "2026-07-01 00:00:00"),
        S("b", "/Users/x/Code/myproject",        "2026-07-08 00:00:00"),  # same project, newer
        S("c", "/Users/x/Code/myorg/otherproject", "2026-07-05 00:00:00"),
        S("d", "/Users/x/Code/myorg/scoutbot",   "2026-07-09 00:00:00"),  # bot
        S("e", "/private/tmp/x/scratchpad",    "2026-07-10 00:00:00"),  # dropped
    ]
    real, bots = build_journal(sessions, config)
    assert [p.name for p in real] == ["myproject", "otherproject"]  # myproject newest (b) first
    assert real[0].count == 2 and real[0].latest.session_id == "b"
    assert [p.name for p in bots] == ["scoutbot"]


def test_build_journal_promotes_long_bot_sessions_and_drops_noise():
    config = Config(bot_names={"scoutbot"})
    sessions = [
        S("f", "/Users/x/Code/myorg/scoutbot", "2026-07-09 00:00:00", message_count=3397),
        S("g", "/Users/x/Code/myorg/scoutbot/worker", "2026-07-09 01:00:00", message_count=2),
        S("h", "/Users/x/Code/myorg/sideproject", "2026-07-09 02:00:00", message_count=2),
        S("i", "/Users/x/Code/myorg/sideproject", "2026-07-09 03:00:00", message_count=40),
    ]
    real, bots = build_journal(sessions, config)
    real_names = {p.name for p in real}
    assert "scoutbot" in real_names  # promoted: long session in a bot-named project
    assert "sideproject" in real_names
    sideproject = next(p for p in real if p.name == "sideproject")
    assert sideproject.count == 1 and sideproject.latest.session_id == "i"  # noisy session dropped


def test_recency_bucket_active_within_24_hours():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2026-07-13 00:00:00", now=now) == "active"


def test_recency_bucket_active_at_exactly_24_hours():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2026-07-12 12:00:00", now=now) == "active"


def test_recency_bucket_recent_just_past_24_hours():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2026-07-12 11:59:59", now=now) == "recent"


def test_recency_bucket_recent_at_exactly_7_days():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2026-07-06 12:00:00", now=now) == "recent"


def test_recency_bucket_stale_just_past_7_days():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2026-07-06 11:59:59", now=now) == "stale"


def test_recency_bucket_stale_long_ago():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2020-01-01 00:00:00", now=now) == "stale"


def test_recency_bucket_defaults_now_to_current_time():
    # No `now` passed — exercises the real datetime.now() default path.
    recent = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assert recency_bucket(recent) == "active"
