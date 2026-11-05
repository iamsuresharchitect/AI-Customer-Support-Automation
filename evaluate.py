"""Evaluate the support desk against ground-truth questions and save the results to CSV.

    python evaluate.py                 # retrieval only (no API key needed)
    python evaluate.py --answers       # + answer faithfulness (uses Claude)
    python evaluate.py --followups     # + follow-up rewrite check (uses Claude)
    python evaluate.py --all           # everything

Ground truth lives in evaluation/ground_truth.json. Results are written to evaluation/results/:
    retrieval_<time>.csv   one row per question and search method (hit@1, hit@3, reciprocal rank)
    answers_<time>.csv     one row per question (key facts found, faithfulness score, judge notes)
    followups_<time>.csv   one row per follow-up (hit@3 for the raw text vs the rewritten question)
    summary_<time>.csv     the averages, also printed at the end

Metrics:
    hit@k         share of questions where a relevant section is in the top k results
    MRR           mean of 1 / rank of the first relevant section (0 if not in the top k)
    fact recall   share of answers that contain the expected key fact (e.g. "15 minutes")
    faithfulness  supported claims / total claims, judged by Claude against the retrieved passages
"""

import argparse
import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path

from agents.knowledge_agent import search_kb, search_passages

ROOT = Path(__file__).resolve().parent
GROUND_TRUTH = ROOT / "evaluation" / "ground_truth.json"
RESULTS_DIR = ROOT / "evaluation" / "results"
METHODS = ["dense", "bm25", "hybrid"]
K = 3

JUDGE_PROMPT = """You check whether a customer-support reply is faithful to the knowledge-base passages it was based on.
Split the reply into its factual claims (policies, numbers, timelines, steps, promises). Ignore greetings and sign-offs.
For each claim decide if the passages support it.
Answer with JSON only, in this shape:
{"claims": [{"claim": "...", "supported": true}], "notes": "one short sentence"}"""


def _key(doc: str, heading: str) -> tuple[str, str]:
    return doc.strip().lower(), heading.strip().lower()


def first_relevant_rank(hits: list[dict], relevant: list[list[str]]) -> int:
    """1-based rank of the first relevant section in hits, 0 if none."""
    wanted = {_key(d, h) for d, h in relevant}
    for rank, hit in enumerate(hits, start=1):
        if _key(hit["source"], hit["heading"]) in wanted:
            return rank
    return 0


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        fields = list(dict.fromkeys(k for row in rows for k in row))  # summary rows have different columns
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ---------- 1. Retrieval ----------


def evaluate_retrieval(questions: list[dict]) -> tuple[list[dict], list[dict]]:
    rows = []
    for q in questions:
        for method in METHODS:
            hits, _ = search_passages(q["question"], method=method, top_k=K)
            rank = first_relevant_rank(hits, q["relevant"])
            rows.append(
                {
                    "id": q["id"],
                    "question": q["question"],
                    "method": method,
                    "hit@1": int(rank == 1),
                    f"hit@{K}": int(rank > 0),
                    "reciprocal_rank": round(1 / rank, 3) if rank else 0,
                    "rank_of_relevant": rank or "",
                    "top_results": " | ".join(f"{h['source']} > {h['heading']}" for h in hits),
                }
            )
    summary = []
    for method in METHODS:
        mine = [r for r in rows if r["method"] == method]
        n = len(mine)
        summary.append(
            {
                "part": "retrieval",
                "method": method,
                "questions": n,
                "hit@1": round(sum(r["hit@1"] for r in mine) / n, 3),
                f"hit@{K}": round(sum(r[f"hit@{K}"] for r in mine) / n, 3),
                "MRR": round(sum(r["reciprocal_rank"] for r in mine) / n, 3),
            }
        )
    return rows, summary


# ---------- 2. Answer faithfulness ----------


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON in judge reply")
    return json.loads(match.group(0))


def _reply_text(raw: str) -> str:
    match = re.search(r"REPLY:\s*(.*?)(?:\nUSED_SOURCES:|$)", raw, re.S)
    return (match.group(1) if match else raw).strip()


async def evaluate_answers(questions: list[dict]) -> tuple[list[dict], list[dict]]:
    from autogen_core.models import SystemMessage, UserMessage

    from agents.model_client import get_model_client
    from agents.resolution_agent import SYSTEM_MESSAGE as RESOLUTION_PROMPT

    client = get_model_client()
    rows = []
    for q in questions:
        passages = search_kb(q["question"])
        task = f"Customer message:\n{q['question']}\n\nKnowledge Base Agent's passages:\n{passages}"
        row = {"id": q["id"], "question": q["question"], "reply": "", "fact_found": "", "claims": "",
               "supported_claims": "", "faithfulness": "", "judge_notes": ""}
        try:
            result = await client.create([SystemMessage(content=RESOLUTION_PROMPT), UserMessage(content=task, source="user")])
            reply = _reply_text(result.content if isinstance(result.content, str) else str(result.content))
            row["reply"] = reply
            row["fact_found"] = int(any(f.lower() in reply.lower() for f in q.get("facts", [])))

            judge_input = f"Passages:\n{passages}\n\nReply:\n{reply}"
            verdict = await client.create([SystemMessage(content=JUDGE_PROMPT), UserMessage(content=judge_input, source="user")])
            data = _parse_json(verdict.content if isinstance(verdict.content, str) else str(verdict.content))
            claims = data.get("claims", [])
            supported = sum(1 for c in claims if c.get("supported"))
            row["claims"] = len(claims)
            row["supported_claims"] = supported
            row["faithfulness"] = round(supported / len(claims), 3) if claims else 1.0
            row["judge_notes"] = data.get("notes", "")
        except Exception as exc:  # keep going; the row records the error
            row["judge_notes"] = f"ERROR: {exc}"
        rows.append(row)
        print(f"  {q['id']}: fact={row['fact_found']} faithfulness={row['faithfulness']}")

    scored = [r for r in rows if r["faithfulness"] != ""]
    summary = [
        {
            "part": "answers",
            "method": "hybrid + resolution agent",
            "questions": len(rows),
            "answered": len(scored),
            "fact_recall": round(sum(r["fact_found"] for r in scored) / len(scored), 3) if scored else "",
            "faithfulness": round(sum(r["faithfulness"] for r in scored) / len(scored), 3) if scored else "",
        }
    ]
    return rows, summary


# ---------- 3. Follow-ups ----------


async def evaluate_followups(followups: list[dict]) -> tuple[list[dict], list[dict]]:
    from agents.followup import rewrite_followup

    rows = []
    for f in followups:
        raw_hits, _ = search_passages(f["followup"], top_k=K)
        rewritten = await rewrite_followup(f["complaint"], f["reply"], f["followup"])
        new_hits, _ = search_passages(rewritten, top_k=K)
        rows.append(
            {
                "id": f["id"],
                "followup": f["followup"],
                "followup_chars": len(f["followup"]),
                "rewritten": rewritten,
                f"raw_hit@{K}": int(first_relevant_rank(raw_hits, f["relevant"]) > 0),
                f"rewritten_hit@{K}": int(first_relevant_rank(new_hits, f["relevant"]) > 0),
            }
        )
    n = len(rows)
    summary = [
        {
            "part": "followups",
            "method": "raw follow-up",
            "questions": n,
            f"hit@{K}": round(sum(r[f"raw_hit@{K}"] for r in rows) / n, 3),
        },
        {
            "part": "followups",
            "method": "LLM-rewritten follow-up",
            "questions": n,
            f"hit@{K}": round(sum(r[f"rewritten_hit@{K}"] for r in rows) / n, 3),
        },
    ]
    return rows, summary


def print_summary(summary: list[dict]) -> None:
    print("\n=== Summary ===")
    for row in summary:
        rest = ", ".join(f"{k}={v}" for k, v in row.items() if k not in ("part", "method"))
        print(f"{row['part']:<10} {row['method']:<28} {rest}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval, answers and follow-ups.")
    parser.add_argument("--answers", action="store_true", help="also score answer faithfulness (uses Claude)")
    parser.add_argument("--followups", action="store_true", help="also check follow-up rewriting (uses Claude)")
    parser.add_argument("--all", action="store_true", help="run every part")
    args = parser.parse_args()

    data = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = []

    print(f"Retrieval: {len(data['questions'])} questions x {len(METHODS)} methods")
    rows, part = evaluate_retrieval(data["questions"])
    write_csv(RESULTS_DIR / f"retrieval_{stamp}.csv", rows)
    summary += part

    if args.answers or args.all:
        print(f"Answers: generating and judging {len(data['questions'])} replies")
        rows, part = asyncio.run(evaluate_answers(data["questions"]))
        write_csv(RESULTS_DIR / f"answers_{stamp}.csv", rows)
        summary += part

    if args.followups or args.all:
        print(f"Follow-ups: {len(data['followups'])} cases")
        rows, part = asyncio.run(evaluate_followups(data["followups"]))
        write_csv(RESULTS_DIR / f"followups_{stamp}.csv", rows)
        summary += part

    write_csv(RESULTS_DIR / f"summary_{stamp}.csv", summary)
    print_summary(summary)
    print(f"\nCSV files saved in {RESULTS_DIR.relative_to(ROOT)}/ (run {stamp})")


if __name__ == "__main__":
    main()
