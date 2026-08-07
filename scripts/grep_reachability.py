"""Can a read-only tool reach what the Candidate Set missed?

Rung 4 exists to find a Ground-Truth File that retrieval never returned. The
union Candidate Set's hit@20 is 88.9% on the dev split, so about 27 Instances of
244 hold no correct answer anywhere in the list. Those Instances are the whole
target: no amount of reasoning helps when the answer was never there to rank.

`search_code` is `git grep`, and `git grep` finds a literal string or nothing.
So this script asks whether the report and the Ground-Truth File share one. It
calls no model, it costs nothing, and it writes no `RESULTS.md` entry, because
it scores no Rung.

Two numbers per kind of pattern, because the tool truncates its output:

- **reachable** -- some pattern's matches include a Ground-Truth File
- **reachable within the cap** -- the file is inside the first `HIT_CAP` matches,
  in git's own order, which is what the tool would actually show the agent

The gap between the two is what truncation costs. A pattern that matches 800
files reaches the answer and shows the agent something else.

A low number is a finding rather than a failure. It would say the tool roster is
wrong, and ADR-0009 must answer that before rung 4 costs $8 to run.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from faultloc.candidates import hit_at_k, reciprocal_rank_fusion
from faultloc.dataset.models import Instance
from faultloc.dataset.splits import load_splits
from faultloc.dataset.verified import load_verified_set
from faultloc.issue_patterns import KINDS, patterns
from faultloc.llm import MODELS
from faultloc.repos import RepoStore
from faultloc.response_cache import ResponseCache
from faultloc.rungs.bm25_chunks import Bm25ChunksRung
from faultloc.rungs.embed import EmbedRung
from faultloc.rungs.rerank import MAX_TOKENS, LlmRerankRung
from faultloc.scoring import normalize_path

#: Where the Candidate Set's ceiling was measured, so where the misses are.
CEILING_K = 20

#: Matches a truncating tool would show. Rung 4's `search_code` caps its hits,
#: and a reachability figure that ignored the cap would overstate what the agent
#: can see. Not yet a decided constant -- issue 05 sets it, and this measurement
#: is one input to that.
HIT_CAP = 30


def off_list_paths(text: str, head: tuple[str, ...]) -> list[str]:
    """Path-looking lines in a reply that were never candidates.

    Mirrors `LlmRerankRung._parse`'s rule deliberately, because the question is
    what *that* rung counted. The rung counts these and discards the path, so
    the paths themselves were never recorded. This is the only way back to them.
    """
    wanted = set(head)
    found = []
    for line in text.splitlines():
        candidate = line.strip().strip("`").lstrip("-*0123456789. ").strip()
        if not candidate or candidate in wanted:
            continue
        if "/" in candidate or candidate.endswith(".py"):
            found.append(candidate)
    return found


def reachability(
    store: RepoStore,
    instance: Instance,
    truth: set[str],
) -> dict[str, tuple[bool, bool]]:
    """Per kind: was a Ground-Truth File reachable, and reachable within the cap.

    One `git grep` per pattern. A pattern whose matches include a truth file
    makes that kind reachable, and the cap decides whether the agent would have
    been shown it.
    """
    result = {}
    for kind, kind_patterns in patterns(instance.issue_text).items():
        reached = capped = False
        for pattern in kind_patterns:
            matches = store.grep(instance.repo, instance.base_commit, pattern)
            normalized = [normalize_path(path) for path in matches]
            if truth & set(normalized):
                reached = True
                if truth & set(normalized[:HIT_CAP]):
                    capped = True
                    break  # nothing further can improve this kind
        result[kind] = (reached, capped)
    return result


def main() -> int:
    loaded = load_verified_set()
    splits = load_splits()
    instances = splits.select(loaded.instances, "dev")

    store = RepoStore()
    lexical = Bm25ChunksRung(store, include_bodies=True)
    dense = EmbedRung(store)

    # Only for the footnote: the rung supplies the exact prompt whose hash keys
    # the cache. Nothing here calls a model, so a cache miss simply yields no
    # evidence for that Instance.
    rung = LlmRerankRung(store, candidates=None, model=MODELS["gpt-oss-high"])
    cache = ResponseCache()

    missed: list[tuple[Instance, set[str]]] = []
    off_list: list[tuple[Instance, str]] = []
    replies = 0

    print(f"pass 1: candidate sets over {len(instances)} dev Instances", flush=True)
    for n, instance in enumerate(instances, 1):
        truth = {normalize_path(path) for path in instance.ground_truth_files}

        lex = lexical.predict(instance).ranked_files
        den = dense.predict(instance).ranked_files
        merged = reciprocal_rank_fusion([lex, den])

        ranked = tuple(normalize_path(path) for path in merged)
        if not hit_at_k(ranked, sorted(truth), CEILING_K):
            missed.append((instance, truth))

        head = merged[: rung.top_k]
        if head:
            reply = cache.get(rung.model, rung._prompt(instance, head), MAX_TOKENS)
            if reply is not None:
                replies += 1
                off_list.extend((instance, path) for path in off_list_paths(reply.text, head))

        if n % 50 == 0:
            print(f"  ... {n}/{len(instances)}  missed so far: {len(missed)}", flush=True)

    total = len(instances)
    print(f"\ndev split, n={total}")
    print(f"hit@{CEILING_K} = {100 * (total - len(missed)) / total:.1f}%")
    print(f"Instances with no Ground-Truth File in the list: {len(missed)}")

    print(f"\npass 2: git grep over {len(missed)} missed Instances", flush=True)
    reached_any: list[bool] = []
    capped_any: list[bool] = []
    by_kind: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    by_repo: dict[str, list[bool]] = defaultdict(list)

    for n, (instance, truth) in enumerate(missed, 1):
        found = reachability(store, instance, truth)
        for kind, flags in found.items():
            by_kind[kind].append(flags)

        reached = any(flags[0] for flags in found.values())
        capped = any(flags[1] for flags in found.values())
        reached_any.append(reached)
        capped_any.append(capped)
        by_repo[instance.repo].append(capped)

        print(
            f"  [{n:>3}/{len(missed)}] {instance.instance_id:40} "
            f"reachable={'yes' if reached else 'no ':3} within cap={'yes' if capped else 'no'}",
            flush=True,
        )

    if not missed:
        print("\nno missed Instances, so nothing to reach")
        return 0

    n_missed = len(missed)
    print(f"\nreachability over the {n_missed} missed Instances")
    print(f"  reachable at all        {100 * sum(reached_any) / n_missed:5.1f}%")
    print(f"  within a {HIT_CAP}-hit cap     {100 * sum(capped_any) / n_missed:5.1f}%")
    lost = sum(reached_any) - sum(capped_any)
    print(f"  lost to truncation      {100 * lost / n_missed:5.1f}%")

    print(f"\nby pattern kind{'':10}reachable   within cap")
    for kind in KINDS:
        flags = by_kind[kind]
        reached = 100 * sum(f[0] for f in flags) / n_missed
        capped = 100 * sum(f[1] for f in flags) / n_missed
        print(f"  {kind:22}{reached:7.1f}%     {capped:7.1f}%")

    print("\nby repo, within cap")
    for repo, flags in sorted(by_repo.items(), key=lambda kv: -len(kv[1])):
        print(f"  {repo:28} missed={len(flags):3}  {100 * sum(flags) / len(flags):5.1f}%")

    print(f"\nfootnote: Off-List Paths from the cached rung-3 cell ({rung.model.label})")
    print(f"  cached replies found: {replies}/{total}")
    if not off_list:
        print("  no Off-List Paths recovered")
        return 0

    exists = 0
    for instance, path in off_list:
        listed = {f.path for f in store.list_files(instance.repo, instance.base_commit)}
        present = path in listed
        exists += present
        print(f"  {'exists ' if present else 'ABSENT '} {instance.instance_id:40} {path}")
    print(
        f"  {len(off_list)} Off-List Paths: {exists} exist at base_commit, "
        f"{len(off_list) - exists} do not. The Path Guardrail catches the second group."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
