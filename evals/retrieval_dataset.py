"""Stage 1 golden dataset — retrieval evaluation.

Ground truth was pulled by reading each paper's real chunks (OpenSearchClient.
get_chunks_by_paper) and picking whichever chunk actually contains the answer — NOT
mechanically defaulting to the abstract (chunk_index=0), and NOT derived from what
today's search happens to return. Both shortcuts would corrupt the labels: the first
makes every question trivially abstract-answerable regardless of what it actually asks;
the second makes a labeling bug and a retrieval bug indistinguishable.

Only 4 of these 20 questions legitimately point at the abstract — the
`summarize_main_contribution` ones, because a high-level summary IS what an abstract is
for. The other 16 point at a specific body section: the retriever has to actually get
past the abstract to find the answer, which is the whole point of a retrieval eval.

Two fields are List[str] rather than str: expected_paper_id, expected_chunk_id. Singular
questions use a one-item list; #16 (multi_paper_comparison) uses three.

difficulty:
    easy    query vocabulary close to the paper's own terms — should work on BM25 alone.
    medium  deliberate paraphrase, avoids the paper's terminology — needs real vector
            matching.
    hard    heavy paraphrase + jargon avoidance, OR the correct answer is "nothing"
            (corpus gap / out of scope) — hard because the system must resist
            hallucinating rather than just needing to locate text.

Note: difficulty is about how hard the QUERY is to match; it is independent of how deep
in the paper the answer chunk sits. PAC-MAN is "easy" (query vocabulary closely tracks
the paper's own abstract wording) even though its answer chunk is a body section, not
the abstract — those are two different axes.

query_type:
    factual_lookup               "what does paper X say about Y"
    summarize_main_contribution  "what is the main contribution of paper X"
    multi_paper_comparison       answer legitimately spans >1 paper
    out_of_scope                 correct behavior is refusal
    vague                        underspecified — tests the rewrite loop, not a
                                  single direct match
"""

GOLDEN_RETRIEVAL: list[dict] = [

    # ══════════════════════════════════════ EASY (10) ══════════════════════════════════════

    {
        "query": "What safety mechanism does PAC-MAN use for humanoid robots?",
        "expected_paper_id": ["2607.28623v1"],
        "expected_chunk_id": ["zFekvJ8B6M9P4WOzsLvX"],   # [8] B. Whole-body barriers
        "expected_answer": "PAC-MAN uses barrier information at two levels: a lightweight "
            "per-link reward (Link-CBF) that guides training, and a more robust whole-body "
            "joint-space projection (Joint-CBF) that can also act as a runtime filter — "
            "studying what a policy can internalize from partial perception versus what "
            "still requires direct online enforcement.",
        "difficulty": "easy",
        "query_type": "factual_lookup",
    },
    {
        "query": "What did the PAIChecker paper find about PR-issue misalignment?",
        "expected_paper_id": ["2607.28587v1"],
        "expected_chunk_id": ["QFekvJ8B6M9P4WOzprvB"],   # [4] 2.2 Results and Analysis
        "expected_answer": "Misalignment follows a taxonomy of five distinct patterns "
            "across 11 fine-grained scenarios, each corresponding to a different root "
            "cause in the PR-Issue pairing pipeline; the patterns are orthogonal, so a "
            "single instance can carry multiple labels.",
        "difficulty": "easy",
        "query_type": "factual_lookup",
    },
    {
        "query": "How reliable are LLMs when it comes to playing dice?",
        "expected_paper_id": ["2606.07515v1"],
        "expected_chunk_id": ["vPQZVp8BFCyB9K3mrSfm"],   # [11] 4 Discussion
        "expected_answer": "Models perform well on standard probability exercises "
            "(average accuracy 0.96) but accuracy drops substantially on the "
            "counterintuitive dataset — a marked gap between mechanical calculation and "
            "genuine probabilistic reasoning.",
        "difficulty": "easy",
        "query_type": "factual_lookup",
    },
    {
        "query": "How does AISPA audit system prompts for LLM applications?",
        "expected_paper_id": ["2607.28617v1"],
        "expected_chunk_id": ["eVekvJ8B6M9P4WOzqbvm"],   # [10] 4.2 Auditing Pipeline
        "expected_answer": "AISPA runs a three-round collaborative audit protocol "
            "combining LLM-assisted analysis with human judgement — each round narrows "
            "the candidate spans and applies a higher evidentiary standard, starting with "
            "LLM-assisted candidate generation in round 1.",
        "difficulty": "easy",
        "query_type": "factual_lookup",
    },
    {
        "query": "What infrastructure does AskChem use to synthesize claims from chemistry literature?",
        "expected_paper_id": ["2607.28618v1"],
        "expected_chunk_id": ["pFekvJ8B6M9P4WOzrbup"],   # [4] 3 Claim Extraction and Evidence Graph
        "expected_answer": "AskChem populates its claim store with two complementary "
            "extraction pipelines: a high-throughput extractor over abstracts at scale, "
            "and a deeper extractor over full-text PDFs that captures claim types often "
            "absent from abstracts.",
        "difficulty": "easy",
        "query_type": "factual_lookup",
    },
    {
        "query": "What is the computational complexity of winner determination under Thiele voting rules?",
        "expected_paper_id": ["2607.28575v1"],
        "expected_chunk_id": ["1lekvJ8B6M9P4WOzmrqq"],   # [8] 3 Structure of Winning Committees
        "expected_answer": "The paper builds a 'dominancy graph' over candidates to "
            "characterize winning-committee structure, then derives FPT and "
            "polynomial-time complexity results from it in later sections.",
        "difficulty": "easy",
        "query_type": "factual_lookup",
        "note": "The full complexity picture actually spans §3-§5 (structure → FPT "
            "results → polynomial algorithm), not one isolated sentence. §3 is the anchor "
            "that everything downstream builds on — a good retriever might reasonably "
            "surface any of §3/§4/§5 here; treat adjacent sections as partial credit, "
            "not just this one exact chunk_id.",
    },
    {
        "query": "How does Tytan construct semantic schemas from relational data?",
        "expected_paper_id": ["2608.06331v1"],
        "expected_chunk_id": ["mVfC358B6M9P4WOzL7wc"],   # [7] 4.1 Structural profiling and Symbolic analysis
        "expected_answer": "Tytan begins by collecting deterministic information from the "
            "database — tables, columns, declared keys, sampled distinct values, "
            "cardinalities, null rates — and also accepts flat files like CSV/Excel by "
            "loading them into a relational store first.",
        "difficulty": "easy",
        "query_type": "factual_lookup",
    },
    {
        "query": "What is the main contribution of the sim-to-real dexterous manipulation paper?",
        "expected_paper_id": ["2605.28812v1"],
        "expected_chunk_id": ["hPQZVp8BFCyB9K3mqSdU"],   # [0] Abstract — correct here, this IS a summary question
        "expected_answer": "It introduces a physics-grounded contact representation that "
            "lets touch — an information-dense modality usually lost in sim-to-real "
            "transfer — be effectively used for contact-rich manipulation.",
        "difficulty": "easy",
        "query_type": "summarize_main_contribution",
    },
    {
        "query": "Summarize the main idea behind OpenCoF.",
        "expected_paper_id": ["2607.08763v1"],
        "expected_chunk_id": ["7fQZVp8BFCyB9K3msifW"],   # [0] Abstract — correct here
        "expected_answer": "OpenCoF proposes reasoning through video generation as an "
            "alternative to Chain-of-Thought — reasoning unfolds through temporally "
            "consistent generated video rather than text.",
        "difficulty": "easy",
        "query_type": "summarize_main_contribution",
    },
    {
        "query": "What is the capital of France?",
        "expected_paper_id": [],
        "expected_chunk_id": [],
        "expected_answer": "REFUSE — not a research-paper question, no corpus lookup should happen.",
        "difficulty": "easy",
        "query_type": "out_of_scope",
    },

    # ══════════════════════════════════════ MEDIUM (5) ══════════════════════════════════════

    {
        "query": "How do agents build a common understanding of each other's requests before working together?",
        "expected_paper_id": ["2305.09349v1"],
        "expected_chunk_id": ["QlfC4J8B6M9P4WOzor0_"],   # [5] 2.2 Agent Communication Establishment
        "expected_answer": "The paper surveys communication-establishment studies "
            "applicable across agents regardless of the (in)formal representation system "
            "each one uses, focused on Open Multi-Agent Systems where the agent "
            "population is dynamic.",
        "difficulty": "medium",
        "query_type": "factual_lookup",
    },
    {
        "query": "How can AI agents prove who they are and build trust with each other before talking?",
        "expected_paper_id": ["2511.02841v2"],
        "expected_chunk_id": ["alfC4J8B6M9P4WOzqb3H"],   # [4] 4 Concept
        "expected_answer": "Each agent belongs to a security domain and controls its own "
            "DID and verifiable credentials; every agent's DID is anchored in a jointly "
            "operated distributed ledger shared across multiple security domains, "
            "enabling cross-domain trust verification.",
        "difficulty": "medium",
        "query_type": "factual_lookup",
    },
    {
        "query": "What theoretical approaches could let a machine conduct genuine scientific discovery on its own?",
        "expected_paper_id": ["2110.01831v1"],
        "expected_chunk_id": ["iVfG4J8B6M9P4WOzx723"],   # [0] Abstract — correct here
        "expected_answer": "The paper explores logicist, emergentist, and universalist "
            "approaches to AGI toward building an 'Artificial Scientist,' concluding a "
            "unified/hybrid approach is necessary.",
        "difficulty": "medium",
        "query_type": "summarize_main_contribution",
    },
    {
        "query": "How do I fine-tune a language model on my own dataset?",
        "expected_paper_id": [],
        "expected_chunk_id": [],
        "expected_answer": "REFUSE or find nothing — generic practical question, not "
            "answered by any specific paper's findings in this corpus.",
        "difficulty": "medium",
        "query_type": "out_of_scope",
    },
    {
        "query": "What's that recent paper about routing tokens more efficiently to save memory?",
        "expected_paper_id": ["2410.17954v2"],
        "expected_chunk_id": ["-FfM358B6M9P4WOz57yf"],   # [10] 3.4 Expert Cache Engine (ECE)
        "expected_answer": "ExpertFlow's Expert Cache Engine manages expert parameters "
            "between GPU and CPU by combining predictive, locality-aware caching (which "
            "plans layout/prefetching from predicted routing) with a real-time correction "
            "mechanism for prediction errors.",
        "difficulty": "medium",
        "query_type": "vague",
    },

    # ══════════════════════════════════════ HARD (5) ══════════════════════════════════════

    {
        "query": "What techniques are used for expert routing in mixture-of-experts models?",
        "expected_paper_id": ["2410.17954v2", "2601.15021v1", "2603.11114v1"],
        "expected_chunk_id": [
            "9lfM358B6M9P4WOz57yf",   # [8] ExpertFlow — 3.2 Routing Path Predictor (RPP)
            "IVfM358B6M9P4WOz671j",   # [9] MoE in Vision — B. Expert Utilization and Specialization
            "z1fM358B6M9P4WOz4bz8",   # [4] Routing Signatures — 3.2 Routing Signatures
        ],
        "expected_answer": "Three distinct routing techniques: ExpertFlow predicts the "
            "routing path ahead of time with a T5-style encoder-decoder (replacing "
            "sequential layer-by-layer MLP prediction); the vision paper tracks per-expert "
            "routing probability across training, finding it converges to balanced "
            "utilization; the routing-signatures paper defines a layer-wise vector "
            "summarizing how often each expert activates per prompt.",
        "difficulty": "hard",
        "query_type": "multi_paper_comparison",
        "note": "Note this uses a DIFFERENT ExpertFlow chunk than the vague case above — "
            "that one asks about memory/caching (§3.4 ECE), this one asks about routing "
            "technique specifically (§3.2 RPP). Same paper, two different correct chunks, "
            "because the two questions genuinely ask about different sections.",
    },
    {
        "query": "What is multi-head attention?",
        "expected_paper_id": [],
        "expected_chunk_id": [],
        "expected_answer": "CORRECTLY find nothing — no attention-mechanism paper exists "
            "in this corpus. A confident answer here is a hallucination, not a success.",
        "difficulty": "hard",
        "query_type": "factual_lookup",
    },
    {
        "query": "How can we tell which parts of an image actually caused a smaller model "
                 "to learn something from a bigger one's example?",
        "expected_paper_id": ["2607.28590v1"],
        "expected_chunk_id": ["OVdEvp8B6M9P4WOzF7we"],   # [7] 3.2 Attributing the Teacher Correction
        "expected_answer": "VAD attributes the teacher's correction token-by-token: a "
            "positive score means the visual evidence raises a candidate token's relative "
            "probability (supports it); a negative score means the evidence refutes it — "
            "this is how it identifies which image regions actually drove the correction.",
        "difficulty": "hard",
        "query_type": "factual_lookup",
    },
    {
        "query": "Can one robot control program work across robots that have completely "
                 "different physical bodies?",
        "expected_paper_id": ["2608.06374v1"],
        "expected_chunk_id": ["Z1fC358B6M9P4WOzKLx_"],   # [0] Abstract — correct here
        "expected_answer": "DyPES-VLA learns shared dynamics priors plus "
            "embodiment-specific control, addressing generalist policy training across "
            "heterogeneous robot embodiments.",
        "difficulty": "hard",
        "query_type": "summarize_main_contribution",
    },
    {
        "query": "What jailbreak techniques work against system prompts?",
        "expected_paper_id": [],
        "expected_chunk_id": [],
        "expected_answer": "REFUSE or find nothing. Adversarial near-miss: shares "
            "vocabulary with AISPA ('system prompts') but AISPA is about USER-FACING "
            "AUDITING/DISCLOSURE, not jailbreak/attack techniques. Tests whether topical "
            "vocabulary overlap fools grading into accepting an unrelated chunk — the "
            "mirror image of the earlier bug where grading was too strict.",
        "difficulty": "hard",
        "query_type": "out_of_scope",
    },
]
