from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

# Local, gitignored NimStim_ER folder. Do not commit or publicly share these files.
NIMSTIM_ROOT = PROJECT_ROOT / "resources" / "NimStim_ER"

CONDITIONS_DIR = PROJECT_ROOT / "conditions"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

TRIAL_SEQUENCE_CSV = CONDITIONS_DIR / "trial_sequence.csv"

REQUIRED_EMOTIONS = ("angry", "fearful", "happy", "neutral")

TIMINGS_SECONDS = {
    "fixation": 0.800,
    "target": 0.033,
    "mask": 0.467,
    "response": 7.700,
}

# Edit this mapping for scanner box counterbalancing, or pass --response-map
# to run_experiment.py. The mapping used is saved in every data row.
RESPONSE_KEY_MAP = {
    "1": "happy",
    "2": "angry",
    "3": "neutral",
    "4": "fearful",
}

START_KEYS = ("1",)
QUIT_KEYS = ("escape",)

WINDOW_SIZE = (1024, 768)
BACKGROUND_COLOR = (-1, -1, -1)
FOREGROUND_COLOR = (1, 1, 1)
FACE_SIZE = (0.58, 0.75)
