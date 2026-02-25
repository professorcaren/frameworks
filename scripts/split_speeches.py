#!/usr/bin/env python3
"""Split source markdown anthologies into one file per speech + CSV metadata."""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class SpeechRecord:
    book_slug: str
    book_title: str
    speech_index: int
    speech_title: str
    speaker: str
    section: str
    source_file: str
    output_file: str


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return normalized or "untitled"


def clean_heading_text(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"`<\?pagebreak[^`]*>`\{=html\}", "", text)
    text = re.sub(r"\[\]\{#[^}]+\}", "", text)
    text = re.sub(r"\s*\{#[^}]+\}\s*$", "", text)
    text = re.sub(r"\s*\{\.[^}]+\}\s*$", "", text)
    text = text.replace("**", "")
    text = text.replace("`", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title_key(text: str) -> str:
    key = text.strip().strip("'").strip('"').lower()
    key = re.sub(r"\s+", " ", key)
    return key


def is_probable_person_name(text: str) -> bool:
    raw = re.sub(r"^\d+\s*", "", text).strip()
    if not raw:
        return False
    tokens = [t for t in re.split(r"\s+", raw) if t]
    if len(tokens) > 6:
        return False
    allowed_lower = {"de", "da", "di", "bin", "al", "van", "von", "la", "le", "del", "du"}
    score = 0
    for token in tokens:
        token = token.strip(".,:;!?()[]\"'")
        if not token:
            continue
        if token.lower() in allowed_lower:
            score += 1
        elif token[0].isupper():
            score += 1
    return score >= max(1, len(tokens) - 1)


def split_bounds(lines: list[str], is_start: Callable[[str], bool]) -> list[tuple[int, int]]:
    starts = [i for i, line in enumerate(lines) if is_start(line)]
    bounds: list[tuple[int, int]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        bounds.append((start, end))
    return bounds


def parse_50_speeches(path: Path) -> tuple[str, str, list[tuple[SpeechRecord, str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    book_title = "50 Speeches That Made the Modern World"
    book_slug = "50-speeches-that-made-the-modern-world"

    title_start_pattern = re.compile(r"^##\s+.*'")
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    date_pattern = re.compile(
        rf"^\s*(?:\d{{1,2}}\s+(?:{months})\b.*\b\d{{4}}\b|(?:{months})\s+\d{{4}}\b)"
    )

    starts_with_date: list[tuple[int, int]] = []
    for i in range(len(lines)):
        line = lines[i].strip()
        if not title_start_pattern.match(line):
            continue

        date_idx = -1
        for j in range(i + 1, min(len(lines), i + 10)):
            probe = lines[j].strip().replace("\t", " ")
            if not probe:
                continue
            if date_pattern.match(probe):
                date_idx = j
                break
            # Allow short wrapped title continuation lines before the date.
            if len(probe) <= 100 and not probe.startswith("## ") and not re.search(r"\b\d{4}\b", probe):
                continue
            if probe.startswith("## "):
                continue
            break

        if date_idx != -1:
            starts_with_date.append((i, date_idx))

    grouped_starts: list[int] = []
    for idx, (start_idx, date_idx) in enumerate(starts_with_date):
        if idx == 0:
            grouped_starts.append(start_idx)
            continue
        prev_start, prev_date = starts_with_date[idx - 1]
        if prev_date == date_idx and start_idx - prev_start <= 4:
            continue
        grouped_starts.append(start_idx)

    starts = grouped_starts
    bounds: list[tuple[int, int]] = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        bounds.append((start, end))
    parsed: list[tuple[SpeechRecord, str]] = []

    for idx, (start, end) in enumerate(bounds, start=1):
        title_parts: list[str] = [clean_heading_text(lines[start])]
        for j in range(start + 1, min(end, start + 6)):
            probe = lines[j].strip()
            if not probe:
                continue
            if probe.startswith("## "):
                part = clean_heading_text(probe)
                if "'" in part:
                    title_parts.append(part)
                    continue
            # Non-heading continuation line for wrapped title.
            if len(probe) <= 100 and not re.search(r"\b\d{4}\b", probe):
                title_parts.append(probe)
                continue
            break

        speech_title = " ".join(p.strip() for p in title_parts if p.strip())
        speech_title = speech_title.strip().strip("'").strip()
        speech_title = speech_title.replace("\t", " ").strip()
        if not speech_title:
            continue

        speaker = ""
        for j in range(start - 1, max(-1, start - 30), -1):
            candidate = lines[j].strip()
            if not candidate.startswith("##"):
                continue
            raw = clean_heading_text(candidate)
            if not raw or raw.startswith("'") or raw.startswith("["):
                continue
            raw = re.sub(r"^\d+\s*", "", raw).strip()
            if not raw:
                continue
            tokens = [t for t in re.split(r"\s+", raw) if t]
            if not tokens:
                continue
            role_like = sum(1 for t in tokens if t[:1].islower()) > 0
            if role_like:
                continue
            speaker = raw
            break

        content_lines = lines[start:end]
        content = "\n".join(content_lines).strip() + "\n"
        filename = f"{idx:03d}_{slugify(speech_title)}.md"
        record = SpeechRecord(
            book_slug=book_slug,
            book_title=book_title,
            speech_index=idx,
            speech_title=speech_title,
            speaker=speaker,
            section="",
            source_file=str(path),
            output_file=filename,
        )
        parsed.append((record, content))

    return book_title, book_slug, parsed


def parse_penguin(path: Path) -> tuple[str, str, list[tuple[SpeechRecord, str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    book_title = "The Penguin Book of Modern Speeches"
    book_slug = "the-penguin-book-of-modern-speeches"

    toc_map: dict[str, str] = {}
    toc_pattern = re.compile(r"^\[([^\]]+?)\s+\*'([^']+)'.*")
    for line in lines:
        m = toc_pattern.match(line.strip())
        if m:
            toc_map[normalize_title_key(m.group(2))] = m.group(1).strip()

    start_pattern = re.compile(r"^##\s+.*\{#chapter\d+\.html_[^}]*\.EB04MainHead\}")
    bounds = split_bounds(lines, lambda ln: bool(start_pattern.match(ln)))
    parsed: list[tuple[SpeechRecord, str]] = []

    for idx, (start, end) in enumerate(bounds, start=1):
        speaker_line = clean_heading_text(lines[start])
        speech_title = ""
        for j in range(start + 1, min(len(lines), start + 8)):
            if not lines[j].strip().startswith("####"):
                continue
            title_line = clean_heading_text(lines[j])
            title_match = re.match(r"^'(.+)'$", title_line)
            if title_match:
                speech_title = title_match.group(1).strip()
                break

        if not speech_title:
            continue

        speaker = toc_map.get(normalize_title_key(speech_title), speaker_line)
        content = "\n".join(lines[start:end]).strip() + "\n"
        filename = f"{idx:03d}_{slugify(speech_title)}.md"
        record = SpeechRecord(
            book_slug=book_slug,
            book_title=book_title,
            speech_index=idx,
            speech_title=speech_title,
            speaker=speaker,
            section="",
            source_file=str(path),
            output_file=filename,
        )
        parsed.append((record, content))

    return book_title, book_slug, parsed


def parse_lend(path: Path) -> tuple[str, str, list[tuple[SpeechRecord, str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    book_title = "Lend Me Your Ears: Great Speeches in History"
    book_slug = "lend-me-your-ears-great-speeches-in-history"

    section_pattern = re.compile(r"^#\s+.*\{\.part1\}\s*$")
    speech_start_pattern = re.compile(r"^#\s+.*\{#part\d+\.html_c\d+\s+\.toc\}\s*$")

    current_section = ""
    section_by_line: dict[int, str] = {}
    for i, line in enumerate(lines):
        if section_pattern.match(line.strip()):
            current_section = clean_heading_text(line)
        section_by_line[i] = current_section

    bounds = split_bounds(lines, lambda ln: bool(speech_start_pattern.match(ln)))
    parsed: list[tuple[SpeechRecord, str]] = []

    for idx, (start, end) in enumerate(bounds, start=1):
        heading = clean_heading_text(lines[start])
        speech_title = heading
        speaker = ""
        # Speaker is usually the first token chunk before a verb in title phrasing.
        speaker_guess = re.split(
            r"\s+(Extols|Refuses|Defines|Speaks|Celebrates|Affirms|Lashes|Evokes|Pledges|Rededicates|Ignites|Turns|Launches|Inveighs|Talks|Hails|Demands|Exhorts|Takes|Surrenders|Presents|Defends|Justifies|Declares|Braces|Rallies|Commands|Asks|Acts|Shakes)\s+",
            speech_title,
            maxsplit=1,
        )
        if len(speaker_guess) > 1:
            speaker = speaker_guess[0].strip()

        section = section_by_line.get(start, "")
        content = "\n".join(lines[start:end]).strip() + "\n"
        filename = f"{idx:03d}_{slugify(speech_title)}.md"
        record = SpeechRecord(
            book_slug=book_slug,
            book_title=book_title,
            speech_index=idx,
            speech_title=speech_title,
            speaker=speaker,
            section=section,
            source_file=str(path),
            output_file=filename,
        )
        parsed.append((record, content))

    return book_title, book_slug, parsed


def write_outputs(output_root: Path, parsed_books: list[tuple[str, str, list[tuple[SpeechRecord, str]]]]) -> None:
    all_rows: list[SpeechRecord] = []
    for _, book_slug, records in parsed_books:
        book_dir = output_root / book_slug
        speeches_dir = book_dir / "speeches"
        speeches_dir.mkdir(parents=True, exist_ok=True)
        for old_file in speeches_dir.glob("*.md"):
            old_file.unlink()
        csv_path = book_dir / "speeches.csv"
        if csv_path.exists():
            csv_path.unlink()

        rows: list[SpeechRecord] = []
        for record, content in records:
            (speeches_dir / record.output_file).write_text(content, encoding="utf-8")
            rows.append(record)
            all_rows.append(record)

        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "book_slug",
                    "book_title",
                    "speech_index",
                    "speech_title",
                    "speaker",
                    "section",
                    "source_file",
                    "output_file",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row.book_slug,
                        row.book_title,
                        row.speech_index,
                        row.speech_title,
                        row.speaker,
                        row.section,
                        row.source_file,
                        f"{row.book_slug}/speeches/{row.output_file}",
                    ]
                )

    with (output_root / "all_speeches.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "book_slug",
                "book_title",
                "speech_index",
                "speech_title",
                "speaker",
                "section",
                "source_file",
                "output_file",
            ]
        )
        for row in all_rows:
            writer.writerow(
                [
                    row.book_slug,
                    row.book_title,
                    row.speech_index,
                    row.speech_title,
                    row.speaker,
                    row.section,
                    row.source_file,
                    f"{row.book_slug}/speeches/{row.output_file}",
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing source markdown files (default: data)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/split_speeches",
        help="Output directory for split speech files + CSVs",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    book_parsers: list[tuple[str, Callable[[Path], tuple[str, str, list[tuple[SpeechRecord, str]]]]]] = [
        ("50 Speeches That Made the Modern World", parse_50_speeches),
        ("The Penguin Book of Modern Speeches", parse_penguin),
        ("Lend Me Your Ears - Great Speeches in History", parse_lend),
    ]

    parsed_books: list[tuple[str, str, list[tuple[SpeechRecord, str]]]] = []
    data_files = list(data_dir.glob("*.md"))
    for contains, parser_fn in book_parsers:
        matched = next((p for p in data_files if contains in p.name), None)
        if matched is None:
            continue
        parsed_books.append(parser_fn(matched))

    write_outputs(output_dir, parsed_books)

    total = sum(len(records) for _, _, records in parsed_books)
    print(f"Wrote {total} speeches across {len(parsed_books)} books to {output_dir}")


if __name__ == "__main__":
    main()
