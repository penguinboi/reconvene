# ABOUTME: Tests for journal model — grouping, splitting, and ranking sessions.
# ABOUTME: Verifies project aggregation, real vs bot classification, and recency ranking.
from datetime import datetime, timezone

from reconvene.config import Config
from reconvene.db import Session
from reconvene.journal import (
    abbreviate_home,
    build_journal,
    build_settings_projects,
    recency_bucket,
    relative_time,
    verbose_age,
)


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


def test_build_journal_excludes_user_hidden_projects():
    # A project the user hid by name must not appear on the journal (real or bot).
    config = Config(hidden_names={"secretproj"})
    sessions = [
        S("a", "/Users/x/Code/myproject", "2026-07-08 00:00:00"),
        S("b", "/Users/x/Code/secretproj", "2026-07-09 00:00:00"),
    ]
    real, bots = build_journal(sessions, config)
    names = {p.name for p in real} | {p.name for p in bots}
    assert names == {"myproject"}  # secretproj hidden from the journal


def test_build_settings_projects_includes_user_hidden_but_not_noise():
    # The settings view surfaces real + bot + user-hidden projects (so hidden ones can be toggled
    # back), but still excludes noise-dropped ones (scratchpad, <=2-message pings).
    config = Config(bot_names={"scoutbot"}, hidden_names={"secretproj"})
    sessions = [
        S("a", "/Users/x/Code/myproject", "2026-07-08 00:00:00"),
        S("b", "/Users/x/Code/secretproj", "2026-07-09 00:00:00"),      # user-hidden
        S("c", "/Users/x/Code/scoutbot", "2026-07-09 00:00:00", message_count=100),  # bot->real (promoted)
        S("d", "/private/tmp/x/scratchpad", "2026-07-10 00:00:00"),     # noise drop
        S("e", "/Users/x/Code/pingbot", "2026-07-10 00:00:00", message_count=1),  # noise drop
    ]
    projects = build_settings_projects(sessions, config)
    names = {p.name for p in projects}
    assert "myproject" in names
    assert "secretproj" in names   # user-hidden IS shown here (so it can be un-hidden)
    assert "scoutbot" in names
    assert "scratchpad" not in names  # noise stays out
    assert "pingbot" not in names     # noise stays out
    hidden = next(p for p in projects if p.name == "secretproj")
    assert hidden.category == "hidden"


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
    # No `now` passed — exercises the real default-clock path. Must be UTC, matching
    # ccrider's real timestamps (see test below) -- a local-time default would silently
    # misclassify recency by the local UTC offset.
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    assert recency_bucket(recent) == "active"


def test_recency_bucket_handles_real_ccrider_timestamp_format():
    # ccrider's real `updated_at` values include fractional seconds and a "+0000 UTC"
    # suffix (Go's default time.Time.String() format), e.g. "2026-07-13 10:12:17.839 +0000 UTC" --
    # not the simplified "YYYY-MM-DD HH:MM:SS" the rest of this file's fixtures use.
    # Reproduces a real ValueError crash seen against live production data.
    now = datetime(2026, 7, 13, 10, 12, 20)
    assert recency_bucket("2026-07-13 10:12:17.839 +0000 UTC", now=now) == "active"


def test_relative_time_just_now_under_a_minute():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-15 11:59:30", now=now) == "just now"


def test_relative_time_minutes_ago():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-15 11:58:00", now=now) == "2m ago"


def test_relative_time_hours_ago():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-15 09:00:00", now=now) == "3h ago"


def test_relative_time_days_ago():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-13 12:00:00", now=now) == "2d ago"


def test_relative_time_months_ago():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-05-15 12:00:00", now=now) == "2mo ago"


def test_relative_time_years_ago():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2024-07-15 12:00:00", now=now) == "2y ago"


def test_relative_time_handles_real_ccrider_timestamp_format():
    # Same fractional-seconds + "+0000 UTC" format that once crashed recency_bucket
    # (see the test-fixtures-mirror-real-schema lesson) — relative_time must not
    # reintroduce that bug.
    now = datetime(2026, 7, 13, 10, 12, 20)
    assert relative_time("2026-07-13 10:12:17.839 +0000 UTC", now=now) == "just now"


# Boundary tests for relative_time: exactly at threshold vs just below
# (exercises all 5 comparison thresholds: 60s, 3600s, 86400s, 2592000s, 31536000s)

def test_relative_time_59_seconds_stays_just_now():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-15 11:59:01", now=now) == "just now"


def test_relative_time_60_seconds_crosses_to_minutes():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-15 11:59:00", now=now) == "1m ago"


def test_relative_time_3599_seconds_stays_in_minutes():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-15 11:00:01", now=now) == "59m ago"


def test_relative_time_3600_seconds_crosses_to_hours():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-15 11:00:00", now=now) == "1h ago"


def test_relative_time_86399_seconds_stays_in_hours():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-14 12:00:01", now=now) == "23h ago"


def test_relative_time_86400_seconds_crosses_to_days():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-14 12:00:00", now=now) == "1d ago"


def test_relative_time_2591999_seconds_stays_in_days():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-06-15 12:00:01", now=now) == "29d ago"


def test_relative_time_2592000_seconds_crosses_to_months():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-06-15 12:00:00", now=now) == "1mo ago"


def test_relative_time_31535999_seconds_stays_in_months():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2025-07-15 12:00:01", now=now) == "12mo ago"


def test_relative_time_31536000_seconds_crosses_to_years():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2025-07-15 12:00:00", now=now) == "1y ago"


def test_abbreviate_home_collapses_home_prefix():
    assert abbreviate_home("/Users/fake/Code/foo", home="/Users/fake") == "~/Code/foo"


def test_abbreviate_home_exact_home_path():
    assert abbreviate_home("/Users/fake", home="/Users/fake") == "~"


def test_abbreviate_home_leaves_unrelated_path_unchanged():
    assert abbreviate_home("/opt/other/path", home="/Users/fake") == "/opt/other/path"


def test_abbreviate_home_does_not_match_sibling_dir_with_shared_prefix():
    # "/Users/fake2" starts with the string "/Users/fake" but is a different directory —
    # must not be treated as being under "/Users/fake".
    assert abbreviate_home("/Users/fake2/Code", home="/Users/fake") == "/Users/fake2/Code"


def test_verbose_age_just_now_under_a_minute():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert verbose_age("2026-07-15 11:59:30", now=now) == "just now"


def test_verbose_age_minutes_singular_and_plural():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert verbose_age("2026-07-15 11:59:00", now=now) == "1 minute ago"
    assert verbose_age("2026-07-15 11:30:00", now=now) == "30 minutes ago"


def test_verbose_age_hours_singular_and_plural():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert verbose_age("2026-07-15 11:00:00", now=now) == "1 hour ago"
    assert verbose_age("2026-07-15 09:00:00", now=now) == "3 hours ago"


def test_verbose_age_days_singular_and_plural():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert verbose_age("2026-07-14 12:00:00", now=now) == "1 day ago"
    assert verbose_age("2026-07-13 12:00:00", now=now) == "2 days ago"


def test_verbose_age_weeks_singular_and_plural():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert verbose_age("2026-07-08 12:00:00", now=now) == "1 week ago"
    assert verbose_age("2026-06-24 12:00:00", now=now) == "3 weeks ago"


def test_verbose_age_months_singular_and_plural():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert verbose_age("2026-06-13 12:00:00", now=now) == "1 month ago"
    assert verbose_age("2026-05-15 12:00:00", now=now) == "2 months ago"


def test_verbose_age_years_singular_and_plural():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert verbose_age("2025-07-15 12:00:00", now=now) == "1 year ago"
    assert verbose_age("2024-07-15 12:00:00", now=now) == "2 years ago"


def test_verbose_age_handles_real_ccrider_timestamp_format():
    now = datetime(2026, 7, 13, 10, 12, 20)
    assert verbose_age("2026-07-13 10:12:17.839 +0000 UTC", now=now) == "just now"
