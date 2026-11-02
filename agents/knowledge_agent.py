"""Knowledge Base Agent: retrieves relevant policy passages with the search_kb tool.

Documents in knowledge_base/ are split into sections by their "## " headings, embedded with
ChromaDB's built-in local model (all-MiniLM-L6-v2) and stored in chroma_db/. If ChromaDB is not
available (for example offline on first run), search falls back to simple keyword matching.
"""

import hashlib
import re
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "knowledge_base"
CHROMA_DIR = ROOT / "chroma_db"
COLLECTION = "shopnest_kb"

# Cosine distance: 0 is identical, 1 is unrelated. Passages above this are dropped; the
# Resolution Agent still decides whether the remaining ones actually answer the question.
MAX_DISTANCE = 0.70
TOP_K = 3

_collection = None


def load_sections() -> list[dict]:
    """Split every markdown file into one section per '## ' heading."""
    sections = []
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
        doc_title = title_match.group(1).strip() if title_match else path.stem
        for part in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
            heading, _, body = part.partition("\n")
            sections.append(
                {
                    "id": f"{path.name}::{heading.strip()}",
                    "source": path.name,
                    "heading": heading.strip(),
                    "text": f"{doc_title} - {heading.strip()}\n{body.strip()}",
                }
            )
    return sections


def _kb_fingerprint(sections: list[dict]) -> str:
    return hashlib.sha256("".join(s["text"] for s in sections).encode("utf-8")).hexdigest()[:16]


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
        metadatas=[{"source": s["source"], "heading": s["heading"]} for s in sections],
    )
    _collection = collection
    return _collection


def _vector_search(query: str) -> list[dict]:
    result = _get_collection().query(query_texts=[query], n_results=TOP_K)
    hits = []
    for text, meta, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
        if distance <= MAX_DISTANCE:
            hits.append({"source": meta["source"], "heading": meta["heading"], "text": text, "score": 1 - distance})
    return hits


def _keyword_search(query: str) -> list[dict]:
    stopwords = {"the", "a", "an", "and", "or", "to", "of", "my", "i", "is", "it", "for", "in", "on", "with", "can", "how", "do", "was"}
    words = {w for w in re.findall(r"[a-z]+", query.lower()) if w not in stopwords and len(w) > 2}
    scored = []
    for section in load_sections():
        section_words = set(re.findall(r"[a-z]+", section["text"].lower()))
        overlap = len(words & section_words)
        if overlap >= 2:
            scored.append({**section, "score": overlap / max(len(words), 1)})
    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:TOP_K]


def search_passages(query: str) -> tuple[list[dict], str]:
    """Return (hits, method). Used by the tool below and by the Streamlit app."""
    try:
        return _vector_search(query), "chromadb"
    except Exception:
        return _keyword_search(query), "keyword"


def search_kb(query: str) -> str:
    """Search the ShopNest knowledge base (shipping, refunds, account/login, product FAQ) and return the matching passages with their source file names."""
    hits, method = search_passages(query)
    if not hits:
        return f"SOURCES: NONE\nNo relevant passage found in the knowledge base for: {query!r} (search: {method})"

    sources = sorted({h["source"] for h in hits})
    lines = [f"SOURCES: {', '.join(sources)}", f"(search: {method})", ""]
    for i, hit in enumerate(hits, start=1):
        lines.append(f"[{i}] {hit['source']} > {hit['heading']} (relevance {hit['score']:.2f})")
        lines.append(hit["text"])
        lines.append("")
    return "\n".join(lines).strip()


SYSTEM_MESSAGE = """You are the Knowledge Base Agent for ShopNest customer support.
Your only job is to look up company documents. Do not answer the customer.
Read the Query Agent's CATEGORY and SUMMARY, then call the search_kb tool exactly once with a short, specific search query in English (for example "late order delivery timeline trace"), even if the customer wrote in another language.
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
