import os
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


PROMPT_FILE_MAP = {
    "webhook": "webhook.txt",
    "rate-limiter": "rate-limiter.txt",
    "standard-vectorization": "standard-vectorization.txt",
    "langchain-vectorization": "langchain-vectorization.txt",
    "robust-otp": "robust-otp.txt",
    "data-extractor": "data-extractor.txt",
}


def trim_large_text(text: str = "", max_chars: int = 18000) -> str:
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n\n[TRUNCATED]"


def trim_file_map(file_map: dict | None, max_chars_per_file: int = 12000) -> dict:
    trimmed = {}

    for file_path, content in (file_map or {}).items():
        trimmed[file_path] = trim_large_text(content, max_chars_per_file)

    return trimmed


def load_assessment_prompt(assessment_type: str) -> str:
    prompt_file_name = PROMPT_FILE_MAP.get(assessment_type)

    if not prompt_file_name:
        raise ValueError(f"No prompt file mapped for assessment type: {assessment_type}")

    prompt_path = Path.cwd() / "prompts" / prompt_file_name

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8")


def get_assessment_calibration_rules(assessment_type: str) -> str:
    common_rules = """
GLOBAL FINAL EVALUATION CALIBRATION RULES

Apply these rules for every assessment type:

- The assessment prompt is the source of truth.
- The cloned repository evidence is the source of truth for implementation.
- The original assignment PDF is the source of truth for what the candidate was asked to build.
- The weak-signal scan is negative supporting evidence only.
- The weak-signal scan must never increase the candidate's score.
- The weak-signal scan must never be used to award points.
- The weak-signal scan has no score, no grade, and no positive signals.
- Use weak-signal scan only to catch problems that may be missed during final evaluation.
- Do not trust README claims unless code, results.json, tests, or deployment evidence supports them.
- If code and README disagree, trust code.
- If weak-signal scan and code disagree, trust code.
- If there is doubt between partial and full, choose partial.
- Award full points only when implementation evidence is clear and directly visible.
- Award partial points only when there is a real attempt but incomplete correctness.
- Award 0 when the feature is only claimed in README but not implemented.
- Missing tests must receive 0 for automated test criteria.
- Broken deployment must receive 0 for live deployment/accessibility portions.
- Missing deployment URL is not a hard rejection.
- If no deployment URL is provided, continue evaluation.
- Deployment score should be 0 unless rubric allows Docker/local setup credit.
- Mention missing deployment URL clearly in Weak Points.
- README placeholders, TODO text, fake clone URLs, missing-file references, and template leftovers must reduce README/documentation accuracy points.
- Before final answer, verify that all base rubric row scores sum exactly to the Base Rubric Score.

FULL-SCORE EVIDENCE RULE

This rule applies to every assessment type and every criterion.

For any criterion scored full marks, the evaluator must identify direct evidence in the cloned repository files, results.json, tests, or deployment check.

If the implementation exists but exact correctness is not fully proven from the provided evidence, award partial instead of full.

Do not give full marks based only on:
- README claims
- route names
- file names
- comments
- example responses in documentation
- weak-signal scan observations

Endpoint correctness criteria:
- Full marks require actual endpoint implementations and exact response shapes visible in code.
- README examples are not enough.
- If response shape is close but not exact, award partial.
- If status transitions or validation paths are not fully traceable, award partial.

Results.json criteria:
- Apply results.json scoring only when the assessment prompt or assignment PDF requires results.json.
- For vectorization and data-extractor assignments, results.json must be present, complete, and semantically correct for the required number of inputs or queries.
- For webhook, rate-limiter, and OTP assignments, do not penalize missing results.json unless the selected rubric explicitly requires it.
- If results.json is required and is missing, incomplete, malformed, empty, or not clearly relevant, apply the hard rule from the assessment prompt.

Configuration criteria:
- Full marks require relevant values to be configurable through env vars or config files.
- Hardcoded security values, retry intervals, limits, thresholds, model names, or API settings reduce the score unless the rubric explicitly allows them.
- If only some values are configurable, award partial.

Structured logging criteria:
- Full marks require real structured logging with log levels and useful fields such as event ID, request ID, user identifier, endpoint type, status, decision, or lifecycle stage.
- print(), console.log(), or basic logger messages without structured fields should receive partial or 0.

Concurrency safety criteria:
- Full marks require explicit evidence of locking, transaction, atomic update, compare-and-set, queue-safe design, or another clear race-prevention mechanism.
- Single-threaded async behavior alone should not receive full marks unless the candidate clearly acknowledges and bounds the limitation.

Security criteria:
- Full marks require secure implementation evidence, not only security claims in README.
- Weak default secrets, permissive production CORS, predictable tokens, plaintext sensitive data, missing constant-time comparison, or unsafe external URL handling should reduce security/professionalism points.

Deployment criteria:
- Missing deployment URL is not a hard rejection.
- If no deployment URL is provided, continue evaluating the repository.
- If no deployment URL is provided, deployment score should be 0 unless the rubric allows Docker/local setup credit.
- If deployment URL is checked and returns 500, timeout, DNS failure, or inaccessible response, live deployment credit is 0.
- If deployment is reachable but root path returns 404, check supporting evidence such as /docs, /health, /openapi.json, or assignment-specific endpoints before calling it fully failed.
- Docker or docker-compose credit is allowed only if the actual Dockerfile or docker-compose file exists and is relevant.
- A deployment link in README alone is not enough unless automated deployment evidence confirms it is reachable.

Test criteria:
- No test files = 0.
- Tests that only cover happy path should receive partial at most.
- Full marks require tests that directly cover the rubric’s important behavior.

Documentation / README accuracy criteria:
- README must be consistent with actual files and implementation.
- If README contains TODO placeholders, fake clone URLs, missing-file references, deployment placeholders, or AI/template leftovers, do not give full documentation accuracy.
- If the specific rubric says README accuracy requires zero boilerplate artifacts, then any obvious placeholder or template leftover makes that criterion 0.

SOURCE FILE QUALITY RULE

If fileQuality.hasCriticalFileQualityIssue is true:
- Treat the finding as direct repository evidence.
- Do not give code implementation credit for files marked as README-style, JSON-only, empty, malformed, or misplaced.
- If ingest.py is not a runnable source file, ingestion pipeline criteria must receive 0.
- If server.py is not a runnable source file, retrieval endpoint/API criteria must receive 0.
- If requirements.txt contains application code instead of dependency names, do not count that code as implementation.
- If results.json is required for the selected assessment and is empty, malformed, or contains dependency names instead of expected outputs, results.json quality and results-related criteria must receive 0.
- Do not penalize missing results.json for assessment types where results.json is not required.
- README text cannot rescue broken or misplaced source files.
""".strip()

    webhook_rules = """
WEBHOOK DELIVERY ENGINE CALIBRATION

A1:
- Full only if retry schedule is exactly immediate → 30s → 5min → 30min.
- If schedule differs, is unclear, or has extra/missing retries, award partial or 0.
- If any queue library is used, A1 = 0.

A2:
- Full only if all required endpoints exist, return exact required shapes, and status transitions are implemented correctly.
- If endpoints exist but exact response shape or transitions are unclear, award partial.
- Do not award high A2 from README examples alone.

A3:
- Full only if every outgoing webhook request is signed using HMAC-SHA256, key is configurable, and method is documented.
- If HMAC exists but only partially applied or not configurable, award partial.

A4:
- Full only if non-2xx, timeout, and network error are all handled without crashing.

B1:
- Structured logging requires log levels and meaningful lifecycle logs.
- Simple print or console.log should not get full points.

B2:
- Full only if ports, keys, timeouts, retry intervals, and relevant settings are environment configurable.
- Hardcoded security values or retry values reduce points.

B3:
- SQLite or file-backed persistence earns full if state survives restart.
- In-memory storage only gets partial if README honestly explains restart loss.

B4:
- Full only with clear concurrency protection, locking, transaction, atomic update, or safe design.
- Single-threaded async with no explanation should not get full.

B5:
- Full only if payload is deterministically serialized/canonicalized before signing.

B6:
- Full if routes, delivery engine, storage, config, and worker concerns are separated.

B7:
- No tests = 0.

B8:
- Missing deployment URL = 0 for live deployment.
- Broken deployment URL = 0 for live deployment.
- Docker/docker-compose credit only if file exists and is relevant.

B9:
- Full if clear health/status endpoint beyond required four exists in code.

B10:
- Points only for a dedicated dead-event endpoint or clear filter/query mechanism to list dead events.
- Internal dead status alone is not enough.

B11:
- Full only if event/correlation ID is logged consistently across lifecycle.

B12:
- If README has TODO placeholders, fake clone URLs, deployment placeholders, or missing-file references, B12 = 0.
""".strip()

    rate_limiter_rules = """
CONTEXT-AWARE RATE LIMITER CALIBRATION

A1:
- Full only if all four combinations are enforced exactly: free/AI=5, free/read=30, paid/AI=30, paid/read=120.
- Window must reset correctly after 60 seconds.
- If any rate-limiting library is used, A1 = 0.
- If Redis, database, file storage, or external state is used, A1 + A2 = 0.

A2:
- Full only if middleware intercepts every request.
- X-User-Tier must be used.
- Missing/invalid tier must default to free.
- Endpoint type must come from route-level tag/decorator/metadata, not URL string parsing.
- If endpoint type is parsed from URL, A2 = 0.

A3:
- Full only if 429 response exactly includes error, limit, window_seconds, retry_after_seconds.
- retry_after_seconds must be accurate and never negative.

A4:
- Full only if all four routes exist, return {"ok": true}, and handlers do not contain rate-limit logic.

B1:
- Full only for true sliding window counter/log.
- Fixed window gets partial only if README honestly acknowledges limitation.

B2:
- Full only with locking, atomic operations, or clear no-race design.
- Single-threaded async gets partial only with stated limitation awareness.

B3:
- Full only if key includes tier, endpoint type, and meaningful user identifier.
- Raw IP alone should not get full.

B4:
- Full only for structured logs containing tier, endpoint type, decision, and remaining quota.
- print/console.log alone should not get full.

B5:
- Full only if limits, window, and port are configurable via env vars.
- Hardcoded rule values reduce score.

B6:
- Full only if middleware, store, rules, and routes are separated.

B7:
- No cleanup = 0.
- Passive expiry on access = partial.
- Active cleanup or bounded store = full.

B8:
- No tests = 0.

B9:
- Missing deployment URL = 0 for live deployment.
- Broken deployment URL = 0 for live deployment.
- Docker credit only if Dockerfile/docker-compose exists.

B10:
- Full only if endpoint exposes quota/usage/reset information.
""".strip()

    standard_vector_rules = """
PDF STANDARD VECTORISATION PIPELINE CALIBRATION

A1:
- Full only if ingestion runs end-to-end: PDF text extraction with page numbers, chunking, embedding, and vector DB storage.
- If LangChain, LlamaIndex, or RAG/agent framework is used, A1 = 0.

A2:
- Full only if POST /query returns exact shape {chunk_text, page_number, score}.
- Must use vector similarity search only.
- top_k must be respected.
- Keyword search, SQL LIKE, full-text search, or manual matching makes A2 = 0.

A3:
- If results.json is absent or has fewer than 3 queries, A3 = 0.
- Evaluate relevance directly from results.json.
- Off-topic or random chunks reduce score.

A4:
- README must include setup, chunk size/overlap justification, embedding model justification, and vector DB justification.
- Missing justifications reduce score.

B1:
- Full only if chunking reasoning is tied to token limits and retrieval behavior.
- Arbitrary defaults get 0.

B2:
- Full only if embedding model choice includes tradeoffs such as cost, quality, dimensions, or latency.
- “Used because default/OpenAI” gets 0.

B3:
- Full only if vector DB choice explains persistence, local/hosted tradeoffs, scalability, or operational fit.

B4:
- Use results.json as evidence.
- High scores with irrelevant chunks should be penalized.

B5:
- Full only if metadata includes more than chunk_text and page_number.

B6:
- Full only with content hash, vector ID, or equivalent deduplication.
- Filename-only deduplication is partial.

B7:
- Full only if missing PDF, parse errors, empty pages, and embedding failures are handled gracefully.

B8:
- Full only if parsing, chunking, embedding, storage, and retrieval are modularized.

B9:
- No tests = 0.

B10:
- Missing deployment URL = 0 for live deployment.
- Broken deployment URL = 0 for live deployment.
- Docker credit only if Dockerfile/docker-compose exists.
""".strip()

    langchain_vector_rules = """
LANGCHAIN PDF VECTORISATION PIPELINE CALIBRATION

File-quality caps:
- If ingest.py is README-style content, JSON-only content, missing, or not runnable Python, A1 = 0.
- If server.py is README-style content, JSON-only content, missing, or does not expose a real POST /query endpoint, A2 = 0.
- If results.json is empty, malformed, or not actual query output, A3 = 0 and B4 = 0.
- If LangChain code appears only in README or requirements.txt and not in runnable source files, do not award LangChain implementation points.
- If both A1 and A2 are 0 because source files are invalid, final score should normally not exceed 15 before bonus.

A1:
- Full only if LangChain is used for loader, splitter, embedding integration, and vector store operations.
- If LangChain is not used across these required primitives, A1 = 0.

A2:
- Full only if POST /query calls similarity_search_with_score or equivalent directly on vector store.
- RetrievalQA, ConversationalRetrievalChain, or pre-built RAG chain makes A2 = 0.
- Must return {chunk_text, page_number, score} and respect top_k.

A3:
- If results.json is absent, empty, malformed, or has fewer than 3 queries, A3 = 0.
- Evaluate semantic relevance directly from results.json.

A4:
- README must include setup, requirements.txt, and justification for loader, splitter, embedding model, and vector store.
- If requirements.txt is absent, A4 can receive only partial maximum.

B1:
- LangGraph absent = 0.
- LangGraph present but undocumented/unnamed nodes = partial.
- Named nodes with README diagram or node list = full.
- LangGraph mentioned only in README or requirements.txt but not used in source code = 0.

B2:
- Full only if chunking is justified against token limits and retrieval behavior.
- Arbitrary defaults get 0.

B3:
- Full only if each LangChain component is justified with tradeoffs.
- “Used because easy/example” gets 0.

B4:
- Use results.json as evidence.
- Empty results.json = 0.
- Off-topic chunks or uniformly weak scores reduce score.

B5:
- Full only with document ID, content hash, or store-level deduplication.
- Filename-only deduplication is partial.

B6:
- Full only if metadata includes more than minimum page number.

B7:
- Full only if PDF loading failures, missing files, empty pages, and embedding errors are handled gracefully.

B8:
- Full only if loading, splitting, embedding, vector storage, and retrieval are separated.

B9:
- No tests = 0.

B10:
- Missing deployment URL = 0 for live deployment.
- Broken deployment URL = 0 for live deployment.
- Docker credit only if Dockerfile/docker-compose exists.
""".strip()

    otp_rules = """
ABUSE-RESISTANT OTP SYSTEM CALIBRATION

A1:
- Full only if OTP uses CSPRNG and is stored as bcrypt/SHA-256 hash.
- Plaintext OTP persisted anywhere makes A1 = 0.
- Math.random or Python random makes A1 = 0.
- Authentication libraries such as Passport, NextAuth, Firebase Auth, Django Allauth make A1 = 0.

A2:
- Full only if failed verify increments attempt counter and OTP locks after 5 incorrect attempts with 429.
- If attempts are not persisted/tracked correctly, award partial or 0.

A3:
- Full only if send rate limit is per identifier, max 3 per 10 minutes, returns 429, and resets correctly.
- Per-IP rate limit makes A3 = 0.

A4:
- Full only if success immediately marks code used, expired code after 10 minutes is rejected, and reused code returns 400.

B1:
- Full for bcrypt/Argon2 with reasoning.
- SHA-256 with honest weakness acknowledgement = partial.
- SHA-256 with no acknowledgement = 0.

B2:
- Full only if README honestly explains leaked-table threat and 6-digit brute-force space.
- “Attacker cannot recover code” without reasoning = 0.

B3:
- Full only with constant-time comparison such as hmac.compare_digest or crypto.timingSafeEqual.
- ==, ===, .equals, or naive comparison = 0.

B4:
- Full only with lock, transaction, atomic update, compare-and-set, or equivalent.
- Single-threaded async gets partial only with awareness.

B5:
- Full only if session token uses CSPRNG.
- UUID v4 or timestamp token should not get full.

B6:
- Full only if logging is development-safe and avoids raw OTP in production path.

B7:
- Full only if expiry, rate limits, and hashing parameters are env configurable.

B8:
- Full only if auth, rate limit, storage, and routes are separated.

B9:
- No tests = 0.
- Happy path only = partial.
- Tests covering at least two security rules = full.

B10:
- Missing deployment URL = 0 for live deployment.
- Broken deployment URL = 0 for live deployment.
- Docker credit only if Dockerfile/docker-compose exists.
""".strip()

    data_extractor_rules = """
STRUCTURED DATA EXTRACTOR CALIBRATION

A1:
- Full only if POST /extract always returns exact required shape.
- Every field must include value, confidence, needs_review.
- Top-level review_required must exist.
- If extraction is hardcoded and LLM is not doing extraction, A1 = 0.

A2:
- If confidence scores are identical across all fields in any input, A2 = 0.
- If only one overall confidence score is used, A2 = 0.
- Full only if confidence genuinely varies by field and input ambiguity.

A3:
- Full only if 0.75 needs_review threshold is applied consistently.
- review_required must be true when any field is flagged.

A4:
- If results.json absent or fewer than 5 inputs, A4 = 0.
- If Input 5 crashes or returns 500, A4 = 0.
- Input 5 must return valid shape with null values and low confidence.

B1:
- Full only if prompt explicitly asks for per-field confidence with reasoning/uncertainty calibration.
- Single confidence or vague confidence instruction = 0.

B2:
- Evaluate Inputs 1 and 2 directly from results.json.
- Clean inputs should have correct values, YYYY-MM-DD dates, numeric amounts, and ISO 4217 currency.

B3:
- Input 3 ambiguous date should be lower confidence and flagged.
- Input 4 unusual format should not hallucinate fields or crash.

B4:
- Full only if post-processing normalizes dates, amounts, and currency after LLM response.
- Returning raw “12 March 2024” or “₹1,250” gets 0 for B4.

B5:
- Bare JSON.parse/json.loads with no error handling gets 0.
- Full only if malformed LLM output is caught and handled gracefully.

B6:
- Full only if API key, model name, and confidence threshold are env configurable.
- Hardcoded secrets = 0 or severe penalty.

B7:
- Full only if prompt construction, LLM call, parsing, normalization, and flag logic are separated.

B8:
- Full only if README includes actual prompt or representative excerpt and explains strategy.
- Prose-only strategy = partial.

B9:
- No tests = 0.

B10:
- Missing deployment URL = 0 for live deployment.
- Broken deployment URL = 0 for live deployment.
- Docker credit only if Dockerfile/docker-compose exists.
""".strip()

    specific_rules = {
        "webhook": webhook_rules,
        "rate-limiter": rate_limiter_rules,
        "standard-vectorization": standard_vector_rules,
        "langchain-vectorization": langchain_vector_rules,
        "robust-otp": otp_rules,
        "data-extractor": data_extractor_rules,
    }

    return f"""
{common_rules}

{specific_rules.get(assessment_type, "")}
""".strip()


def get_value_add_bonus_rules(assessment_type: str) -> str:
    common_bonus_rules = """
VALUE-ADD BONUS RULES

Use these rules only after calculating the Base Rubric Score.

Bonus max: 5 points.

The bonus is for useful extra work beyond the assignment PDF/rubric.

Important:
- Bonus must never replace required assignment features.
- Bonus must never be used to fix missing required functionality.
- Bonus must never be awarded for fake or unsupported README claims.
- Feature-based bonus requires actual code/file evidence.
- README-only documentation bonus is allowed, but capped at 1 point.
- Bonus should normally be 0 if the core implementation is mostly non-functional.
- If the core implementation is mostly non-functional but an extra feature is independently working and useful for evaluation, award at most 1 bonus point.
- Bonus should be 0 if the extra feature is only mentioned but not implemented.
- Bonus should be 0 if the extra feature breaks, confuses, or distracts from the core assignment.
- Final Score must be capped at 100.

BONUS CATEGORIES

1. Architecture / Design Documentation Bonus — max 1 point
Award +0.5 to +1 if README or docs include useful architecture/design explanation beyond the minimum.

Examples:
+0.5: Clear architecture explanation showing modules, responsibilities, and data flow.
+0.5: Simple workflow diagram, sequence diagram, request lifecycle, or system design section.
+0.5: Explains design tradeoffs, limitations, and why certain libraries/storage/approaches were chosen.
+0.5: Explains failure scenarios, edge cases, or operational assumptions clearly.

Rules:
- Architecture/design bonus can be given from README/docs even if no extra feature code exists.
- README-only architecture/design bonus is capped at 1 point.
- Do not award this bonus if README has serious placeholders, fake claims, missing-file references, or unsupported architecture claims.

2. Frontend / UI Bonus — max 2 points
Award +1 to +2 for a working frontend or useful UI that helps evaluate the backend/API.

Examples:
+1: Simple UI to call the main API endpoint.
+1.5: UI supports main workflow cleanly with inputs, results, and error display.
+2: Polished UI with multiple relevant screens, clear state handling, and real integration with backend.

Rules:
- Must have actual frontend code or static UI files.
- README screenshots alone are not enough.
- UI must be relevant to the assignment.

3. Dashboard / Admin / Monitoring Bonus — max 2 points
Award +1 to +2 for useful dashboards or admin screens.

Examples:
+1: Basic status/usage/history screen.
+1.5: Shows meaningful internal state such as retries, attempts, quota, confidence, results, or logs.
+2: Useful dashboard with filters, actions, or real-time/recent status.

Rules:
- Must be implemented in code.
- Must help evaluate or operate the assignment.

4. API Documentation / Developer Experience Bonus — max 1 point
Award +0.5 to +1 for developer-friendly usage beyond minimum README.

Examples:
+0.5: Clear request/response examples for all important endpoints.
+0.5: Postman collection, Swagger/OpenAPI examples, curl scripts, or API docs.
+0.5: Clear error examples and expected status codes.
+1: Complete developer guide that makes evaluation easy.

Rules:
- Do not award if examples are fake, inconsistent with code, or copied placeholders.

5. Setup / Docker / One-Command Run Bonus — max 1 point
Award +0.5 to +1 for making the project easy to run.

Examples:
+0.5: Useful setup script, Makefile, npm script, or run script.
+1: Working Dockerfile or docker-compose setup.
+1: Clear one-command local setup with sample data.

Rules:
- Docker/setup files must actually exist.
- README claim alone is not enough.

6. Demo Data / Evaluation Script Bonus — max 1 point
Award +0.5 to +1 for scripts or sample data that help verify the assignment.

Examples:
+0.5: Sample payloads, sample PDF, sample input files, seed data, or demo requests.
+1: Script that runs an end-to-end demo flow.
+1: Script that proves required edge cases.

Rules:
- Must be useful for evaluator.
- Must not replace required tests or results.json.

7. Testing / Verification Bonus — max 1 point
Award +0.5 to +1 for extra testing support beyond rubric expectation.

Examples:
+0.5: Manual test checklist in README.
+0.5: Useful test script or smoke test.
+1: Automated tests covering extra edge cases beyond the minimum rubric.

Rules:
- If base rubric already awards test points, avoid double-counting.
- Bonus only for extra testing quality beyond the base rubric.

8. Error Handling / Validation Bonus — max 1 point
Award +0.5 to +1 for extra robust handling beyond minimum requirements.

Examples:
+0.5: Clear validation messages for bad input.
+0.5: Graceful handling of missing files, invalid payloads, empty inputs, or service errors.
+1: Consistent error model across the API.

Rules:
- Must be implemented in code.
- README claims alone are not enough.

9. Security / Safety Bonus — max 1 point
Award +0.5 to +1 for extra security or safety improvements beyond rubric.

Examples:
+0.5: Safer config handling, no weak defaults, input restrictions, safe CORS, safe URL handling.
+0.5: Avoids leaking secrets, tokens, OTPs, stack traces, or internal errors.
+1: Clear and implemented security hardening relevant to the assignment.

Rules:
- Do not award if security is only claimed in README.
- Do not award if core security requirement is missing.

10. Observability / Logging / Health Bonus — max 1 point
Award +0.5 to +1 for extra operational visibility.

Examples:
+0.5: Health endpoint, status endpoint, or metrics endpoint beyond minimum.
+0.5: Structured logs with request IDs, event IDs, user/tier info, or lifecycle status.
+1: Useful tracing/history that helps debug the assignment flow.

Rules:
- Must be implemented in code.
- Avoid double-counting if the base rubric already has a logging/health criterion.

11. Export / Download / Review Workflow Bonus — max 1 point
Award +0.5 to +1 for helpful evaluator/user workflow.

Examples:
+0.5: Export results as JSON/CSV.
+0.5: Download logs/results/report.
+0.5: Review screen for low-confidence or failed items.
+1: Complete review/export flow relevant to assignment.

12. Performance / Scalability / Concurrency Bonus — max 1 point
Award +0.5 to +1 for extra engineering quality.

Examples:
+0.5: Handles concurrency safely beyond requirement.
+0.5: Efficient batching, cleanup, bounded memory, or cache control.
+1: Clear scalable design without overengineering.

Rules:
- Must be implemented or clearly evidenced in code.
- Do not award for vague README claims.

BONUS SCORING GUIDELINES

Recommended bonus range:
0: No useful extra value.
0.5–1: Good README architecture/design, manual testing notes, or small developer-experience improvement.
1–2: Useful implemented extra feature such as simple frontend, demo script, Docker, or dashboard.
2–3: Multiple useful extras with real implementation evidence.
3–5: Strong extra product-quality work, such as working frontend + dashboard + Docker/demo + strong docs.

Do not double-count:
- If one feature qualifies under multiple categories, award it only once.
- Example: a frontend dashboard should not receive both full frontend bonus and full dashboard bonus unless it clearly has separate functionality.

README-only bonus:
- README-only bonus is capped at 1 point total.
- README-only bonus can be awarded for architecture/design, diagrams, tradeoffs, limitations, manual test cases, or troubleshooting.
- README-only bonus cannot be awarded for unimplemented features.

Final rule:
Value-Add Bonus must be between 0 and 5.
Final Score = min(100, Base Rubric Score + Value-Add Bonus).
""".strip()
    assessment_specific_bonus = {
        "webhook": """
Webhook bonus examples:
+1 to +2: UI/dashboard to view events, attempts, failures, and dead events.
+1: Manual retry button in UI or admin panel.
+1: Webhook delivery history timeline.
+1: Request/response inspector for delivery attempts.
""".strip(),

        "rate-limiter": """
Rate limiter bonus examples:
+1 to +2: UI/dashboard showing current usage, quota, reset time, and tier.
+1: Developer-friendly endpoint to inspect quota status.
+1: Clear visualization of free vs paid limits.
+1: Safe demo script that proves all four rate-limit combinations.
""".strip(),

        "standard-vectorization": """
Standard vectorization bonus examples:
+1 to +2: Frontend to upload/query PDFs and show retrieved chunks.
+1: Highlighted source page/chunk display.
+1: Demo script that runs ingestion and sample queries end-to-end.
+1: Better local persistence or reset/reindex command.
""".strip(),

        "langchain-vectorization": """
LangChain vectorization bonus examples:
+1 to +2: Frontend to upload/query PDFs and show retrieved chunks.
+1: Proper LangGraph workflow visualization if actually implemented in code.
+1: Highlighted source page/chunk display.
+1: Demo script that runs ingestion and sample queries end-to-end.
""".strip(),

        "robust-otp": """
OTP bonus examples:
+1 to +2: Simple frontend/demo UI for sending and verifying OTP.
+1: Admin/debug-safe screen showing rate-limit state without exposing OTP.
+1: Better audit logs without leaking sensitive data.
+1: Demo script proving brute-force and resend-limit behavior.
""".strip(),

        "data-extractor": """
Data extractor bonus examples:
+1 to +2: Frontend to paste messy text and view extracted fields.
+1: Visual highlighting of low-confidence fields.
+1: Export extracted data as JSON/CSV.
+1: Demo script running all sample inputs.
""".strip(),
    }

    return f"""
{common_bonus_rules}

{assessment_specific_bonus.get(assessment_type, "")}
""".strip()


def build_final_assessment_payload(
    repo_evidence: dict,
    assessment_type: str,
    deployment_results: list[dict],
    weak_signal_scan: dict,
    assignment_pdf: dict | None = None,
) -> dict:
    assignment_pdf_evidence = {
        "found": assignment_pdf.get("found") if assignment_pdf else False,
        "fileName": assignment_pdf.get("fileName") if assignment_pdf else None,
        "pageCount": assignment_pdf.get("pageCount") if assignment_pdf else 0,
        "message": assignment_pdf.get("message") if assignment_pdf else "No assignment PDF provided.",
        "combinedText": trim_large_text(
            assignment_pdf.get("combinedText", "") if assignment_pdf else "",
            22000,
        ),
    }

    return {
        "detectedAssessmentType": assessment_type,
        "assignmentPdfEvidence": assignment_pdf_evidence,

        "importantInstruction": {
            "message": (
                "The final evaluator must consider the weak-signal scan and cloned repository evidence. "
                "The weak-signal scan is negative-only supporting evidence and must never increase score. "
                "The final score must be computed from the selected assessment rubric, with optional value-add bonus."
            )
        },

        "repo": {
            "repoFullName": repo_evidence.get("repoFullName"),
            "repoPrivate": repo_evidence.get("repoPrivate"),
            "repoDefaultBranch": repo_evidence.get("repoDefaultBranch"),
            "repoUrl": repo_evidence.get("repoUrl"),
        },

        "submissionStatus": repo_evidence.get("submissionStatus"),

        "weakSignalScan": {
            "assignmentAlignment": weak_signal_scan.get("assignmentAlignment"),
            "weakSignals": weak_signal_scan.get("weakSignals"),
            "mustConsiderInFinalEvaluation": weak_signal_scan.get("mustConsiderInFinalEvaluation"),
            "manualReviewNeeded": weak_signal_scan.get("manualReviewNeeded"),
        },

        "deploymentEvidence": {
            "deploymentUrls": repo_evidence.get("deploymentUrls"),
            "deploymentResults": deployment_results,
        },

        "clonedRepositoryEvidence": {
            "includedFiles": repo_evidence.get("fileList"),
            "fileStats": repo_evidence.get("fileStats"),
            "fileQuality": repo_evidence.get("fileQuality"),
            "readmeText": trim_large_text(repo_evidence.get("readmeText")),
            "packageJsonText": trim_large_text(repo_evidence.get("packageJsonText")),
            "resultsJsonText": trim_large_text(repo_evidence.get("resultsJsonText")),
            "sourceFiles": trim_file_map(repo_evidence.get("sourceFiles")),
            "testFiles": trim_file_map(repo_evidence.get("testFiles")),
            "configFiles": trim_file_map(repo_evidence.get("configFiles")),
            "readmeUrls": repo_evidence.get("readmeUrls"),
        },
    }


def run_final_assessment_evaluation(
    repo_evidence: dict,
    assessment_type: str,
    deployment_results: list[dict],
    weak_signal_scan: dict,
    assignment_pdf: dict | None = None,
) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY missing in .env")

    if assessment_type == "unknown":
        raise ValueError("Cannot run final evaluation because assessment type is unknown.")

    assessment_prompt = load_assessment_prompt(assessment_type)

    payload = build_final_assessment_payload(
        repo_evidence,
        assessment_type,
        deployment_results,
        weak_signal_scan,
        assignment_pdf,
    )

    calibration_rules = get_assessment_calibration_rules(assessment_type)
    value_add_bonus_rules = get_value_add_bonus_rules(assessment_type)

    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
        input=[
            {
                "role": "system",
                "content": f"""
You are a strict but fair senior backend engineer evaluating an internship candidate submission.

You must use four sources of information:

1. The assessment prompt and scoring rubric.
2. The original assignment PDF text.
3. The weak-signal scan result.
4. The cloned repository evidence, including README, source files, config files, test files, package/requirements files, results.json, deployment results, file quality findings, and file list.

Priority order:
1. The assessment prompt is the source of truth for base rubric scoring.
2. The cloned repository evidence is the source of truth for what was actually implemented.
3. The original assignment PDF is the source of truth for what the candidate was asked to build.
4. The weak-signal scan is negative supporting evidence only.

Weak-signal scan usage rules:
- The weak-signal scan must never increase the candidate's score.
- The weak-signal scan must never be used to award points.
- The weak-signal scan has no score, no grade, and no positive signals.
- Use weak-signal scan only to catch problems that may be missed during final evaluation.
- If weak-signal scan reports source files are invalid, README-style, JSON-only, misplaced, empty, or inconsistent, verify from cloned repository evidence and then penalize relevant criteria.
- If weak-signal scan reports empty or invalid results.json, verify from repository evidence and then set results.json-related criteria to 0.
- If weak-signal scan reports missing deployment URL, broken deployment, missing tests, README placeholders, wrong assignment alignment, fake claims, unsupported LangGraph/Docker/test claims, or dependency problems, consider those issues while scoring.
- Do not copy text blindly from weak-signal scan. Use it as a checklist of negative issues to verify.
- Never mention weak-signal scan as a positive reason.

Assignment PDF usage rules:
- Use the assignment PDF to verify what the candidate was actually asked to build.
- Use the evaluator prompt as the base scoring rubric.
- If the evaluator prompt and assignment PDF conflict, follow the evaluator prompt for scoring.
- If the conflict affects fairness, mention it in Weak Points.
- If the repository solves a different assignment than the PDF, heavily penalize relevant criteria.
- If the detected assessment type does not match the assignment PDF, mention it clearly and score only what is actually relevant.
- Do not trust README claims unless code and assignment alignment support them.

Base scoring rules:
- Award base rubric points only for actual code, files, results.json, assignment alignment, and deployment evidence.
- Do not trust README claims unless code or result evidence supports them.
- Do not invent missing endpoints, tests, files, deployment configs, or implementation details.
- If deployment failed or deployment URL is missing, use that evidence for the deployment criterion.
- If no tests were found, use that evidence for the automated tests criterion.
- If README has placeholders or mismatch, use that evidence for README accuracy/documentation criteria.
- If security issues exist, verify them from cloned files before using them in scoring.
- Be strict on required assignment deliverables.
- Be fair with partial credit when a real implementation exists but is incomplete.

Value-add bonus rules:
- Value-add bonus is separate from base rubric score.
- Bonus can reward useful extra work beyond the assignment.
- Bonus must never hide or fix missing required assignment features.
- Bonus requires actual code evidence.
- Bonus must be between 0 and 5.
- Final Score = min(100, Base Rubric Score + Value-Add Bonus).

ASSESSMENT-SPECIFIC CALIBRATION RULES:
{calibration_rules}

VALUE-ADD BONUS RULES:
{value_add_bonus_rules}

Output must include base score, bonus score, final score, strong points, weak points, base score breakdown, and bonus breakdown.
                """.strip(),
            },
            {
                "role": "user",
                "content": f"""
ASSESSMENT PROMPT:
{assessment_prompt}

FULL FINAL EVALUATION EVIDENCE:
{json.dumps(payload, indent=2)}

Now perform the final assessment evaluation strictly but fairly.

Before writing the Overall Score:
1. Review the original assignment PDF evidence.
2. Review the cloned repository evidence.
3. Review the weak-signal scan and verify each relevant issue against repository evidence.
4. Apply the assessment-specific calibration rules.
5. Score each base rubric row using only real implementation evidence.
6. Sum the base rubric rows to calculate Base Rubric Score.
7. Evaluate value-add bonus features separately using only real implementation evidence.
8. Bonus must be between 0 and 5.
9. Final Score = min(100, Base Rubric Score + Value-Add Bonus).
10. Do not use bonus points to cover missing required assignment features.

The final report must use this score format:

Overall Score: <Final Score> / 100
Base Rubric Score: <Base Score> / 100
Value-Add Bonus: <Bonus Score> / 5

Also include:
- Strong Points
- Weak Points
- Score Breakdown table for base rubric rows
- Value-Add Bonus Breakdown table

If no bonus is awarded, show:
Value-Add Bonus: 0 / 5

Return only the final evaluation report.
                """.strip(),
            },
        ],
    )

    return response.output_text