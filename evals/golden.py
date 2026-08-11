"""Golden eval set.

Start small and grow. Five cases that already have known-correct answers beat fifty
guessed ones — get the harness running first, then expand.

Each case declares what SHOULD happen. Fields are optional; an evaluator skips a case
that doesn't declare the field it measures.

    query        the user's question
    tool         expected router decision: "retrieve" | "fetch_live_papers"
    answered     True  = should produce a real answer
                 False = should refuse (off-topic) or fall back (nothing relevant)
    papers       arxiv_ids that SHOULD appear in the sources (retrieval check)
    note         why this case exists — keep it, future-you will forget
"""

GOLDEN: list[dict] = [
    # ── routing: ordinary questions must NOT trigger a live fetch ──────────────
    {
        "query": "what safety mechanism does PAC-MAN use for humanoid robots?",
        "tool": "retrieve",
        "answered": True,
        "papers": ["2607.28623v1"],
        "note": "In-corpus happy path. Also the guardrail false-refusal regression: "
                "PAC-MAN is a real paper, not the video game.",
    },
    {
        "query": "what did the PAIChecker paper find?",
        "tool": "retrieve",
        "answered": True,
        "papers": ["2607.28587v1"],
        "note": "Names a paper but ASKS ABOUT it — must not route to summarize/fetch.",
    },
    {
        "query": "how reliable are LLMs at probabilistic reasoning?",
        "tool": "retrieve",
        "answered": True,
        "papers": ["2606.07515v1"],
        "note": "Paraphrase — the paper is about dice, the query says 'probabilistic'.",
    },

    # ── routing: explicit fetch intent ────────────────────────────────────────
    {
        "query": "find new papers on speculative decoding",
        "tool": "fetch_live_papers",
        "note": "Explicit 'find new papers' → live fetch. No `answered` assertion: "
                "depends on what arXiv returns today.",
    },
    {
        "query": "search arxiv for recent work on quantum machine learning",
        "tool": "fetch_live_papers",
        "note": "Different phrasing of the same intent.",
    },

    # ── guardrail: must refuse ────────────────────────────────────────────────
    {
        "query": "what is the capital of France?",
        "answered": False,
        "note": "Clearly off-topic → guardrail refuses before any retrieval.",
    },
    {
        "query": "what's a good recipe for sourdough bread?",
        "answered": False,
        "note": "Second off-topic control, so the refusal rate isn't a single sample.",
    },

    # ── known-hard: currently expected to FAIL the answered check ─────────────
    {
        "query": "what is multi-head attention?",
        "tool": "retrieve",
        "answered": False,
        "note": "There is NO attention paper in the corpus, so 'no relevant papers' is "
                "the CORRECT behaviour. Flip `answered` to True once one is ingested — "
                "this case is here to catch the grader becoming too lenient.",
    },
]
