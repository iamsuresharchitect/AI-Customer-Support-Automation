"""Knowledge Base Agent: retrieves relevant policy passages with the search_kb tool.

Documents in knowledge_base/ are split into sections by their "## " headings. Each section gets
metadata at ingestion time (document, section, topic) and is searched two ways:
- dense: ChromaDB with its built-in local embedding model (all-MiniLM-L6-v2), cosine distance
- sparse: BM25 over the same sections, so exact names and figures ("15 minutes", "₹10,000") count
The two rankings are fused with Reciprocal Rank Fusion. If ChromaDB is unavailable (for example
offline on first run), search falls back to BM25 alone.
"""

import hashlib
import math
import re
from collections import Counter
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "knowledge_base"
CHROMA_DIR = ROOT / "chroma_db"
COLLECTION = "shopnest_kb"

# Cosine distance: 0 is identical, 1 is unrelated. A section counts as relevant if its vector is
# close enough OR it matches enough query terms in BM25; the Resolution Agent still decides whether
# the passages actually answer the question.
MAX_DISTANCE = 0.70
MIN_BM25_SHARE = 0.5  # a keyword-only hit must score at least half of the best BM25 score
TOP_K = 3
RRF_K = 60  # standard Reciprocal Rank Fusion constant
TOPIC_BOOST = 1.2  # sections on the Query Agent's category rank a little higher

TOPICS = ["Shipping", "Refund", "Account", "Product", "Billing"]
# Section headings that belong to a different topic than their document.
HEADING_TOPICS = [(r"billing|charge|payment", "Billing")]

_collection = None


def _topic(doc_title: str, heading: str) -> str:
    """Topic of a section: from its heading if that names one, otherwise from the document title."""
    for pattern, topic in HEADING_TOPICS:
        if re.search(pattern, heading, re.IGNORECASE):
            return topic
    for topic in TOPICS:
        if topic.lower() in doc_title.lower():
            return topic
    return "Other"


def load_sections() -> list[dict]:
    """Split every markdown file into one section per '## ' heading, with its metadata."""
    sections = []
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
        doc_title = title_match.group(1).strip() if title_match else path.stem
        for part in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
            heading, _, body = part.partition("\n")
            heading = heading.strip()
            sections.append(
                {
                    "id": f"{path.name}::{heading}",
                    "source": path.name,
                    "doc_title": doc_title,
                    "heading": heading,
                    "topic": _topic(doc_title, heading),
                    "text": f"{doc_title} - {heading}\n{body.strip()}",
                }
            )
    return sections


def _kb_fingerprint(sections: list[dict]) -> str:
    return hashlib.sha256("".join(s["text"] + s["topic"] for s in sections).encode("utf-8")).hexdigest()[:16]


def _get_collection():
    """Open the ChromaDB collection, rebuilding it whenever the documents change."""
    global _collection
    if _collection is not None:
        return _collection

    import chromadb

    sections = load_sections()
    fingerprint = _kb_fingerprint(sections)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        existing = client.get_collection(COLLECTION)
        if (existing.metadata or {}).get("fingerprint") == fingerprint:
            _collection = existing
            return _collection
        client.delete_collection(COLLECTION)
    except Exception:
        pass

    collection = client.create_collection(
        COLLECTION,
        metadata={"fingerprint": fingerprint},
        configuration={"hnsw": {"space": "cosine"}},
    )
    collection.add(
        ids=[s["id"] for s in sections],
        documents=[s["text"] for s in sections],
        metadatas=[{"source": s["source"], "heading": s["heading"], "topic": s["topic"], "doc_title": s["doc_title"]} for s in sections],
    )
    _collection = collection
    return _collection


def _dense_ranking(query: str) -> dict[str, float]:
    """Section id -> cosine distance for every section, closest first."""
    count = len(load_sections())
    result = _get_collection().query(query_texts=[query], n_results=count)
    return dict(zip(result["ids"][0], result["distances"][0]))


def _stem(word: str) -> str:
    """Very light stemming so "charged", "charges" and "charge" match ("refunds" -> "refund")."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _tokens(text: str) -> list[str]:
    # Keep numbers whole ("10,000" -> "10000") so figures match exactly.
    return [_stem(t) for t in re.findall(r"[a-z]+|\d+", text.lower().replace(",", ""))]


STOPWORDS = {"the", "a", "an", "and", "or", "to", "of", "my", "i", "is", "it", "for", "in", "on", "with", "can",
             "how", "do", "was", "what", "be", "are", "you", "your", "me", "this", "that", "at", "if", "we", "our"}


def bm25_scores(query: str, sections: list[dict], k1: float = 1.5, b: float = 0.75) -> dict[str, float]:
    """Okapi BM25 score of each section for the query (only sections with a score above 0)."""
    docs = [_tokens(f"{s['heading']} {s['text']}") for s in sections]  # the heading counts too
    avg_len = sum(len(d) for d in docs) / len(docs)
    doc_freq = Counter(term for d in docs for term in set(d))
    terms = [t for t in _tokens(query) if t not in STOPWORDS]
    scores = {}
    for section, doc in zip(sections, docs):
        counts = Counter(doc)
        score = 0.0
        for term in terms:
            if term not in counts:
                continue
            idf = math.log(1 + (len(docs) - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            tf = counts[term]
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(doc) / avg_len))
        if score > 0:
            scores[section["id"]] = score
    return scores


def search_passages(query: str, topic: str = "", method: str = "hybrid", top_k: int = TOP_K) -> tuple[list[dict], str]:
    """Return (hits, method used). method is "hybrid", "dense" or "bm25" (the last two are for evaluate.py)."""
    sections = load_sections()
    by_id = {s["id"]: s for s in sections}
    dense = {}
    if method in ("hybrid", "dense"):
        try:
            dense = _dense_ranking(query)
        except Exception:
            method = "bm25"  # ChromaDB unavailable: keyword search still works
    bm25 = bm25_scores(query, sections) if method in ("hybrid", "bm25") else {}

    # Relevant = close in vector space, or a strong keyword match.
    best_bm25 = max(bm25.values(), default=0)
    relevant = {i for i, d in dense.items() if d <= MAX_DISTANCE} | {i for i, sc in bm25.items() if sc >= MIN_BM25_SHARE * best_bm25}

    dense_rank = {i: r for r, i in enumerate(sorted(dense, key=dense.get), start=1)}
    bm25_rank = {i: r for r, i in enumerate(sorted(bm25, key=bm25.get, reverse=True), start=1)}
    fused = {}
    for i in relevant:
        score = sum(1 / (RRF_K + ranks[i]) for ranks in (dense_rank, bm25_rank) if i in ranks)
        if topic and by_id[i]["topic"].lower() == topic.strip().lower():
            score *= TOPIC_BOOST
        fused[i] = score

    hits = []
    for i in sorted(fused, key=fused.get, reverse=True)[:top_k]:
        hits.append(
            {
                **by_id[i],
                "score": fused[i],
                "dense_rank": dense_rank.get(i),
                "bm25_rank": bm25_rank.get(i),
                "distance": dense.get(i),
            }
        )
    label = {"hybrid": "hybrid: chromadb + bm25", "dense": "chromadb", "bm25": "bm25"}[method]
    return hits, label


def search_kb(query: str, category: str = "") -> str:
    """Search the ShopNest knowledge base (shipping, refunds, account/login, product FAQ, billing) and return the matching passages with their source file names. Pass the Query Agent's CATEGORY as category so passages on that topic rank higher."""
    hits, method = search_passages(query, topic=category)
    if not hits:
        return f"SOURCES: NONE\nNo relevant passage found in the knowledge base for: {query!r} (search: {method})"

    sources = sorted({h["source"] for h in hits})
    lines = [f"SOURCES: {', '.join(sources)}", f"(search: {method})", ""]
    for i, hit in enumerate(hits, start=1):
        found_by = " + ".join(n for n, r in (("vector", hit["dense_rank"]), ("keyword", hit["bm25_rank"])) if r)
        lines.append(f"[{i}] {hit['source']} > {hit['heading']} (topic: {hit['topic']}; found by {found_by})")
        lines.append(hit["text"])
        lines.append("")
    return "\n".join(lines).strip()


SYSTEM_MESSAGE = """You are the Knowledge Base Agent for ShopNest customer support.
Your only job is to look up company documents. Do not answer the customer.
Read the Query Agent's CATEGORY and SUMMARY, then call the search_kb tool exactly once with category set to that CATEGORY and a short, specific search query in English (for example "late order delivery timeline trace"), even if the customer wrote in another language.
Do not write anything else; the tool's output is passed on to the Resolution Agent."""


def create_knowledge_agent(model_client) -> AssistantAgent:
    return AssistantAgent(
        name="knowledge_agent",
        description="Searches the company knowledge base and returns relevant passages with source file names. Speaks after the complaint has been classified.",
        model_client=model_client,
        system_message=SYSTEM_MESSAGE,
        tools=[search_kb],
        reflect_on_tool_use=False,
        tool_call_summary_format="{result}",
    )
