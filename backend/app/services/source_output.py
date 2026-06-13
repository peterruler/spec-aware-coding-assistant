import re
from datetime import datetime
from pathlib import Path
from typing import Optional


CONTINUE_TAIL_CHARS = 2000


def sanitize_filename_part(value: str, fallback: str = "program", max_len: int = 48) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        value = fallback
    return value[:max_len].strip("_") or fallback


def extract_program_keyword(user_message: str) -> str:
    text = user_message.strip()
    filename_match = re.search(
        r"\b([a-zA-Z0-9_\-.]+\.(?:py|js|ts|tsx|jsx|java|cs|cpp|c|h|hpp|rs|go|php|rb|sql|xml|json|yaml|yml|sh|bash|txt|md|html|css))\b",
        text,
    )
    if filename_match:
        return sanitize_filename_part(filename_match.group(1))

    quoted_match = re.search(r"[\"'`]{1}([a-zA-Z0-9_\-. ]{3,80})[\"'`]{1}", text)
    if quoted_match:
        return sanitize_filename_part(quoted_match.group(1))

    patterns = [
        r"(?:program|script|app|application|tool|module|file|source|src|code)\s+(?:called|named|for|to|that)?\s*([a-zA-Z0-9_\-.]{3,64})",
        r"(?:create|generate|write|build|implement)\s+(?:a|an|the)?\s*([a-zA-Z0-9_\-.]{3,64})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            keyword = sanitize_filename_part(match.group(1))
            if keyword not in {"the", "for", "with", "source", "code", "file", "program"}:
                return keyword

    words = re.findall(r"[a-zA-Z0-9]{3,}", text)
    stop_words = {
        "create",
        "generate",
        "write",
        "build",
        "implement",
        "please",
        "source",
        "code",
        "file",
        "program",
        "script",
        "using",
        "with",
        "from",
        "based",
        "spec",
        "specs",
        "qscript",
        "output",
        "return",
        "complete",
        "full",
        "only",
        "plain",
        "final",
        "show",
        "give",
        "make",
        "need",
        "want",
    }
    for word in words:
        if word.lower() not in stop_words:
            return sanitize_filename_part(word)
    return "program"


def dedupe_exact_repeated_text(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    for repeat_count in range(12, 1, -1):
        if len(text) % repeat_count != 0:
            continue
        part_len = len(text) // repeat_count
        part = text[:part_len]
        if part and part * repeat_count == text:
            return part.strip()
    return text


def strip_thinking(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(?is)<think>.*?</think>", "", text)
    text = re.sub(r"(?is)^.*?</think>", "", text)
    return text.strip()


def extract_source_only(text: str) -> str:
    if not text:
        return ""

    text = strip_thinking(text)
    marker_match = re.search(r"(?is)FINAL_ANSWER_SOURCE\s*(.*)$", text)
    if marker_match:
        text = marker_match.group(1).strip()

    fenced_blocks = re.findall(
        r"```[a-zA-Z0-9_+\-.#]*\s*\n(.*?)\n```",
        text,
        flags=re.DOTALL,
    )
    if fenced_blocks:
        blocks = [block.strip() for block in fenced_blocks if block.strip()]
        if blocks:
            return dedupe_exact_repeated_text(blocks[-1]).rstrip() + "\n"

    text = re.sub(
        r"^\s*(?:sure|here(?:'s| is)|below is|this is|the following is)[^\n]*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(
        r"\n\s*(?:explanation|notes?|summary)\s*:\s*.*$",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    text = text.replace("FINAL_ANSWER_SOURCE", "").strip()

    placeholder_values = {
        "source code here",
        "<actual final source code only>",
        "actual final source code only",
    }
    if text.strip().lower() in placeholder_values:
        return ""
    return dedupe_exact_repeated_text(text).rstrip() + "\n"


def force_crlf_line_endings(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return text.replace("\n", "\r\n")


def save_generated_txt(
    content: str,
    user_message: str,
    generated_dir: Path,
    prefix: str = "source",
) -> Optional[str]:
    plain_text = extract_source_only(content)
    if not plain_text.strip():
        return None

    generated_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    keyword = extract_program_keyword(user_message)
    path = generated_dir / f"{timestamp}_{keyword}_{prefix}.txt"
    path.write_text(force_crlf_line_endings(plain_text), encoding="utf-8", newline="")
    return str(path)

