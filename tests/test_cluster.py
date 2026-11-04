# ABOUTME: Tests for root detection and the sticky TopicCache.
# ABOUTME: Roots = paths prefixing >=3 other session paths (worktree children excluded).
import pytest

from reconvene.cluster import (
    TopicAuthError, TopicCache, build_organize_prompt, detect_roots,
    load_topic_lookup, organize, parse_assignments,
)
from reconvene.config import Config
from reconvene.constants import WORKTREE_MARKERS
from tests.conftest import add_session, add_message


def test_detect_roots_needs_three_distinct_children():
    paths = {"/u/Code", "/u/Code/a", "/u/Code/b", "/u/Code/c"}
    assert detect_roots(paths) == {"/u/Code"}


def test_detect_roots_two_children_is_not_a_root():
    assert detect_roots({"/u/Code", "/u/Code/a", "/u/Code/b"}) == set()


def test_detect_roots_ignores_worktree_children():
    paths = {"/u/Code/foo",
             "/u/Code/foo/.claude-worktrees/a",
             "/u/Code/foo/.claude-worktrees/b",
             "/u/Code/foo/.claude-worktrees/c"}
    assert detect_roots(paths) == set()


def test_detect_roots_candidate_must_be_a_session_path():
    # /u/Code prefixes three paths but is not itself a session's project_path.
    assert detect_roots({"/u/Code/a", "/u/Code/b", "/u/Code/c"}) == set()


def test_detect_roots_prefix_is_segment_aligned():
    # /u/Code must not claim /u/Codebase as a child.
    paths = {"/u/Code", "/u/Codebase1", "/u/Codebase2", "/u/Codebase3"}
    assert detect_roots(paths) == set()


def test_topic_cache_assign_is_sticky(tmp_path):
    cache = TopicCache(str(tmp_path / "r.db"))
    cache.assign("s1", "NAS & Pi-Hole")
    cache.assign("s1", "Something Else")     # must NOT overwrite
    assert cache.get_all() == {"s1": "NAS & Pi-Hole"}
    assert cache.topics() == {"NAS & Pi-Hole"}
    cache.close()


def test_load_topic_lookup_roundtrip(tmp_path):
    cache = TopicCache(str(tmp_path / "r.db"))
    cache.assign("s1", "Desktop Cleanup")
    cache.close()
    assert load_topic_lookup(str(tmp_path / "r.db")) == {"s1": "Desktop Cleanup"}


def test_parse_assignments_valid_partial_and_garbage():
    output = "s1: NAS & Pi-Hole\ngarbage line\n- s2: Desktop Cleanup\nsx: Not A Session\n"
    assert parse_assignments(output, {"s1", "s2"}) == {
        "s1": "NAS & Pi-Hole", "s2": "Desktop Cleanup",
    }


def test_build_organize_prompt_includes_sessions_and_existing_topics(ccrider_db):
    add_session(ccrider_db, "l1", "/Users/x/Code", "2026-07-08 00:00:00",
                message_count=20, summary="nas work")
    add_message(ccrider_db, "l1", "user", "tune the synology", sequence=1)
    from reconvene.db import load_sessions
    (s,) = load_sessions(str(ccrider_db))
    prompt = build_organize_prompt([s], str(ccrider_db), {"Desktop Cleanup"})
    assert "l1" in prompt and "tune the synology" in prompt
    assert "Desktop Cleanup" in prompt and "nas work" in prompt


def test_organize_assigns_and_is_sticky(tmp_path, ccrider_db):
    add_session(ccrider_db, "l1", "/Users/x/Code", "2026-07-08 00:00:00", message_count=20)
    add_message(ccrider_db, "l1", "user", "pihole setup", sequence=1)
    from reconvene.db import load_sessions
    sessions = load_sessions(str(ccrider_db))
    cache = TopicCache(str(tmp_path / "r.db"))
    n = organize(sessions, str(ccrider_db), cache, Config(),
                 runner=lambda prompt: "l1: NAS & Pi-Hole")
    assert n == 1
    n2 = organize(sessions, str(ccrider_db), cache, Config(),
                  runner=lambda prompt: "l1: Different Topic")
    assert cache.get_all() == {"l1": "NAS & Pi-Hole"}   # sticky
    cache.close()


def test_organize_auth_none_raises(tmp_path, ccrider_db):
    add_session(ccrider_db, "l1", "/Users/x/Code", "2026-07-08 00:00:00", message_count=20)
    add_message(ccrider_db, "l1", "user", "hi", sequence=1)
    from reconvene.db import load_sessions
    cache = TopicCache(str(tmp_path / "r.db"))
    with pytest.raises(TopicAuthError):
        organize(load_sessions(str(ccrider_db)), str(ccrider_db), cache,
                 Config(recap_auth_mode="none"), runner=lambda p: "")
    cache.close()


def test_organize_empty_input_is_zero_and_no_claude_call(tmp_path):
    calls = []
    cache = TopicCache(str(tmp_path / "r.db"))
    assert organize([], "/nonexistent.db", cache, Config(),
                    runner=lambda p: calls.append(p) or "") == 0
    assert calls == []
    cache.close()


def _reference_detect_roots(paths):
    norm = {p.rstrip("/") for p in paths if p and p.rstrip("/")}
    roots = set()
    for cand in norm:
        prefix = cand + "/"
        children = {
            p for p in norm
            if p != cand and p.startswith(prefix)
            and not any(m in p[len(cand):] for m in WORKTREE_MARKERS)
        }
        if len(children) >= 3:
            roots.add(cand)
    return roots


@pytest.mark.parametrize("paths", [
    [],
    ["", "/", "//"],
    ["/u/Code/", "/u/Code/a/", "/u/Code/b", "/u/Code/c"],
    ["/u", "/u/a", "/u/a/x", "/u/a/y", "/u/a/z", "/u/b"],
    ["/a/b", "/a/bc", "/a/bd", "/a/be", "/a/b/c"],
    ["/a/b", "/a/b/1", "/a/b/2", "/a/bx", "/a/b-1"],
    ["/r", "/r/a", "/r/b"],
    ["/r", "/r/a", "/r/b", "/r/c"],
    ["/u/Code/foo", "/u/Code/foo/.claude-worktrees/a", "/u/Code/foo/.worktrees/b",
     "/u/Code/foo/x--claude-worktrees", "/u/Code/foo/real"],
    ["/u/Code/foo", "/u/Code/foo/a", "/u/Code/foo/b", "/u/Code/foo/c/.worktrees/d"],
    ["/u/.worktrees/p", "/u/.worktrees/p/a", "/u/.worktrees/p/b", "/u/.worktrees/p/c"],
])
def test_detect_roots_matches_reference_on_hand_written_cases(paths):
    assert detect_roots(paths) == _reference_detect_roots(paths)


def test_detect_roots_matches_reference_on_random_paths():
    import random
    rng = random.Random(1774)
    parts = ["a", "b", "bc", "b-1", "Code", ".claude-worktrees", ".worktrees", "x--claude-worktrees", "z"]
    for _ in range(5):
        paths = []
        for _ in range(1000):
            path = "/" + "/".join(rng.choice(parts) for _ in range(rng.randint(0, 5)))
            if rng.random() < 0.15:
                path += "/"
            paths.append(path)
        paths.append("")
        assert detect_roots(paths) == _reference_detect_roots(paths)
