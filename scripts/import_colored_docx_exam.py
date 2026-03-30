#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DEFAULT_CORRECT_COLOR = "00B050"


def compact_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:?)])", r"\1", text)
    text = re.sub(r"([¿(])\s+", r"\1", text)
    return text


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def read_docx_paragraphs(docx_path: Path) -> list[dict]:
    with ZipFile(docx_path) as archive:
        xml_bytes = archive.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    paragraphs = []

    for paragraph in root.findall(".//w:body/w:p", WORD_NAMESPACE):
        runs = []
        for run in paragraph.findall("./w:r", WORD_NAMESPACE):
            text_chunks = [node.text or "" for node in run.findall(".//w:t", WORD_NAMESPACE)]
            text = "".join(text_chunks)
            if not text:
                continue

            color = None
            color_node = run.find("./w:rPr/w:color", WORD_NAMESPACE)
            if color_node is not None:
                color = color_node.attrib.get(f"{{{WORD_NAMESPACE['w']}}}val", "").upper()

            runs.append({"text": text, "color": color})

        paragraph_text = compact_text("".join(run["text"] for run in runs))
        if not paragraph_text:
            continue

        paragraphs.append({"text": paragraph_text, "runs": runs})

    return paragraphs


def build_exam_from_docx(
    docx_path: Path,
    exam_id: str,
    title: str | None,
    correct_color: str,
    extra_source: dict[str, str],
) -> dict:
    paragraphs = read_docx_paragraphs(docx_path)
    if len(paragraphs) < 6:
        raise ValueError(f"El documento {docx_path} no tiene contenido suficiente.")

    exam_title = title or paragraphs[0]["text"]
    questions = []
    current_question = None
    current_options = []
    current_correct_option = None

    def flush_question() -> None:
        nonlocal current_question, current_options, current_correct_option
        if not current_question:
            return
        if len(current_options) != 4:
            raise ValueError(
                f"La pregunta {len(questions) + 1} de {docx_path.name} no tiene 4 opciones."
            )
        if current_correct_option is None:
            raise ValueError(
                f"La pregunta {len(questions) + 1} de {docx_path.name} no tiene respuesta marcada."
            )

        question_number = len(questions) + 1
        questions.append(
            {
                "id": f"q{question_number}",
                "number": question_number,
                "text": current_question,
                "options": current_options,
                "correctOption": current_correct_option,
            }
        )
        current_question = None
        current_options = []
        current_correct_option = None

    for paragraph in paragraphs[1:]:
        option_match = re.match(r"^([a-d])\.\s*(.+)$", paragraph["text"], flags=re.IGNORECASE)
        if option_match:
            if not current_question:
                raise ValueError(
                    f"Se ha encontrado una opción sin pregunta previa en {docx_path.name}: {paragraph['text']}"
                )

            option_id = option_match.group(1).lower()
            option_text = compact_text(option_match.group(2))
            current_options.append({"id": option_id, "text": option_text})

            paragraph_colors = {
                (run["color"] or "").upper()
                for run in paragraph["runs"]
                if (run["color"] or "").upper()
            }
            if correct_color in paragraph_colors:
                current_correct_option = option_id
            continue

        flush_question()
        current_question = paragraph["text"]

    flush_question()

    if not questions:
        raise ValueError(f"No se han podido extraer preguntas desde {docx_path.name}.")

    source = {"questionsDocx": str(docx_path), "answersDocx": str(docx_path)}
    source.update(extra_source)

    return {
        "id": exam_id,
        "title": exam_title,
        "source": source,
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


def parse_extra_sources(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Formato de --extra-source no válido: {item}")
        key, value = item.split("=", 1)
        result[key] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa un examen desde un DOCX con la respuesta correcta marcada por color."
    )
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--exam-id")
    parser.add_argument("--title")
    parser.add_argument("--correct-color", default=DEFAULT_CORRECT_COLOR)
    parser.add_argument("--extra-source", action="append", default=[])
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Añade o actualiza el examen en el catálogo existente.",
    )
    args = parser.parse_args()

    exam_id = args.exam_id or slugify(args.docx.stem)
    exam = build_exam_from_docx(
        docx_path=args.docx,
        exam_id=exam_id,
        title=args.title,
        correct_color=args.correct_color.upper(),
        extra_source=parse_extra_sources(args.extra_source),
    )

    payload = {"exams": [exam]}
    if args.merge:
        payload = merge_payload(load_existing_payload(args.output), exam)

    write_output(payload, args.output)
    print(f"Examen importado: {exam['title']} ({exam['questionCount']} preguntas)")


if __name__ == "__main__":
    main()
