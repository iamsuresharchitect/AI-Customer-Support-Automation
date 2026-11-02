# AI Customer Support Automation

A multi-agent support desk for **ShopNest**, a made-up online store. Four AutoGen agents powered by Claude read a customer complaint, look up the answer in the company's own policy documents, write a grounded reply in the customer's own language, and log every ticket. Hard cases go to a human support person, who approves, edits or rejects the reply before it is sent.

Built with **AutoGen (agentchat 0.7)**, **Anthropic Claude**, **ChromaDB** and **Streamlit**.

![Resolved ticket](screenshots/resolved.png)

## How it works

```
Customer complaint (Streamlit form)
        │
        ▼
┌──────────────────────┐   CATEGORY / URGENCY / SENTIMENT / SUMMARY
│ Customer Query Agent │──────────────────────────────────────────┐
└──────────────────────┘                                          │
        ▼                                                         │
┌──────────────────────┐   search_kb(query) ──► ChromaDB          │
│ Knowledge Base Agent │   passages + source file names           │
└──────────────────────┘                                          │
        ▼                                                         │
┌──────────────────────┐   REPLY / USED_SOURCES / CONFIDENCE      │
│   Resolution Agent   │   (only facts from the passages)         │
└──────────────────────┘                                          │
        ▼                                                         ▼
┌──────────────────────┐   log_ticket(...) ──► logs/tickets.csv
│      Log Agent       │   escalation rule ──► Resolved / Escalated
└──────────────────────┘   replies "LOGGED TKT-0007" ──► team stops
        │
        ▼  (escalated tickets only)
┌──────────────────────┐   Approvals tab: approve / edit / reject
│ Support reviewer     │   UserProxyAgent ──► review_status, final_response
│ (human)              │
└──────────────────────┘
```

| Agent | Job | Output |
|---|---|---|
| Customer Query Agent | Understands the complaint | Category, urgency (Low/Medium/High), sentiment, language, one-line summary |
| Knowledge Base Agent | Calls the `search_kb` tool | Matching passages with their source file |
| Resolution Agent | Writes the customer reply from the passages only, in the customer's language | Reply, sources used, confidence |
| Log Agent | Calls the `log_ticket` tool | One CSV row, status and escalation reason |
| Support reviewer (human) | A `UserProxyAgent` for the support person | Approved, edited or rejected reply |

The agents run in a `SelectorGroupChat`: after each message the model reads the conversation and the agents' descriptions and picks who speaks next (normally Query → Knowledge → Resolution → Log). A `candidate_func` offers only agents that haven't spoken yet, so each does its job once and the run can't loop. A `TextMentionTermination("LOGGED")` on the Log Agent ends the run, with a `MaxMessageTermination(8)` as a safety net.

### Human in the loop

Escalated tickets are logged as **Pending approval**. In the app's **Approvals** tab, a support person reads the complaint, the reason it was escalated and the draft reply, then approves it, edits it, or rejects it with a note. The decision goes through AutoGen's `UserProxyAgent` (`agents/review_agent.py`) and is saved in the ticket log (`review_status`, `reviewer`, `final_response`, `reviewed_at`). Running `python team.py "..."` asks for the same decision in the terminal.

### Customer language

The Query Agent detects the complaint's language, including Indian languages such as Tamil, Malayalam, Telugu and Hindi (and Tanglish-style mixes). The Knowledge Base Agent still searches in English, and the Resolution Agent writes the reply in the customer's language. The language is shown on the result and saved in the log.

### Knowledge base (RAG)

`knowledge_base/` holds four policy documents: shipping, refunds, account and login, and a product FAQ. Each file is split into sections by its `##` headings, embedded with ChromaDB's built-in local model (all-MiniLM-L6-v2, so no extra API key is needed) and stored in `chroma_db/`. The index rebuilds itself whenever a document changes. If ChromaDB is unavailable, search falls back to keyword matching.

### Escalation rule

A ticket is **Escalated** to human support when any of these is true; otherwise it is **Resolved**:

- urgency is High
- the customer is Angry or Very Angry
- no matching document was used for the reply
- the Resolution Agent's confidence is Low
- the complaint mentions legal action, fraud or a payment dispute

The rule lives in plain Python (`decide_escalation` in `agents/log_agent.py`) so it is predictable and easy to test.

## Project structure

```
├── app.py                     # Streamlit UI: new ticket, approvals, ticket log, dashboard
├── team.py                    # wires the four agents into one AutoGen team
├── test_cases.py              # runs the test complaints and checks the status
├── agents/
│   ├── model_client.py        # shared Claude model client
│   ├── query_agent.py         # Customer Query Agent
│   ├── knowledge_agent.py     # Knowledge Base Agent + search_kb tool (ChromaDB)
│   ├── resolution_agent.py    # Resolution Agent
│   ├── log_agent.py           # Log Agent + log_ticket tool + escalation rule
│   └── review_agent.py        # human approval through UserProxyAgent
├── knowledge_base/            # company documents
├── logs/tickets.csv           # created automatically
├── screenshots/
├── .env.example
├── requirements.txt
└── README.md
```

## Setup

You need Python 3.10 or newer and an Anthropic API key.

```bash
git clone https://github.com/iamsuresharchitect/AI-Customer-Support-Automation.git
cd AI-Customer-Support-Automation
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
copy .env.example .env          # cp on macOS / Linux
```

Open `.env` and set `ANTHROPIC_API_KEY`. `ANTHROPIC_MODEL` is optional and defaults to `claude-opus-5-5`.

## Run

```bash
streamlit run app.py
```

The first run downloads the 80 MB embedding model once.

To run all test complaints from the terminal:

```bash
python test_cases.py        # all cases
python test_cases.py 5      # just case 5
```

## Test results

| # | Complaint | Result |
|---|---|---|
| 1 | Where is my order? It was supposed to arrive yesterday. | Shipping · shipping_policy.md · **Resolved** |
| 2 | I want to return the shoes I bought last week. How do I get a refund? | Refund · refund_policy.md · **Resolved** |
| 3 | I forgot my password and can't log in. | Account · account_and_login.md · **Resolved** |
| 4 | The blender I received is broken. Can I get a replacement? | Product · refund_policy.md, product_faq.md · **Resolved** |
| 5 | You charged my card three times! Fix this now or I'm contacting my bank and a lawyer. | Billing · High · Very Angry · **Escalated** (high urgency, angry, legal threat, payment dispute) |
| 6 | Do you sell gift cards for a company of 500 employees with custom branding? | Not covered by the docs · honest reply · **Escalated** (low confidence) |
| 7 *(own)* | Can I change the delivery address? I just placed the order an hour ago. | Shipping · shipping_policy.md · **Resolved** |
| 8 *(own)* | Someone logged into my account and placed orders I never made. This is fraud! | Account · High · Angry · **Escalated** (high urgency, angry, possible fraud) |
| 9 *(own)* | मेरा ऑर्डर अभी तक नहीं आया। यह कल आना था। (Hindi: my order hasn't arrived) | Shipping · Hindi · reply in Hindi · expected **Resolved** |
| 10 *(own)* | நான் கடந்த வாரம் வாங்கிய காலணிகளைத் திருப்பி அனுப்ப வேண்டும். பணத்தை எப்படித் திரும்பப் பெறுவது? (Tamil: return shoes, get a refund) | Refund · Tamil · reply in Tamil · expected **Resolved** |

Cases 1 to 8 matched the expected status in the live run. Cases 9 and 10 were added with the language feature.

## Screenshots

| Resolved ticket | Escalated ticket |
|---|---|
| ![Resolved](screenshots/resolved.png) | ![Escalated](screenshots/escalated.png) |

| Own test case: change address | Own test case: account fraud |
|---|---|
| ![Own case 1](screenshots/own_case_address.png) | ![Own case 2](screenshots/own_case_fraud.png) |

| Ticket log | Dashboard |
|---|---|
| ![Ticket log](screenshots/ticket_log.png) | ![Dashboard](screenshots/dashboard.png) |

| Approvals (human in the loop) | Reply in the customer's language |
|---|---|
| ![Approvals](screenshots/approvals.png) | ![Tamil reply](screenshots/tamil_reply.png) |

## Bonus features

- **Embeddings + vector store:** ChromaDB with a local embedding model, rebuilt automatically when the documents change.
- **SelectorGroupChat:** the model decides which agent speaks next.
- **Human in the loop:** a support person approves, edits or rejects escalated replies through `UserProxyAgent`.
- **Multilingual replies:** the customer's language (for example Tamil, Malayalam, Telugu, Hindi) is detected and the reply is written in it, in that language's script.
- **Dashboard:** KPIs (total, resolved by AI, escalated and awaiting approval, average urgency), ticket volume over time, tickets per category, AI resolution rate per category, urgency, customer mood and escalation reasons.
- **Excel export:** the ticket log downloads as CSV or Excel.
- **Deployment:** runs on Streamlit Community Cloud (see below).

## Deploying to Streamlit Community Cloud

1. Push this repository to GitHub (`.env` is ignored, so your key stays local).
2. At [share.streamlit.io](https://share.streamlit.io), create an app from the repo with `app.py` as the main file and Python 3.12.
3. Under **Advanced settings → Secrets**, add:
   ```toml
   ANTHROPIC_API_KEY = "your-key"
   ```
4. Deploy. Note that the ticket log on Streamlit Cloud resets whenever the app restarts.

## Notes

- AutoGen 0.7's Anthropic client always sends `temperature`, which current Claude models reject, so `agents/model_client.py` removes it before each request, and `requirements.txt` keeps the Anthropic SDK on 1.x.
- No API keys are committed: `.env` is in `.gitignore`, and `.env.example` shows the format.
