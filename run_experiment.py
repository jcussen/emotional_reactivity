#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

import config


# Edit this mapping here or in config.py for response-box counterbalancing.
RESPONSE_KEY_MAP = dict(config.RESPONSE_KEY_MAP)


def normalize_key_name(key_name: str) -> str:
    return str(key_name).strip().lower()


def aliases_for_key(key_name: str) -> set[str]:
    key_name = normalize_key_name(key_name)
    aliases = {key_name}
    if key_name.isdigit():
        aliases.add(f"num_{key_name}")
        aliases.add(f"numpad_{key_name}")
    if key_name.startswith("num_") and key_name[4:].isdigit():
        aliases.add(key_name[4:])
        aliases.add(f"numpad_{key_name[4:]}")
    if key_name.startswith("numpad_") and key_name[7:].isdigit():
        aliases.add(key_name[7:])
        aliases.add(f"num_{key_name[7:]}")
    return aliases


def build_key_lookup(keys: list[str] | tuple[str, ...]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for key in keys:
        canonical = normalize_key_name(key)
        for alias in aliases_for_key(canonical):
            lookup[alias] = canonical
    return lookup


def build_response_key_lookup(response_map: dict[str, str]) -> dict[str, str]:
    return build_key_lookup(tuple(response_map.keys()))


def key_name_from_event(key_event) -> str:
    value = key_event
    for _ in range(10):
        if hasattr(value, "name"):
            value = value.name
            continue
        if isinstance(value, (list, tuple)) and value:
            value = value[0]
            continue
        break
    return normalize_key_name(value)


def key_timestamp_from_event(key_event) -> float | None:
    if hasattr(key_event, "rt") and key_event.rt is not None:
        return float(key_event.rt)
    if isinstance(key_event, (list, tuple)) and len(key_event) > 1:
        try:
            return float(key_event[1])
        except (TypeError, ValueError):
            return None
    if hasattr(key_event, "name"):
        return key_timestamp_from_event(key_event.name)
    return None


def response_rt_from_event(key_event, response_onset: float | None, run_clock) -> float | None:
    timestamp = key_timestamp_from_event(key_event)
    if timestamp is not None:
        if response_onset is not None:
            elapsed = timestamp - response_onset
            if 0 <= elapsed <= 30:
                return elapsed
        if 0 <= timestamp <= 30:
            return timestamp
    if response_onset is not None:
        return max(0.0, run_clock.getTime() - response_onset)
    return None


def clear_keyboard_events(kb, event_module=None) -> None:
    try:
        kb.clearEvents(eventType="keyboard")
    except TypeError:
        kb.clearEvents()
    if event_module is not None:
        try:
            event_module.clearEvents(eventType="keyboard")
        except TypeError:
            event_module.clearEvents()


def poll_response_key_events(kb, event_module, key_list: list[str]):
    for key in kb.getKeys(keyList=None, waitRelease=False, clear=True):
        yield "keyboard", key
    if event_module is not None:
        for key in event_module.getKeys(keyList=key_list, timeStamped=kb.clock):
            yield "event", key


def parse_response_map(raw: str | None) -> dict[str, str]:
    if not raw:
        return dict(RESPONSE_KEY_MAP)

    mapping: dict[str, str] = {}
    for part in raw.split(","):
        if "=" not in part:
            raise SystemExit(
                "--response-map must look like '1=happy,2=angry,3=neutral,4=fearful'."
            )
        key, emotion = [piece.strip().lower() for piece in part.split("=", 1)]
        if emotion not in config.REQUIRED_EMOTIONS:
            raise SystemExit(f"Unknown response emotion in --response-map: {emotion}")
        mapping[key] = emotion

    if set(mapping.values()) != set(config.REQUIRED_EMOTIONS):
        raise SystemExit(
            "Response map must include each emotion exactly once: "
            + ", ".join(config.REQUIRED_EMOTIONS)
        )
    return mapping


def load_trials(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(
            f"Condition file not found: {path}\n"
            "Run build_stimuli.py before starting the experiment."
        )

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    required = {
        "trial_number",
        "trial_id",
        "actor_id",
        "target_emotion",
        "target_image_path",
        "mask_image_path",
        "repetition",
    }
    missing = required.difference(rows[0].keys() if rows else [])
    if missing:
        raise SystemExit(f"Condition file is missing columns: {', '.join(sorted(missing))}")

    missing_files = []
    for row in rows:
        for key in ("target_image_path", "mask_image_path"):
            if not Path(row[key]).exists():
                missing_files.append(row[key])
    if missing_files:
        preview = "\n".join(missing_files[:10])
        raise SystemExit(f"Missing stimulus image files:\n{preview}")

    return rows


def setup_logging(participant_id: str, session: str) -> Path:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = config.LOGS_DIR / f"sub-{participant_id}_ses-{session}_{timestamp}.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return log_path


def data_path(participant_id: str, session: str) -> Path:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return config.DATA_DIR / f"sub-{participant_id}_ses-{session}_{timestamp}.csv"


def image_size_for_height(image_path: str, face_height: float) -> tuple[float, float]:
    with Image.open(image_path) as image:
        width, height = image.size
    aspect = width / height
    return (face_height * aspect, face_height)


def frame_counts_for_timings(win, timings: dict[str, float], assumed_frame_rate: float):
    frame_rate = win.getActualFrameRate(nIdentical=60, nMaxFrames=120, nWarmUpFrames=10)
    if frame_rate is None:
        frame_rate = assumed_frame_rate
        logging.warning("Could not measure frame rate; using assumed %.3f Hz.", frame_rate)

    counts = {
        phase: max(1, int(round(duration * frame_rate)))
        for phase, duration in timings.items()
    }
    return frame_rate, counts


def draw_for_frames(win, run_clock, drawables, frame_count: int) -> float:
    onset = None
    for frame_idx in range(frame_count):
        for drawable in drawables:
            drawable.draw()
        win.flip()
        if frame_idx == 0:
            onset = run_clock.getTime()
    return float(onset)


def response_items(response_map: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(response_map.items(), key=lambda item: item[0])


def response_x_positions(item_count: int) -> list[float]:
    if item_count == 1:
        return [0.0]
    left = -0.45
    right = 0.45
    step = (right - left) / (item_count - 1)
    return [left + idx * step for idx in range(item_count)]


def create_response_display(win, visual, response_map: dict[str, str]):
    items = response_items(response_map)
    x_positions = response_x_positions(len(items))
    prompt = visual.TextStim(
        win,
        text="Which expression was shown?",
        height=0.035,
        color=config.FOREGROUND_COLOR,
        units="height",
        pos=(0, -0.12),
    )
    labels = {}
    for (key, emotion), x_pos in zip(items, x_positions):
        labels[key] = visual.TextStim(
            win,
            text=f"{key}\n{emotion}",
            height=0.03,
            color=config.FOREGROUND_COLOR,
            units="height",
            pos=(x_pos, -0.24),
            alignText="center",
        )
    marker = visual.Circle(
        win,
        radius=0.011,
        fillColor=config.FOREGROUND_COLOR,
        lineColor=config.FOREGROUND_COLOR,
        units="height",
        pos=(0, -0.34),
    )
    return prompt, labels, marker


def draw_response_display(prompt, labels, marker, selected_key: str) -> None:
    prompt.draw()
    for label in labels.values():
        label.draw()
    if selected_key:
        marker.pos = (labels[selected_key].pos[0], marker.pos[1])
        marker.draw()


def collect_response_frames(
    win,
    run_clock,
    kb,
    event_module,
    response_key_lookup: dict[str, str],
    frame_count: int,
    response_display,
) -> tuple[float, str, str, float | None]:
    response_onset = None
    response_key = ""
    raw_response_key = ""
    response_rt = None
    prompt, labels, marker = response_display
    quit_lookup = build_key_lookup(config.QUIT_KEYS)
    key_list = sorted(set(response_key_lookup) | set(quit_lookup))

    clear_keyboard_events(kb, event_module)
    for frame_idx in range(frame_count):
        if frame_idx == 0:
            if hasattr(win, "callOnFlip"):
                win.callOnFlip(kb.clock.reset)
                if event_module is not None:
                    win.callOnFlip(clear_keyboard_events, kb, event_module)
            else:
                kb.clock.reset()
                clear_keyboard_events(kb, event_module)
        draw_response_display(prompt, labels, marker, response_key)
        win.flip()
        if frame_idx == 0:
            response_onset = run_clock.getTime()
        for source, key in poll_response_key_events(kb, event_module, key_list):
            raw_key = key_name_from_event(key)
            if raw_key in quit_lookup:
                raise KeyboardInterrupt("Experiment aborted with escape.")
            canonical_key = response_key_lookup.get(raw_key)
            if canonical_key and not response_key:
                response_key = canonical_key
                raw_response_key = raw_key
                response_rt = response_rt_from_event(key, response_onset, run_clock)
                logging.info(
                    "Accepted response key source=%s raw=%s canonical=%s rt=%.6f",
                    source,
                    raw_response_key,
                    response_key,
                    response_rt if response_rt is not None else -1,
                )
            elif not canonical_key:
                logging.info("Ignored response-window key source=%s raw=%s", source, raw_key)

    return float(response_onset), response_key, raw_response_key, response_rt


def write_header(handle, fieldnames: list[str]) -> csv.DictWriter:
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    handle.flush()
    return writer


def show_text(win, text_stim, message: str):
    text_stim.text = message
    text_stim.draw()
    win.flip()


def wait_for_start_key(event) -> tuple[str, str]:
    start_lookup = build_key_lookup(config.START_KEYS)
    quit_lookup = build_key_lookup(config.QUIT_KEYS)
    key_list = sorted(set(start_lookup) | set(quit_lookup))
    event.clearEvents()
    pressed = event.waitKeys(keyList=key_list)
    raw_start_key = key_name_from_event(pressed[0]) if pressed else ""
    if raw_start_key in quit_lookup:
        return "", raw_start_key
    return start_lookup.get(raw_start_key, raw_start_key), raw_start_key


def run_experiment(args) -> int:
    from psychopy import core, event, gui, visual
    from psychopy.hardware import keyboard

    response_map = parse_response_map(args.response_map)
    response_key_lookup = build_response_key_lookup(response_map)
    trials = load_trials(args.conditions.expanduser().resolve())
    timings = config.TIMINGS_SECONDS

    info = {
        "participant_id": args.participant or "",
        "session": args.session or "1",
    }
    if not args.no_dialog:
        dialog = gui.DlgFromDict(info, title="Masked Faces fMRI Task")
        if not dialog.OK:
            return 1

    participant_id = str(info["participant_id"]).strip() or "unknown"
    session = str(info["session"]).strip() or "1"

    log_path = setup_logging(participant_id, session)
    out_path = data_path(participant_id, session)
    logging.info("Starting experiment with %d trials.", len(trials))
    logging.info("Condition file: %s", args.conditions)
    logging.info("Data file: %s", out_path)

    win = visual.Window(
        size=config.WINDOW_SIZE,
        fullscr=not args.windowed,
        screen=args.screen,
        units="height",
        color=config.BACKGROUND_COLOR,
        allowGUI=args.windowed,
    )
    win.mouseVisible = False

    frame_rate, frame_counts = frame_counts_for_timings(
        win, timings, args.assumed_frame_rate
    )
    logging.info("Frame rate used: %.6f", frame_rate)
    logging.info("Frame counts: %s", frame_counts)

    fixation = visual.TextStim(
        win,
        text="+",
        height=0.08,
        color=config.FOREGROUND_COLOR,
        units="height",
    )
    text_stim = visual.TextStim(
        win,
        text="",
        height=0.035,
        color=config.FOREGROUND_COLOR,
        units="height",
        wrapWidth=1.3,
    )
    target_stim = visual.ImageStim(win, interpolate=True, units="height")
    mask_stim = visual.ImageStim(win, interpolate=True, units="height")
    response_display = create_response_display(win, visual, response_map)

    mapping_lines = "\n".join(
        f"{key} = {emotion}" for key, emotion in sorted(response_map.items())
    )
    instructions = (
        "A face will be flashed very briefly and then masked.\n\n"
        "During the response screen, report which expression was flashed.\n"
        "A marker will show your selection after you answer.\n\n"
        f"{mapping_lines}\n\n"
        "Press 1 to start."
    )
    show_text(win, text_stim, instructions)
    start_key, raw_start_key = wait_for_start_key(event)
    if raw_start_key in build_key_lookup(config.QUIT_KEYS):
        win.close()
        return 1

    kb = keyboard.Keyboard()
    run_clock = core.Clock()
    run_clock.reset()

    fieldnames = [
        "participant_id",
        "session",
        "date_time",
        "condition_file",
        "response_mapping",
        "start_key",
        "raw_start_key",
        "frame_rate",
        "fixation_frames",
        "target_frames",
        "mask_frames",
        "response_frames",
        "trial_number",
        "trial_id",
        "actor_id",
        "target_emotion",
        "target_image_path",
        "mask_image_path",
        "repetition",
        "fixation_onset",
        "target_onset",
        "mask_onset",
        "response_window_onset",
        "response_key",
        "raw_response_key",
        "response_emotion",
        "correctness",
        "rt_from_target_onset",
        "rt_from_response_window_onset",
        "trial_duration",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = write_header(handle, fieldnames)
        try:
            for trial in trials:
                target_path = trial["target_image_path"]
                mask_path = trial["mask_image_path"]
                target_stim.image = target_path
                mask_stim.image = mask_path
                target_stim.size = image_size_for_height(target_path, config.FACE_HEIGHT)
                mask_stim.size = image_size_for_height(mask_path, config.FACE_HEIGHT)

                fixation_onset = draw_for_frames(
                    win, run_clock, [fixation], frame_counts["fixation"]
                )
                target_onset = draw_for_frames(
                    win, run_clock, [target_stim], frame_counts["target"]
                )
                mask_onset = draw_for_frames(
                    win, run_clock, [mask_stim], frame_counts["mask"]
                )
                response_onset, response_key, raw_response_key, response_rt = collect_response_frames(
                    win,
                    run_clock,
                    kb,
                    event,
                    response_key_lookup,
                    frame_counts["response"],
                    response_display,
                )
                trial_end = run_clock.getTime()

                response_emotion = response_map.get(response_key, "")
                correct = (
                    response_emotion == trial["target_emotion"]
                    if response_emotion
                    else False
                )
                rt_from_target = (
                    response_onset + response_rt - target_onset
                    if response_rt is not None
                    else ""
                )

                writer.writerow(
                    {
                        "participant_id": participant_id,
                        "session": session,
                        "date_time": datetime.now().isoformat(timespec="milliseconds"),
                        "condition_file": str(args.conditions.resolve()),
                        "response_mapping": json.dumps(response_map, sort_keys=True),
                        "start_key": start_key,
                        "raw_start_key": raw_start_key,
                        "frame_rate": f"{frame_rate:.6f}",
                        "fixation_frames": frame_counts["fixation"],
                        "target_frames": frame_counts["target"],
                        "mask_frames": frame_counts["mask"],
                        "response_frames": frame_counts["response"],
                        "trial_number": trial["trial_number"],
                        "trial_id": trial["trial_id"],
                        "actor_id": trial["actor_id"],
                        "target_emotion": trial["target_emotion"],
                        "target_image_path": target_path,
                        "mask_image_path": mask_path,
                        "repetition": trial["repetition"],
                        "fixation_onset": f"{fixation_onset:.6f}",
                        "target_onset": f"{target_onset:.6f}",
                        "mask_onset": f"{mask_onset:.6f}",
                        "response_window_onset": f"{response_onset:.6f}",
                        "response_key": response_key,
                        "raw_response_key": raw_response_key,
                        "response_emotion": response_emotion,
                        "correctness": int(correct),
                        "rt_from_target_onset": (
                            f"{rt_from_target:.6f}" if rt_from_target != "" else ""
                        ),
                        "rt_from_response_window_onset": (
                            f"{response_rt:.6f}" if response_rt is not None else ""
                        ),
                        "trial_duration": f"{trial_end - fixation_onset:.6f}",
                    }
                )
                handle.flush()
        except KeyboardInterrupt:
            logging.warning("Experiment aborted by user.")
            show_text(win, text_stim, "Experiment stopped.")
            core.wait(1.0)
            win.close()
            return 130

    show_text(win, text_stim, "Run complete.")
    core.wait(1.0)
    win.close()
    logging.info("Experiment complete. Data saved to %s; log saved to %s", out_path, log_path)
    print(f"Data saved to: {out_path}")
    print(f"Log saved to: {log_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the masked NimStim face task.")
    parser.add_argument(
        "--conditions",
        type=Path,
        default=config.TRIAL_SEQUENCE_CSV,
        help="CSV trial sequence created by build_stimuli.py.",
    )
    parser.add_argument("--windowed", action="store_true", help="Use a windowed display.")
    parser.add_argument("--participant", default=None, help="Participant ID override.")
    parser.add_argument("--session", default=None, help="Session/run number override.")
    parser.add_argument("--no-dialog", action="store_true", help="Skip participant GUI dialog.")
    parser.add_argument("--screen", type=int, default=0, help="PsychoPy display index.")
    parser.add_argument(
        "--assumed-frame-rate",
        type=float,
        default=60.0,
        help="Fallback frame rate if PsychoPy cannot measure the display.",
    )
    parser.add_argument(
        "--response-map",
        default=None,
        help="Override response keys, e.g. '1=happy,2=angry,3=neutral,4=fearful'.",
    )
    args = parser.parse_args()
    return run_experiment(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportError as exc:
        print(
            "Missing experiment dependency. Install PsychoPy and Pillow with "
            "`python -m pip install -r requirements.txt`.",
            file=sys.stderr,
        )
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
