def get_text(value) -> str:
    if not value:
        return ""

    if isinstance(value, dict):
        return "\n".join(str(item) for item in value.values())

    if isinstance(value, list):
        return "\n".join(str(item) for item in value)

    return str(value)


def contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def build_repo_corpus(repo_evidence: dict) -> dict:
    readme_text = get_text(repo_evidence.get("readmeText")).lower()
    package_json_text = get_text(repo_evidence.get("packageJsonText")).lower()
    results_json_text = get_text(repo_evidence.get("resultsJsonText")).lower()
    file_list_text = get_text(repo_evidence.get("fileList")).lower()

    source_files_text = get_text(repo_evidence.get("sourceFiles")).lower()
    test_files_text = get_text(repo_evidence.get("testFiles")).lower()
    config_files_text = get_text(repo_evidence.get("configFiles")).lower()

    full_text = "\n".join([
        readme_text,
        package_json_text,
        results_json_text,
        file_list_text,
        source_files_text,
        test_files_text,
        config_files_text,
    ])

    code_text = "\n".join([
        package_json_text,
        source_files_text,
        config_files_text,
        file_list_text,
    ])

    return {
        "readme": readme_text,
        "package": package_json_text,
        "results": results_json_text,
        "files": file_list_text,
        "source": source_files_text,
        "tests": test_files_text,
        "config": config_files_text,
        "full": full_text,
        "code": code_text,
    }


def add_score(scores: dict, assessment_type: str, points: int, reason: str):
    scores[assessment_type]["score"] += points
    scores[assessment_type]["evidence"].append(reason)


def detect_assessment_type_with_evidence(repo_evidence: dict) -> dict:
    corpus = build_repo_corpus(repo_evidence)
    full = corpus["full"]
    code = corpus["code"]
    readme = corpus["readme"]
    files = corpus["files"]
    results = corpus["results"]

    scores = {
        "webhook": {"score": 0, "evidence": []},
        "rate-limiter": {"score": 0, "evidence": []},
        "standard-vectorization": {"score": 0, "evidence": []},
        "langchain-vectorization": {"score": 0, "evidence": []},
        "robust-otp": {"score": 0, "evidence": []},
        "data-extractor": {"score": 0, "evidence": []},
    }

    # Webhook
    if contains_any(full, ["webhook delivery engine", "webhook delivery", "webhook"]):
        add_score(scores, "webhook", 20, "Webhook wording found.")
    if contains_any(full, ["hmac-sha256", "hmac sha256", "x-signature", "signature"]):
        add_score(scores, "webhook", 15, "HMAC/signature evidence found.")
    if contains_any(full, ["retry schedule", "dead event", "delivery attempt", "next_attempt_at"]):
        add_score(scores, "webhook", 15, "Retry/dead-event delivery evidence found.")
    if contains_any(code, ["/events", "delivery.py", "webhook_url", "attempt"]):
        add_score(scores, "webhook", 10, "Webhook route/code evidence found.")

    # Rate limiter
    if contains_any(full, ["context-aware rate limiter", "context aware rate limiter", "rate limiter"]):
        add_score(scores, "rate-limiter", 20, "Rate limiter wording found.")
    if contains_any(full, ["x-user-tier", "rate_limit_exceeded", "retry_after_seconds"]):
        add_score(scores, "rate-limiter", 25, "Required rate-limiter response/header evidence found.")
    if contains_any(full, ["/ai/generate", "/ai/summarise", "/data/list", "/data/export"]):
        add_score(scores, "rate-limiter", 20, "Required rate-limiter routes found.")
    if contains_any(full, ["free", "paid", "endpoint type", "window_seconds"]):
        add_score(scores, "rate-limiter", 10, "Tier/window rule evidence found.")

    # Robust OTP
    if contains_any(full, ["abuse-resistant otp", "abuse resistant otp", "otp"]):
        add_score(scores, "robust-otp", 20, "OTP wording found.")
    if contains_any(full, ["brute-force", "brute force", "verify otp", "send otp"]):
        add_score(scores, "robust-otp", 15, "OTP send/verify/brute-force evidence found.")
    if contains_any(full, ["constant-time", "constant time", "timingsafeequal", "compare_digest"]):
        add_score(scores, "robust-otp", 15, "Constant-time comparison evidence found.")
    if contains_any(full, ["bcrypt", "sha-256", "sha256", "hashed otp", "code invalidation"]):
        add_score(scores, "robust-otp", 15, "OTP hashing/invalidation evidence found.")

    # Data extractor
    if contains_any(full, ["structured data extractor", "data extractor"]):
        add_score(scores, "data-extractor", 20, "Data extractor wording found.")
    if contains_any(full, ["/extract", "extract endpoint"]):
        add_score(scores, "data-extractor", 20, "Extract endpoint evidence found.")
    if contains_any(full, ["needs_review", "review_required", "per-field confidence", "per field confidence"]):
        add_score(scores, "data-extractor", 25, "Confidence/review flag evidence found.")
    if contains_any(full, ["invoice_number", "amount", "currency", "date"]):
        add_score(scores, "data-extractor", 10, "Structured extraction field evidence found.")

    # Vectorization common
    vector_common = contains_any(full, [
        "vectorisation",
        "vectorization",
        "pdf vectorisation",
        "pdf vectorization",
        "chunk_text",
        "page_number",
        "top_k",
        "/query",
        "embedding",
        "vector db",
        "vector database",
        "similarity search",
    ])

    # LangChain vectorization
    if vector_common:
        add_score(scores, "standard-vectorization", 10, "Generic vectorization evidence found.")
        add_score(scores, "langchain-vectorization", 10, "Generic vectorization evidence found.")

    langchain_positive = [
        "pdf vectorisation pipeline (langchain)",
        "pdf vectorization pipeline (langchain)",
        "langchain primitives",
        "langchain document loaders",
        "pypdfloader",
        "recursivecharactertextsplitter",
        "huggingfaceembeddings",
        "similarity_search_with_score",
        "langchain_community",
        "langchain_core",
        "langchain_chroma",
        "langchain_huggingface",
        "from langchain",
        "import langchain",
    ]

    if contains_any(full, langchain_positive):
        add_score(scores, "langchain-vectorization", 35, "LangChain implementation/assignment evidence found.")

    if contains_any(full, ["langgraph", "stategraph"]):
        add_score(scores, "langchain-vectorization", 10, "LangGraph evidence found.")

    # Standard vectorization
    standard_negative_langchain = [
        "no langchain",
        "without langchain",
        "do not use langchain",
        "don't use langchain",
        "must not use langchain",
        "langchain is not allowed",
        "no langchain/llamaindex",
        "no langchain / llamaindex",
        "no rag framework",
        "no rag frameworks",
        "do not use rag framework",
        "without rag framework",
    ]

    if contains_any(full, standard_negative_langchain):
        add_score(scores, "standard-vectorization", 40, "No-LangChain / no-RAG constraint found.")

    if contains_any(code, [
        "chromadb",
        "sentence_transformers",
        "sentence-transformers",
        "pymupdf",
        "import fitz",
        "pdfplumber",
        "collection.query",
        "collection.add",
    ]) and not contains_any(code, langchain_positive):
        add_score(scores, "standard-vectorization", 15, "Raw non-LangChain vector implementation evidence found.")

    # Penalize vector false positives
    if contains_any(full, standard_negative_langchain):
        scores["langchain-vectorization"]["score"] -= 30
        scores["langchain-vectorization"]["evidence"].append(
            "Penalty: text says LangChain is not allowed."
        )

    # Pick winner
    sorted_scores = sorted(
        scores.items(),
        key=lambda item: item[1]["score"],
        reverse=True,
    )

    best_type, best_data = sorted_scores[0]
    second_type, second_data = sorted_scores[1]

    best_score = best_data["score"]
    second_score = second_data["score"]

    if best_score < 20:
        return {
            "assessmentType": "unknown",
            "confidence": "low",
            "score": best_score,
            "secondBest": second_type,
            "secondScore": second_score,
            "scores": scores,
            "reason": "No strong assessment markers found.",
        }

    if best_score - second_score < 10:
        return {
            "assessmentType": best_type,
            "confidence": "medium",
            "score": best_score,
            "secondBest": second_type,
            "secondScore": second_score,
            "scores": scores,
            "reason": "Assessment type detected, but second-best score is close.",
        }

    return {
        "assessmentType": best_type,
        "confidence": "high",
        "score": best_score,
        "secondBest": second_type,
        "secondScore": second_score,
        "scores": scores,
        "reason": "Assessment type detected from strong repository evidence.",
    }


def detect_assessment_type(repo_evidence: dict) -> str:
    result = detect_assessment_type_with_evidence(repo_evidence)
    return result["assessmentType"]