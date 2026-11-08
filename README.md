# Haq: AI legal helper for deposit and refund disputes (India)

A chat assistant for two everyday problems:
- **Deposit:** a landlord won't return a security deposit.
- **Refund:** a seller, online store or service provider won't refund, or sold something defective.

It does four things:
1. **Organises the story** into a case card (facts, timeline, evidence you have and are missing).
2. **Explains options**, from mildest to strongest, with what each one costs and needs.
3. **Drafts a legal notice**, using [placeholders] for anything it doesn't know.
4. **Plays the other side** (landlord or customer care) so you can practise the conversation, with a coaching tip each turn.

Haq gives legal information, not legal advice, and is not a lawyer.

## How it avoids inventing laws (3 layers)

| Layer | What it does |
|---|---|
| 1. Verified list (`lawyer/laws.json`) | 13 provisions, each checked by a human against the official text, with a date and a "caution" note where the law is uncertain (for example, the Model Tenancy Act applies only in states that adopted it). |
| 2. Prompt | The model may mention law only from this list, by ID. It never cites court cases or criminal codes, and it says "I can't verify that" instead of guessing. |
| 3. Checker (`lawyer/checker.py`) | Code scans every reply and draft for sections, Acts, Rules, IPC/BNS/CrPC and case-law patterns. Anything not on the list is removed and the user sees a visible warning. The "Laws referred to" panel shows the list's own wording, never the model's. |

The checker is tested against 14 invented and 9 real references (`python test_checker.py`). Known gap: a false legal claim written without any citation (for example "by law landlords must pay 18% interest") can't be caught by pattern matching.

**Sending people to a lawyer** is decided by the model and also by code rules (`referral_triggers`): police or criminal issues, court papers, threats or eviction, amounts over Rs 50 lakh, family law, bounced cheques. Either one can trigger the "talk to a lawyer" box, which points to free legal aid (call 15100).

## Run

```bash
pip install -r requirements.txt
streamlit run app.py               # paste a free Gemini key (aistudio.google.com/apikey) in the sidebar
```

**Swap the model:** in the sidebar, choose `gemini`, `groq`, `openrouter` or `custom` (any OpenAI-compatible API with a base URL).

**Deploy:** push this repo to GitHub, then go to share.streamlit.io → Create app → set the main file to `app.py` → add the secret `GEMINI_API_KEY = "..."`.

## Tests

```bash
python test_checker.py                                         # checker only, no model needed
python run_tests.py --provider gemini --out outputs_gemini     # all 20 test conversations on a real model
python run_tests.py --provider replay --replay-dir replay_answers --out outputs   # reproduce the submitted run
```

- `test_cases.json` has 20 conversations: normal, missing information, adversarial, out of scope, story change, role-play and a large amount.
- Each one saves the full unedited transcript, the model's raw JSON, the checker log and pass/fail checks to `outputs/tests/`, with a table in `outputs/summary.md`.

**Note:** the workspace this was built in could not reach model APIs. In the submitted `outputs/`, the model's answers were written by Claude (Anthropic) through replay files (`replay_answers/`), while all checking was done by the code. Run against Gemini to get results from a real deployed model.

## Adding a new problem type (for example unpaid salary)

1. Add the verified provisions to `laws.json`.
2. Add one line about the new problem type to the scope in `lawyer/prompts.py`.
3. Add 5–10 test cases and run the tests.

Nothing else changes.
