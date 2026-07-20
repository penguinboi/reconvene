# ABOUTME: fzf change:reload target for TUI search — prints one tab-delimited line per FTS hit.
# ABOUTME: Line format: sid<TAB>project · relative · N✓ · snippet (markers stripped, whitespace flat).
import sys

from .classify import canonical_name
from .journal import relative_time
from .search import SNIPPET_CLOSE, SNIPPET_OPEN, search_sessions


def render_hit(hit) -> str:
    snippet = (hit.snippet
               .replace(SNIPPET_OPEN, "").replace(SNIPPET_CLOSE, "")
               .replace("\t", " ").replace("\n", " "))
    return (f"{hit.session_id}\t{canonical_name(hit.project_path)}"
            f" · {relative_time(hit.updated_at)} · {hit.hits}✓ · {snippet}")


def main(argv) -> int:
    query, db_path = argv[0], argv[1]
    try:
        hits = search_sessions(db_path, query)
    except RuntimeError as e:
        print(f"⚠ search unavailable: {e}")
        return 0
    for h in hits:
        print(render_hit(h))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
