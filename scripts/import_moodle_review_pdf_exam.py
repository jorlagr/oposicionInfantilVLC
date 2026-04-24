#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


CORRECT_MARKERS = ("", "✓", "✔")


def compact_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:?)])", r"\1", text)
    text = re.sub(r"([¿(])\s+", r"\1", text)
    return text


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def extract_pdf_text(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.replace("\f", "\n")


def split_marker(text: str) -> tuple[str, bool]:
    for marker in CORRECT_MARKERS:
        if marker in text:
            return text.split(marker, 1)[0], True
    return text, False


def parse_block(block: str) -> dict:
    lines = [line.rstrip() for line in block.splitlines()]
    question_number = None
    question_parts: list[str] = []
    options: list[dict] = []
    current_option = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        question_match = re.match(r"^Pregunta\s+(\d+)$", line)
        if question_match:
            question_number = int(question_match.group(1))
            continue

        if line in {"Correcta", "Incorrecta", "Parcialmente correcta", "Sin responder"}:
            continue
        if line.startswith("Puntúa "):
            continue
        if line == "Respuesta correcta":
            break

        option_match = re.match(r"^([a-d])\.\s*(.+)$", line, flags=re.IGNORECASE)
        if option_match:
            option_text, is_correct = split_marker(option_match.group(2))
            current_option = {
                "id": option_match.group(1).lower(),
                "text": compact_text(option_text),
                "isCorrect": is_correct,
                "locked": is_correct,
            }
            options.append(current_option)
            continue

        if current_option is not None:
            if current_option["locked"]:
                continue
            extra_text, is_correct = split_marker(line)
            current_option["text"] = compact_text(f"{current_option['text']} {extra_text}")
            current_option["isCorrect"] = current_option["isCorrect"] or is_correct
            current_option["locked"] = current_option["locked"] or is_correct
            continue

        question_parts.append(line)

    if question_number is None:
        raise ValueError("No se ha encontrado el número de pregunta en un bloque del PDF.")
    if len(options) != 4:
        raise ValueError(f"La pregunta {question_number} no tiene 4 opciones.")

    correct_options = [option["id"] for option in options if option["isCorrect"]]
    if len(correct_options) != 1:
        raise ValueError(f"La pregunta {question_number} no tiene una única respuesta marcada.")

    return {
        "id": f"q{question_number}",
        "number": question_number,
        "text": compact_text(" ".join(question_parts)),
        "options": [
            {
                "id": option["id"],
                "text": option["text"],
            }
            for option in options
        ],
        "correctOption": correct_options[0],
    }


def build_exam_from_pdf(pdf_path: Path, exam_id: str, title: str | None) -> dict:
    text = extract_pdf_text(pdf_path)
    start_index = text.find("Pregunta 1")
    if start_index == -1:
        raise ValueError(f"No se ha encontrado la primera pregunta en {pdf_path.name}.")

    blocks = re.split(r"(?=^Pregunta\s+\d+$)", text[start_index:], flags=re.MULTILINE)
    questions = [parse_block(block) for block in blocks if block.strip()]
    questions.sort(key=lambda question: question["number"])

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
        description="Importa un examen desde un PDF de revisión de Moodle con la respuesta marcada."
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
