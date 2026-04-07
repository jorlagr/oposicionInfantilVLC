#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import fitz


HEADER_PATTERNS = (
    "TEST TEMA",
)


def compact_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:?)])", r"\1", text)
    text = re.sub(r"([¿(])\s+", r"\1", text)
    return text


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def is_bold_font(font_name: str | None) -> bool:
    return "bold" in (font_name or "").lower()


def has_meaningful_text(text: str) -> bool:
    return bool(re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]", text))


def extract_lines(pdf_path: Path) -> list[dict]:
    doc = fitz.open(pdf_path)
    lines = []

    for page in doc:
        data = page.get_text("dict")
        for block in data["blocks"]:
            for line in block.get("lines", []):
                spans = []
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text or not text.strip():
                        continue
                    spans.append(
                        {
                            "text": compact_text(text),
                            "bold": is_bold_font(span.get("font")),
                        }
                    )

                if not spans:
                    continue

                text = compact_text(" ".join(span["text"] for span in spans))
                if not text:
                    continue

                if text.isdigit():
                    continue

                if any(text.startswith(pattern) for pattern in HEADER_PATTERNS):
                    continue

                lines.append(
                    {
                        "text": text,
                        "bold": any(span["bold"] and has_meaningful_text(span["text"]) for span in spans),
                    }
                )

    return lines


def build_exam_from_pdf(pdf_path: Path, exam_id: str, title: str | None) -> dict:
    lines = extract_lines(pdf_path)
    if not lines:
        raise ValueError(f"No se ha podido extraer texto de {pdf_path.name}.")

    question_pattern = re.compile(r"^(\d+)\.\s*(.+)$")
    option_pattern = re.compile(r"^([a-dA-D])(?:[.)-]|\s)\s*(.+)$")

    questions = []
    current_question_number = None
    current_question_parts: list[str] = []
    current_options: list[dict] = []

    def flush_question() -> None:
        nonlocal current_question_number, current_question_parts, current_options
        if current_question_number is None:
            return

        if len(current_options) != 4:
            raise ValueError(
                f"La pregunta {current_question_number} no tiene 4 opciones en {pdf_path.name}."
            )

        correct_options = [option["id"] for option in current_options if option["isCorrect"]]
        if len(correct_options) != 1:
            raise ValueError(
                f"La pregunta {current_question_number} no tiene una única opción en negrita."
            )

        questions.append(
            {
                "id": f"q{current_question_number}",
                "number": current_question_number,
                "text": compact_text(" ".join(current_question_parts)),
                "options": [
                    {
                        "id": option["id"],
                        "text": compact_text(option["text"]),
                    }
                    for option in current_options
                ],
                "correctOption": correct_options[0],
            }
        )

        current_question_number = None
        current_question_parts = []
        current_options = []

    for line in lines:
        question_match = question_pattern.match(line["text"])
        if question_match:
            flush_question()
            current_question_number = int(question_match.group(1))
            current_question_parts = [question_match.group(2)]
            continue

        option_match = option_pattern.match(line["text"])
        if option_match and current_question_number is not None:
            current_options.append(
                {
                    "id": option_match.group(1).lower(),
                    "text": option_match.group(2),
                    "isCorrect": line["bold"],
                }
            )
            continue

        if current_options:
            current_options[-1]["text"] = f"{current_options[-1]['text']} {line['text']}"
            current_options[-1]["isCorrect"] = current_options[-1]["isCorrect"] or line["bold"]
            continue

        if current_question_number is not None:
            current_question_parts.append(line["text"])

    flush_question()

    if not questions:
        raise ValueError(f"No se han encontrado preguntas válidas en {pdf_path.name}.")

    return {
        "id": exam_id,
        "title": title or pdf_path.stem,
        "source": {
            "questionsPdf": str(pdf_path),
            "answersPdf": str(pdf_path),
        },
        "questionCount": len(questions),
        "questions": questions,
    }


def load_existing_payload(output_path: Path) -> dict:
    if not output_path.exists():
        return {"exams": []}

    raw = output_path.read_text(encoding="utf-8").strip()
    prefix = "window.TEST_APP_DATA = "
    suffix = ";"
    if not raw.startswith(prefix) or not raw.endswith(suffix):
        raise ValueError("El archivo de salida no tiene el formato esperado.")

    return json.loads(raw[len(prefix) : -len(suffix)])


def merge_payload(existing_payload: dict, new_exam: dict) -> dict:
    exams = [exam for exam in existing_payload.get("exams", []) if exam.get("id") != new_exam["id"]]
    exams.append(new_exam)
    exams.sort(key=lambda exam: exam.get("title", ""))
    return {"exams": exams}


def write_output(payload: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = "window.TEST_APP_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    output_path.write_text(output, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa un examen desde un PDF con la respuesta correcta en negrita."
    )
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--exam-id")
    parser.add_argument("--title")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Añade o actualiza el examen en el catálogo existente.",
    )
    args = parser.parse_args()

    exam_id = args.exam_id or slugify(args.pdf.stem)
    exam = build_exam_from_pdf(args.pdf, exam_id=exam_id, title=args.title)

    payload = {"exams": [exam]}
    if args.merge:
        payload = merge_payload(load_existing_payload(args.output), exam)

    write_output(payload, args.output)
    print(f"Examen importado: {exam['title']} ({exam['questionCount']} preguntas)")


if __name__ == "__main__":
    main()
