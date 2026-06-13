from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import fitz
except Exception:  # pragma: no cover - dependency is validated at runtime
    fitz = None

try:
    import tiktoken
except Exception:  # pragma: no cover - optional dependency
    tiktoken = None


MAX_PDF_PAGES_PER_DOC_FOR_TEXT = 40
MAX_EXAMPLE_FILES = 24
MAX_EXAMPLE_CHARS_PER_FILE = 12000
CODIERRICHTLINIEN_TXT_NAME = "Codierrichtlinien.txt"
PRIMARY_RULES_TXT_NAME = "SPEC.txt"


@dataclass
class FileTokenInfo:
    path: str
    kind: str
    chars: int
    estimated_tokens: int
    used_in_prompt: bool
    notes: str = ""


@dataclass
class PromptAssembly:
    system_prompt: str
    user_prompt: str
    token_rows: list[FileTokenInfo]
    used_prompt_tokens_est: int
    remaining_input_tokens_est: int
    reserved_output_tokens: int
    num_ctx: int
    spec_context_token_budget: int
    used_spec_tokens_est: int


class RoughTokenizer:
    def __init__(self) -> None:
        self.enc = None
        if tiktoken is not None:
            try:
                self.enc = tiktoken.get_encoding("cl100k_base")
            except Exception:
                self.enc = None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self.enc is not None:
            try:
                return len(self.enc.encode(text))
            except Exception:
                pass
        return max(1, int(len(text) / 4))


class SpecContextService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def _spec_dir_candidates(self, spec_root: Optional[Path] = None) -> list[Path]:
        if spec_root is not None:
            return [spec_root]
        return [
            self.project_root / "spec",
            self.project_root / "specs",
            self.project_root / "Spec",
            self.project_root / "Specs",
        ]

    @staticmethod
    def _find_first_existing_dir(paths: list[Path]) -> Optional[Path]:
        for path in paths:
            if path.exists() and path.is_dir():
                return path
        return None

    def discover_spec_dirs(
        self,
        spec_root: Optional[Path] = None,
    ) -> tuple[Optional[Path], Optional[Path], Optional[Path], list[Path]]:
        root_spec = self._find_first_existing_dir(self._spec_dir_candidates(spec_root))
        if not root_spec:
            return None, None, None, []

        pdf_dir = self._find_first_existing_dir(
            [root_spec / name for name in ["pdfs", "PDFs", "Pdfs"]]
        )
        reports_dir = self._find_first_existing_dir(
            [root_spec / name for name in ["reports", "resports", "Reports", "Resports", "txt"]]
        )
        pdf_txt_dir = self._find_first_existing_dir(
            [root_spec / name for name in ["pdfs-txt", "pdfs_txt", "PDFS-TXT", "PDFS_TXT"]]
        )
        return pdf_dir, reports_dir, pdf_txt_dir, [root_spec]

    @staticmethod
    def _normalize_name(path: Path) -> str:
        return path.stem.lower().replace("_", " ").replace("-", " ")

    @staticmethod
    def _read_text_file(path: Path, max_chars: Optional[int] = None) -> str:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if max_chars is not None and len(text) > max_chars:
            return text[:max_chars] + "\n\n[TRUNCATED]"
        return text

    @staticmethod
    def _pdf_to_text(pdf_path: Path, max_pages: int = MAX_PDF_PAGES_PER_DOC_FOR_TEXT) -> str:
        if fitz is None:
            raise RuntimeError("PyMuPDF is required for PDF ingestion. Install pymupdf.")

        chunks: list[str] = []
        with fitz.open(pdf_path) as doc:
            page_count = min(len(doc), max_pages)
            for index in range(page_count):
                page = doc.load_page(index)
                text = page.get_text("text")
                if text.strip():
                    chunks.append(f"\n--- PAGE {index + 1} ---\n{text}")
        return "\n".join(chunks).strip()

    @staticmethod
    def _get_codierrichtlinien_txt_path(pdf_txt_dir: Optional[Path]) -> Optional[Path]:
        if not pdf_txt_dir:
            return None
        path = pdf_txt_dir / CODIERRICHTLINIEN_TXT_NAME
        return path if path.exists() and path.is_file() else None

    @staticmethod
    def _get_primary_rules_txt_path(reports_dir: Optional[Path]) -> Optional[Path]:
        if not reports_dir:
            return None
        path = reports_dir / PRIMARY_RULES_TXT_NAME
        return path if path.exists() and path.is_file() else None

    def get_key_pdfs(self, pdf_dir: Optional[Path]) -> tuple[list[Path], list[Path]]:
        if not pdf_dir:
            return [], []

        cheatsheet: list[Path] = []
        priority: list[Path] = []
        others: list[Path] = []
        for path in sorted(pdf_dir.glob("*.pdf")):
            normalized = self._normalize_name(path)
            if "cheatsheet" in normalized:
                cheatsheet.append(path)
            elif "coding guideline" in normalized or "richtlinien" in normalized:
                priority.append(path)
            else:
                others.append(path)
        return cheatsheet + priority, others

    def scan_token_usage(self, spec_root: Optional[Path] = None) -> tuple[list[FileTokenInfo], str]:
        tokenizer = RoughTokenizer()
        pdf_dir, reports_dir, pdf_txt_dir, spec_roots = self.discover_spec_dirs(spec_root)
        rows: list[FileTokenInfo] = []
        notes: list[str] = []

        if not spec_roots:
            if spec_root:
                return [], f"Spec source not found: {spec_root}"
            return [], "No spec/Spec/specs/Specs directory found in the project root."

        if pdf_dir:
            priority_pdfs, other_pdfs = self.get_key_pdfs(pdf_dir)
            for path in priority_pdfs + other_pdfs:
                try:
                    text = self._pdf_to_text(path)
                    rows.append(
                        FileTokenInfo(
                            path=str(path),
                            kind="pdf",
                            chars=len(text),
                            estimated_tokens=tokenizer.count(text),
                            used_in_prompt=False,
                            notes="priority pdf" if path in priority_pdfs else "pdf",
                        )
                    )
                except Exception as exc:
                    rows.append(FileTokenInfo(str(path), "pdf", 0, 0, False, f"read error: {exc}"))
        else:
            notes.append("No specs/pdfs directory found.")

        codierrichtlinien_txt = self._get_codierrichtlinien_txt_path(pdf_txt_dir)
        if codierrichtlinien_txt:
            try:
                text = self._read_text_file(codierrichtlinien_txt)
                rows.append(
                    FileTokenInfo(
                        path=str(codierrichtlinien_txt),
                        kind="txt-guideline",
                        chars=len(text),
                        estimated_tokens=tokenizer.count(text),
                        used_in_prompt=False,
                        notes="secondary priority coding guidelines text",
                    )
                )
            except Exception as exc:
                rows.append(
                    FileTokenInfo(
                        str(codierrichtlinien_txt),
                        "txt-guideline",
                        0,
                        0,
                        False,
                        f"read error: {exc}",
                    )
                )
        else:
            notes.append(f"No {spec_roots[0]}/pdfs-txt/Codierrichtlinien.txt found.")

        primary_rules_txt = self._get_primary_rules_txt_path(reports_dir)
        if primary_rules_txt:
            try:
                text = self._read_text_file(primary_rules_txt)
                rows.append(
                    FileTokenInfo(
                        path=str(primary_rules_txt),
                        kind="txt-primary-rules",
                        chars=len(text),
                        estimated_tokens=tokenizer.count(text),
                        used_in_prompt=False,
                        notes="first priority QScript rules",
                    )
                )
            except Exception as exc:
                rows.append(
                    FileTokenInfo(
                        str(primary_rules_txt),
                        "txt-primary-rules",
                        0,
                        0,
                        False,
                        f"read error: {exc}",
                    )
                )
        else:
            notes.append(f"No reports/{PRIMARY_RULES_TXT_NAME} found.")

        if reports_dir:
            for path in sorted(reports_dir.glob("*.txt")):
                if primary_rules_txt and path == primary_rules_txt:
                    continue
                try:
                    text = self._read_text_file(path, max_chars=MAX_EXAMPLE_CHARS_PER_FILE)
                    rows.append(
                        FileTokenInfo(
                            path=str(path),
                            kind="txt-shot",
                            chars=len(text),
                            estimated_tokens=tokenizer.count(text),
                            used_in_prompt=False,
                            notes="few-shot example",
                        )
                    )
                except Exception as exc:
                    rows.append(FileTokenInfo(str(path), "txt-shot", 0, 0, False, f"read error: {exc}"))
        else:
            notes.append("No reports/resports directory found.")

        return rows, " ".join(notes) if notes else "Spec directories found successfully."

    @staticmethod
    def build_system_prompt() -> str:
        return (
            "You are a coding assistant connected to local specification files. "
            "The first priority source is reports/SPEC.txt when provided; generated QScript code must follow those rules. "
            "Then use the Cheatsheet and priority PDFs as supporting sources of truth. "
            "Then follow the coding rules from the provided Codierrichtlinien text. "
            "Use the .txt report files as many-shot examples for style, patterns, and allowed constructs. "
            "All QScript functions must live inside one FhClass block. "
            "Write the FhClass declaration as SET FORMCLASS FhClass [ and keep that square bracket block open around the entire following function list. "
            "Do not close the FhClass square bracket block until after the final function. "
            "Use oninitshow as the start trigger function. "
            "If information is missing, encode the safest reasonable implementation instead of inventing spec facts. "
            "Return exactly one final source output. "
            "Return the marker FINAL_ANSWER_SOURCE on its own line, then the final source code. "
            "Do not use Markdown fences. "
            "Do not include HTML. "
            "Do not use placeholder text. "
            "Do not include <think> tags, thinking, analysis, explanations, summaries, or closing notes. "
            "Do not repeat the code. "
            "Do not omit trailing functions, classes, or closing braces. "
            "Preserve indentation exactly. "
            "Return complete source files without shortening."
        )

    @staticmethod
    def _conversation_section(history: list[dict[str, str]], max_messages: int = 8) -> str:
        if not history:
            return ""
        lines = ["# RECENT CHAT CONTEXT"]
        for item in history[-max_messages:]:
            role = item.get("role", "user")
            content = item.get("content", "").strip()
            if content:
                lines.append(f"{role.upper()}:\n{content}")
        return "\n\n".join(lines)

    def assemble_prompt(
        self,
        user_message: str,
        history: list[dict[str, str]],
        num_ctx: int,
        reserve_output_tokens: int,
        spec_root: Optional[Path] = None,
        spec_token_budget: Optional[int] = None,
    ) -> PromptAssembly:
        tokenizer = RoughTokenizer()
        token_rows, _ = self.scan_token_usage(spec_root)

        system_prompt = self.build_system_prompt()
        base_budget = max(1024, num_ctx - reserve_output_tokens)
        requested_spec_budget = spec_token_budget if spec_token_budget and spec_token_budget > 0 else base_budget
        conversation_context = self._conversation_section(history)
        used_tokens = (
            tokenizer.count(system_prompt)
            + tokenizer.count(user_message)
            + tokenizer.count(conversation_context)
        )
        available_for_specs = max(0, base_budget - used_tokens)
        spec_context_budget = min(requested_spec_budget, available_for_specs)
        used_spec_tokens = 0

        sections = [
            "# USER REQUEST\n"
            + user_message.strip()
            + "\n\nReturn format:\n"
            + "FINAL_ANSWER_SOURCE\n"
            + "<actual final source code only>\n\n"
            + "Do not output placeholder text. Do not output Markdown fences. Do not output <think> tags."
        ]
        if conversation_context:
            sections.append(conversation_context)

        pdf_dir, reports_dir, pdf_txt_dir, _ = self.discover_spec_dirs(spec_root)
        priority_pdfs, other_pdfs = self.get_key_pdfs(pdf_dir)
        primary_rules_txt = self._get_primary_rules_txt_path(reports_dir)
        codierrichtlinien_txt = self._get_codierrichtlinien_txt_path(pdf_txt_dir)

        def mark_used(path: Path, note: str = "") -> None:
            for row in token_rows:
                if row.path == str(path):
                    row.used_in_prompt = True
                    if note:
                        row.notes = (row.notes + "; " + note).strip("; ")

        def spec_remaining() -> int:
            return max(0, min(base_budget - used_tokens, spec_context_budget - used_spec_tokens))

        def include_spec_block(title: str, path: Path, text: str, full_note: str, truncated_note: str) -> bool:
            nonlocal used_tokens, used_spec_tokens
            block = f"\n# {title}: {path.name}\n{text}"
            tokens = tokenizer.count(block)
            if tokens <= spec_remaining():
                sections.append(block)
                used_tokens += tokens
                used_spec_tokens += tokens
                mark_used(path, full_note)
                return True

            remaining = spec_remaining()
            if remaining < 300:
                return False

            partial = text[: max(1000, remaining * 4)]
            truncated_block = f"\n# {title} (TRUNCATED): {path.name}\n{partial}\n\n[TRUNCATED]"
            truncated_tokens = tokenizer.count(truncated_block)
            while truncated_tokens > spec_remaining() and len(partial) > 1000:
                partial = partial[: int(len(partial) * 0.8)]
                truncated_block = f"\n# {title} (TRUNCATED): {path.name}\n{partial}\n\n[TRUNCATED]"
                truncated_tokens = tokenizer.count(truncated_block)
            if truncated_tokens > spec_remaining():
                return False
            sections.append(truncated_block)
            used_tokens += truncated_tokens
            used_spec_tokens += truncated_tokens
            mark_used(path, truncated_note)
            return False

        if primary_rules_txt:
            text = self._read_text_file(primary_rules_txt)
            include_spec_block(
                "FIRST PRIORITY QSCRIPT RULES",
                primary_rules_txt,
                text,
                "included full first priority QScript rules",
                "included truncated first priority QScript rules",
            )

        for path in priority_pdfs:
            text = self._pdf_to_text(path)
            if not include_spec_block(
                "PRIORITY PDF",
                path,
                text,
                "included full extracted text",
                "included truncated extracted text",
            ):
                break

        if codierrichtlinien_txt:
            text = self._read_text_file(codierrichtlinien_txt)
            include_spec_block(
                "PRIORITY CODIERRICHTLINIEN TXT",
                codierrichtlinien_txt,
                text,
                "included full coding guidelines text",
                "included truncated coding guidelines text",
            )

        for path in other_pdfs:
            text = self._pdf_to_text(path)
            block = f"\n# ADDITIONAL PDF: {path.name}\n{text}"
            tokens = tokenizer.count(block)
            if tokens > spec_remaining():
                continue
            sections.append(block)
            used_tokens += tokens
            used_spec_tokens += tokens
            mark_used(path, "included full extracted text")

        if reports_dir:
            example_blocks: list[str] = []
            for path in sorted(reports_dir.glob("*.txt"))[:MAX_EXAMPLE_FILES]:
                if primary_rules_txt and path == primary_rules_txt:
                    continue
                text = self._read_text_file(path, max_chars=MAX_EXAMPLE_CHARS_PER_FILE)
                block = f"\n## EXAMPLE: {path.name}\n{text}"
                tokens = tokenizer.count(block)
                if tokens > spec_remaining():
                    remaining = spec_remaining()
                    if remaining < 300:
                        break
                    partial = block[: remaining * 4]
                    truncated_example = partial + "\n\n[TRUNCATED]"
                    partial_tokens = tokenizer.count(truncated_example)
                    while partial_tokens > spec_remaining() and len(partial) > 1000:
                        partial = partial[: int(len(partial) * 0.8)]
                        truncated_example = partial + "\n\n[TRUNCATED]"
                        partial_tokens = tokenizer.count(truncated_example)
                    if partial_tokens > spec_remaining():
                        break
                    example_blocks.append(truncated_example)
                    used_tokens += partial_tokens
                    used_spec_tokens += partial_tokens
                    mark_used(path, "included truncated example")
                    break
                example_blocks.append(block)
                used_tokens += tokens
                used_spec_tokens += tokens
                mark_used(path, "included example")
            if example_blocks:
                sections.append("\n# MANY-SHOT EXAMPLES\n" + "\n".join(example_blocks))

        return PromptAssembly(
            system_prompt=system_prompt,
            user_prompt="\n\n".join(sections),
            token_rows=token_rows,
            used_prompt_tokens_est=used_tokens,
            remaining_input_tokens_est=max(0, base_budget - used_tokens),
            reserved_output_tokens=reserve_output_tokens,
            num_ctx=num_ctx,
            spec_context_token_budget=spec_context_budget,
            used_spec_tokens_est=used_spec_tokens,
        )


def render_token_report(assembly: PromptAssembly, base_url: str, model_name: str, extra: str = "") -> str:
    def row_priority(row: FileTokenInfo) -> tuple[bool, int, int]:
        kind_order = {
            "txt-primary-rules": 0,
            "pdf": 1,
            "txt-guideline": 2,
            "txt-shot": 3,
        }
        return (not row.used_in_prompt, kind_order.get(row.kind, 9), -row.estimated_tokens)

    rows = sorted(assembly.token_rows, key=row_priority)
    lines = [
        "backend: OpenAI-compatible model server",
        f"base_url: {base_url}",
        f"model: {model_name}",
        f"num_ctx_budget: {assembly.num_ctx}",
        f"reserved_output_tokens: {assembly.reserved_output_tokens}",
        f"spec_context_token_budget: {assembly.spec_context_token_budget}",
        f"estimated_used_spec_tokens: {assembly.used_spec_tokens_est}",
        f"estimated_used_prompt_tokens: {assembly.used_prompt_tokens_est}",
        f"estimated_remaining_input_tokens: {assembly.remaining_input_tokens_est}",
    ]
    if extra:
        lines.append(extra)
    lines.append("\nPer-file token estimate:")
    for row in rows:
        status = "USED" if row.used_in_prompt else "SKIPPED"
        lines.append(
            f"- [{status}] {row.kind} | tok~{row.estimated_tokens:>6} | chars={row.chars:>7} | {row.path}"
            + (f" | {row.notes}" if row.notes else "")
        )
    return "\n".join(lines)
