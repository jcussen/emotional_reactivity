#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps

import config


@dataclass(frozen=True)
class CandidateImage:
    actor_id: str
    emotion: str
    image_path: str
    variant: str
    variant_label: str
    source_code: str
    parser_notes: str


def actor_sort_key(actor_id: str) -> tuple[int, str, str]:
    match = re.match(r"^(\d+)([A-Z]+)$", actor_id.upper())
    if match:
        return (int(match.group(1)), match.group(2), actor_id.upper())
    return (9999, actor_id.upper(), actor_id.upper())


def actor_sex(actor_id: str) -> str:
    actor_id = actor_id.upper()
    if actor_id.endswith("F"):
        return "F"
    if actor_id.endswith("M"):
        return "M"
    return ""


def natural_path_key(path: str) -> tuple[str, ...]:
    return tuple(Path(path).parts)


def ensure_output_dirs() -> None:
    for path in (
        config.GENERATED_STIMULI_DIR,
        config.CONDITIONS_DIR,
        config.DATA_DIR,
        config.LOGS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def clear_generated_mirror_images() -> None:
    for path in config.GENERATED_STIMULI_DIR.glob("*_NE_mirrored_target.png"):
        path.unlink()


def tokenize_path(path: Path) -> list[str]:
    text = " ".join([path.stem, *path.parent.parts[-3:]])
    return [token for token in re.split(r"[^A-Za-z0-9]+", text.upper()) if token]


def find_actor_id(tokens: list[str], path: Path) -> str | None:
    for token in tokens:
        if re.fullmatch(r"\d{1,3}[FM]", token):
            return token.upper()

    stem_match = re.search(r"(\d{1,3}[FM])", path.stem.upper())
    if stem_match:
        return stem_match.group(1).upper()

    return None


def find_emotion(tokens: list[str], path: Path) -> tuple[str | None, str, str]:
    for idx, token in enumerate(tokens):
        if token in config.EMOTION_CODE_MAP:
            variant = ""
            if idx + 1 < len(tokens) and tokens[idx + 1] in config.NIMSTIM_VARIANT_LABELS:
                variant = tokens[idx + 1]
            source_code = token if not variant else f"{token}_{variant}"
            return config.EMOTION_CODE_MAP[token], variant, source_code

    lower_text = " ".join([path.stem, *path.parent.parts[-3:]]).lower()
    for alias, emotion in config.EMOTION_ALIASES.items():
        if re.search(rf"(^|[^a-z]){re.escape(alias)}([^a-z]|$)", lower_text):
            return emotion, "", alias

    return None, "", ""


def parse_image(path: Path, root: Path) -> tuple[CandidateImage | None, str]:
    tokens = tokenize_path(path.relative_to(root))
    actor_id = find_actor_id(tokens, path)
    emotion, variant, source_code = find_emotion(tokens, path)

    if emotion not in config.REQUIRED_EMOTIONS:
        return None, "not_a_required_emotion"
    if not actor_id:
        return None, "missing_actor_id"

    note = "nimstim_code" if source_code[:2].upper() in config.EMOTION_CODE_MAP else "word_match"
    candidate = CandidateImage(
        actor_id=actor_id,
        emotion=emotion,
        image_path=str(path.resolve()),
        variant=variant,
        variant_label=config.NIMSTIM_VARIANT_LABELS.get(variant, "unknown"),
        source_code=source_code.upper(),
        parser_notes=note,
    )
    return candidate, ""


def scan_images(root: Path) -> tuple[list[CandidateImage], list[dict[str, str]]]:
    candidates: list[CandidateImage] = []
    unmatched: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in config.IMAGE_EXTENSIONS:
            continue
        candidate, reason = parse_image(path, root)
        if candidate is None:
            unmatched.append({"image_path": str(path.resolve()), "reason": reason})
        else:
            candidates.append(candidate)
    return candidates, unmatched


def variant_rank(candidate: CandidateImage) -> tuple[int, int, tuple[str, ...]]:
    preference = config.VARIANT_PREFERENCE[candidate.emotion]
    try:
        variant_index = preference.index(candidate.variant)
    except ValueError:
        variant_index = len(preference)

    suffix = Path(candidate.image_path).suffix.lower()
    suffix_rank = {
        ".bmp": 0,
        ".tif": 1,
        ".tiff": 1,
        ".png": 2,
        ".jpg": 3,
        ".jpeg": 3,
    }.get(suffix, 9)
    return (variant_index, suffix_rank, natural_path_key(candidate.image_path))


def group_candidates(
    candidates: Iterable[CandidateImage],
) -> dict[str, dict[str, list[CandidateImage]]]:
    grouped: dict[str, dict[str, list[CandidateImage]]] = defaultdict(lambda: defaultdict(list))
    for candidate in candidates:
        allowed_variants = config.ALLOWED_VARIANTS_BY_EMOTION.get(candidate.emotion)
        if allowed_variants is not None and candidate.variant not in allowed_variants:
            continue
        grouped[candidate.actor_id][candidate.emotion].append(candidate)

    for emotions in grouped.values():
        for emotion, images in emotions.items():
            images.sort(key=variant_rank)
    return grouped


def choose_actors(
    grouped: dict[str, dict[str, list[CandidateImage]]],
    num_actors: int,
    actor_override: list[str] | None,
) -> list[str]:
    complete = [
        actor
        for actor, emotions in grouped.items()
        if all(emotion in emotions and emotions[emotion] for emotion in config.REQUIRED_EMOTIONS)
    ]
    complete.sort(key=actor_sort_key)

    if actor_override:
        selected = [actor.upper() for actor in actor_override]
        if len(selected) != num_actors:
            raise SystemExit(
                f"--actors must contain exactly {num_actors} actor IDs; got {len(selected)}."
            )
        missing = [actor for actor in selected if actor not in grouped]
        incomplete = [
            actor
            for actor in selected
            if actor in grouped
            and not all(emotion in grouped[actor] for emotion in config.REQUIRED_EMOTIONS)
        ]
        if missing or incomplete:
            details = []
            if missing:
                details.append(f"not found: {', '.join(missing)}")
            for actor in incomplete:
                have = set(grouped[actor])
                absent = [emotion for emotion in config.REQUIRED_EMOTIONS if emotion not in have]
                details.append(f"{actor} missing {', '.join(absent)}")
            raise SystemExit("Manual actor selection is incomplete: " + "; ".join(details))
        return selected

    if len(complete) < num_actors:
        lines = [
            f"Only {len(complete)} actors have all required emotions; need {num_actors}.",
            "Missing-expression summary:",
        ]
        for actor in sorted(grouped, key=actor_sort_key):
            have = set(grouped[actor])
            absent = [emotion for emotion in config.REQUIRED_EMOTIONS if emotion not in have]
            if absent:
                lines.append(f"  {actor}: missing {', '.join(absent)}")
        raise SystemExit("\n".join(lines))

    if config.BALANCE_ACTOR_SEX_WHERE_POSSIBLE and num_actors % 2 == 0:
        by_sex: dict[str, list[str]] = {"F": [], "M": []}
        for actor in complete:
            sex = actor_sex(actor)
            if sex in by_sex:
                by_sex[sex].append(actor)

        half = num_actors // 2
        if len(by_sex["F"]) >= half and len(by_sex["M"]) >= half:
            return sorted(by_sex["F"][:half] + by_sex["M"][:half], key=actor_sort_key)

    return complete[:num_actors]


def selected_images_for_actors(
    grouped: dict[str, dict[str, list[CandidateImage]]], actors: list[str]
) -> dict[str, dict[str, CandidateImage]]:
    selected: dict[str, dict[str, CandidateImage]] = {}
    for actor in actors:
        selected[actor] = {}
        for emotion in config.REQUIRED_EMOTIONS:
            selected[actor][emotion] = grouped[actor][emotion][0]
    return selected


def mirror_neutral_images(
    selected: dict[str, dict[str, CandidateImage]]
) -> dict[str, Path]:
    mirrored: dict[str, Path] = {}
    for actor, emotions in selected.items():
        neutral_path = Path(emotions["neutral"].image_path)
        out_path = config.GENERATED_STIMULI_DIR / f"{actor}_NE_mirrored_target.png"
        with Image.open(neutral_path) as image:
            ImageOps.mirror(image).save(out_path)
        mirrored[actor] = out_path.resolve()
    return mirrored


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_candidate_files(
    candidates: list[CandidateImage],
    unmatched: list[dict[str, str]],
    grouped: dict[str, dict[str, list[CandidateImage]]],
) -> None:
    candidate_rows = [asdict(candidate) for candidate in candidates]
    write_csv(
        config.CANDIDATE_IMAGES_CSV,
        candidate_rows,
        [
            "actor_id",
            "emotion",
            "image_path",
            "variant",
            "variant_label",
            "source_code",
            "parser_notes",
        ],
    )

    write_csv(config.UNMATCHED_IMAGES_CSV, unmatched, ["image_path", "reason"])

    template_rows = []
    for actor in sorted(grouped, key=actor_sort_key):
        row: dict[str, object] = {"include_actor": "", "actor_id": actor}
        for emotion in config.REQUIRED_EMOTIONS:
            images = grouped[actor].get(emotion, [])
            row[f"{emotion}_path"] = images[0].image_path if images else ""
            row[f"{emotion}_candidate_count"] = len(images)
        template_rows.append(row)

    fieldnames = ["include_actor", "actor_id"]
    for emotion in config.REQUIRED_EMOTIONS:
        fieldnames.extend([f"{emotion}_path", f"{emotion}_candidate_count"])
    write_csv(config.MANUAL_TEMPLATE_CSV, template_rows, fieldnames)


def build_stimulus_manifest(
    selected: dict[str, dict[str, CandidateImage]], mirrored: dict[str, Path]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for actor in sorted(selected, key=actor_sort_key):
        for emotion in ("angry", "fearful", "happy"):
            candidate = selected[actor][emotion]
            rows.append(
                {
                    "actor_id": actor,
                    "emotion": emotion,
                    "role": "target",
                    "image_path": candidate.image_path,
                    "source_image_path": candidate.image_path,
                    "is_mirrored": False,
                    "variant": candidate.variant,
                    "variant_label": candidate.variant_label,
                    "source_code": candidate.source_code,
                }
            )

        neutral = selected[actor]["neutral"]
        rows.append(
            {
                "actor_id": actor,
                "emotion": "neutral",
                "role": "target",
                "image_path": str(mirrored[actor]),
                "source_image_path": neutral.image_path,
                "is_mirrored": True,
                "variant": neutral.variant,
                "variant_label": neutral.variant_label,
                "source_code": neutral.source_code,
            }
        )
        rows.append(
            {
                "actor_id": actor,
                "emotion": "neutral",
                "role": "mask",
                "image_path": neutral.image_path,
                "source_image_path": neutral.image_path,
                "is_mirrored": False,
                "variant": neutral.variant,
                "variant_label": neutral.variant_label,
                "source_code": neutral.source_code,
            }
        )
    return rows


def base_trials(
    selected: dict[str, dict[str, CandidateImage]], mirrored: dict[str, Path]
) -> list[dict[str, object]]:
    trials: list[dict[str, object]] = []
    for actor in sorted(selected, key=actor_sort_key):
        neutral_mask = selected[actor]["neutral"].image_path
        for emotion in config.TARGET_EMOTIONS:
            target_path = str(mirrored[actor]) if emotion == "neutral" else selected[actor][emotion].image_path
            for repetition in range(1, config.REPETITIONS_PER_ACTOR_EMOTION + 1):
                trials.append(
                    {
                        "actor_id": actor,
                        "target_emotion": emotion,
                        "target_image_path": target_path,
                        "mask_image_path": neutral_mask,
                        "repetition": repetition,
                    }
                )
    return trials


def max_run_length(values: list[str]) -> int:
    longest = 0
    current = 0
    previous = None
    for value in values:
        if value == previous:
            current += 1
        else:
            current = 1
            previous = value
        longest = max(longest, current)
    return longest


def sequence_stats(sequence: list[dict[str, object]]) -> dict[str, object]:
    same_actor_transitions = []
    for idx in range(1, len(sequence)):
        if sequence[idx]["actor_id"] == sequence[idx - 1]["actor_id"]:
            same_actor_transitions.append(idx + 1)

    emotion_values = [str(trial["target_emotion"]) for trial in sequence]
    actor_counts = Counter(str(trial["actor_id"]) for trial in sequence)
    actor_repeat_possible = max(actor_counts.values(), default=0) <= (len(sequence) + 1) // 2
    return {
        "trial_count": len(sequence),
        "emotion_counts": dict(Counter(emotion_values)),
        "actor_emotion_counts": dict(
            Counter(
                f"{trial['actor_id']}|{trial['target_emotion']}"
                for trial in sequence
            )
        ),
        "same_actor_adjacent_count": len(same_actor_transitions),
        "same_actor_adjacent_trial_numbers": same_actor_transitions,
        "same_actor_avoidance_possible": actor_repeat_possible,
        "max_emotion_run_length": max_run_length(emotion_values),
    }


def would_break_emotion_run(sequence: list[dict[str, object]], emotion: str) -> bool:
    return (
        len(sequence) >= 2
        and sequence[-1]["target_emotion"] == emotion
        and sequence[-2]["target_emotion"] == emotion
    )


def order_trials(
    trials: list[dict[str, object]], seed: int, max_attempts: int = 5000
) -> tuple[list[dict[str, object]], dict[str, object]]:
    master_rng = random.Random(seed)
    best_sequence: list[dict[str, object]] = []
    best_score: tuple[int, int, int] | None = None

    for attempt in range(max_attempts):
        rng = random.Random(master_rng.randrange(0, 2**32) + attempt)
        remaining = [dict(trial) for trial in trials]
        rng.shuffle(remaining)
        sequence: list[dict[str, object]] = []

        while remaining:
            actor_counts = Counter(str(trial["actor_id"]) for trial in remaining)
            emotion_counts = Counter(str(trial["target_emotion"]) for trial in remaining)
            previous_actor = str(sequence[-1]["actor_id"]) if sequence else None
            candidates = [
                trial
                for trial in remaining
                if str(trial["actor_id"]) != previous_actor
                and not would_break_emotion_run(sequence, str(trial["target_emotion"]))
            ]
            if not candidates:
                break

            rng.shuffle(candidates)
            candidates.sort(
                key=lambda trial: (
                    actor_counts[str(trial["actor_id"])],
                    emotion_counts[str(trial["target_emotion"])],
                    rng.random(),
                ),
                reverse=True,
            )
            chosen = candidates[0]
            sequence.append(chosen)
            remaining.remove(chosen)

        stats = sequence_stats(sequence)
        score = (
            int(stats["same_actor_adjacent_count"]),
            max(0, int(stats["max_emotion_run_length"]) - 2),
            len(trials) - len(sequence),
        )
        if best_score is None or score < best_score:
            best_score = score
            best_sequence = sequence

        if len(sequence) == len(trials) and score == (0, 0, 0):
            break

    if len(best_sequence) != len(trials):
        raise SystemExit(
            "Could not create a complete fixed random sequence with the requested constraints. "
            f"Best attempt placed {len(best_sequence)} of {len(trials)} trials."
        )

    for idx, trial in enumerate(best_sequence, start=1):
        trial["trial_number"] = idx
        trial["trial_id"] = f"T{idx:03d}"

    return best_sequence, sequence_stats(best_sequence)


def validate_outputs(
    selected: dict[str, dict[str, CandidateImage]],
    manifest_rows: list[dict[str, object]],
    sequence: list[dict[str, object]],
    stats: dict[str, object],
    expected_actor_count: int,
) -> list[str]:
    messages = []
    selected_actors = sorted(selected, key=actor_sort_key)

    if len(selected_actors) != expected_actor_count:
        raise SystemExit(f"Expected {expected_actor_count} actors, found {len(selected_actors)}.")
    messages.append(f"Selected {len(selected_actors)} actors: {', '.join(selected_actors)}")

    for actor in selected_actors:
        missing = [emotion for emotion in config.REQUIRED_EMOTIONS if emotion not in selected[actor]]
        if missing:
            raise SystemExit(f"{actor} is missing required emotions: {', '.join(missing)}")
    messages.append("Each selected actor has angry, fearful, happy, and neutral images.")

    expected_trials = (
        expected_actor_count
        * len(config.TARGET_EMOTIONS)
        * config.REPETITIONS_PER_ACTOR_EMOTION
    )
    if len(sequence) != expected_trials:
        raise SystemExit(f"Expected {expected_trials} trials, found {len(sequence)}.")
    messages.append(f"Confirmed {expected_trials} trials.")

    expected_per_emotion = {
        emotion: expected_actor_count * config.REPETITIONS_PER_ACTOR_EMOTION
        for emotion in config.TARGET_EMOTIONS
    }
    if stats["emotion_counts"] != expected_per_emotion:
        raise SystemExit(
            f"Expected emotion counts {expected_per_emotion}, found {stats['emotion_counts']}."
        )
    messages.append(
        "Confirmed "
        f"{expected_actor_count * config.REPETITIONS_PER_ACTOR_EMOTION} trials per emotion condition."
    )

    bad_actor_emotion = {
        key: count
        for key, count in stats["actor_emotion_counts"].items()
        if count != config.REPETITIONS_PER_ACTOR_EMOTION
    }
    if bad_actor_emotion:
        raise SystemExit(f"Actor/emotion repetitions are not exactly two: {bad_actor_emotion}")
    messages.append("Confirmed each actor/emotion combination appears exactly twice.")

    if stats["same_actor_adjacent_count"] == 0:
        messages.append("Confirmed no immediate same-actor repetitions.")
    elif stats["same_actor_avoidance_possible"]:
        raise SystemExit(
            "Immediate same-actor repetition was avoidable but present at trial numbers: "
            + ", ".join(map(str, stats["same_actor_adjacent_trial_numbers"]))
        )
    else:
        messages.append(
            "Immediate same-actor repetitions remain, but the actor distribution makes full avoidance impossible."
        )

    if stats["max_emotion_run_length"] > 2:
        raise SystemExit(
            f"Expected no more than two identical emotion labels in a row; found {stats['max_emotion_run_length']}."
        )
    messages.append("Confirmed no more than two identical emotion labels in a row.")

    target_manifest_count = sum(1 for row in manifest_rows if row["role"] == "target")
    mask_manifest_count = sum(1 for row in manifest_rows if row["role"] == "mask")
    messages.append(
        f"Stimulus manifest contains {target_manifest_count} target rows and {mask_manifest_count} mask rows."
    )
    return messages


def print_selection_table(selected: dict[str, dict[str, CandidateImage]]) -> None:
    print("\nSelected images:")
    for actor in sorted(selected, key=actor_sort_key):
        print(f"  {actor}")
        for emotion in config.REQUIRED_EMOTIONS:
            candidate = selected[actor][emotion]
            print(
                f"    {emotion:8s} {candidate.source_code:5s} "
                f"{Path(candidate.image_path).name}"
            )


def parse_actor_override(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [part.strip().upper() for part in raw.split(",") if part.strip()]


def default_actor_override() -> list[str] | None:
    actors = getattr(config, "DEFAULT_ACTOR_IDS", ())
    if not actors:
        return None
    return [actor.upper() for actor in actors]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build NimStim manifests and a fixed masked-face trial sequence."
    )
    parser.add_argument(
        "--nimstim-root",
        type=Path,
        default=config.NIMSTIM_ROOT,
        help="Root folder containing NimStim images.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=config.DEFAULT_RANDOM_SEED,
        help="Random seed for fixed trial ordering.",
    )
    parser.add_argument(
        "--num-actors",
        type=int,
        default=config.NUM_ACTORS,
        help="Number of complete actors to select.",
    )
    parser.add_argument(
        "--actors",
        default=None,
        help="Optional comma-separated actor IDs to force, e.g. 01F,02F,03F,...",
    )
    args = parser.parse_args()

    root = args.nimstim_root.expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"NimStim root does not exist: {root}")

    ensure_output_dirs()
    candidates, unmatched = scan_images(root)
    grouped = group_candidates(candidates)
    write_candidate_files(candidates, unmatched, grouped)

    actor_override = parse_actor_override(args.actors) or default_actor_override()
    selected_actor_ids = choose_actors(grouped, args.num_actors, actor_override)
    selected = selected_images_for_actors(grouped, selected_actor_ids)
    clear_generated_mirror_images()
    mirrored = mirror_neutral_images(selected)

    manifest_rows = build_stimulus_manifest(selected, mirrored)
    write_csv(
        config.STIMULUS_MANIFEST_CSV,
        manifest_rows,
        [
            "actor_id",
            "emotion",
            "role",
            "image_path",
            "source_image_path",
            "is_mirrored",
            "variant",
            "variant_label",
            "source_code",
        ],
    )

    trials = base_trials(selected, mirrored)
    sequence, stats = order_trials(trials, args.seed)
    write_csv(
        config.TRIAL_SEQUENCE_CSV,
        sequence,
        [
            "trial_number",
            "trial_id",
            "actor_id",
            "target_emotion",
            "target_image_path",
            "mask_image_path",
            "repetition",
        ],
    )

    print(f"Scanned NimStim root: {root}")
    print(f"Candidate required-expression images: {len(candidates)}")
    print(f"Unmatched or non-required image files logged: {len(unmatched)}")
    print_selection_table(selected)

    messages = validate_outputs(selected, manifest_rows, sequence, stats, args.num_actors)
    print("\nQuality control:")
    for message in messages:
        print(f"  - {message}")

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "nimstim_root": str(root),
        "seed": args.seed,
        "selected_actors": selected_actor_ids,
        "allowed_variants_by_emotion": config.ALLOWED_VARIANTS_BY_EMOTION,
        "actor_selection_policy": (
            "explicit_actor_ids_from_cli"
            if args.actors
            else "default_actor_ids_from_config"
            if default_actor_override()
            else "balanced_5F_5M_when_available"
            if config.BALANCE_ACTOR_SEX_WHERE_POSSIBLE and args.num_actors == 10
            else "first_complete_actors_by_actor_id"
        ),
        "stats": stats,
        "outputs": {
            "stimulus_manifest": str(config.STIMULUS_MANIFEST_CSV.resolve()),
            "trial_sequence": str(config.TRIAL_SEQUENCE_CSV.resolve()),
            "candidate_images": str(config.CANDIDATE_IMAGES_CSV.resolve()),
            "unmatched_images": str(config.UNMATCHED_IMAGES_CSV.resolve()),
            "manual_template": str(config.MANUAL_TEMPLATE_CSV.resolve()),
        },
    }
    config.BUILD_SUMMARY_JSON.write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print("\nSaved files:")
    for label, path in summary["outputs"].items():
        print(f"  - {label}: {path}")
    print(f"  - build_summary: {config.BUILD_SUMMARY_JSON.resolve()}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
