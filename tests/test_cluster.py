# ABOUTME: Tests for root detection and the sticky TopicCache.
# ABOUTME: Roots = paths prefixing >=3 other session paths (worktree children excluded).
from reconvene.cluster import TopicCache, detect_roots, load_topic_lookup


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
