from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

# Local, gitignored NimStim folder. Do not commit or publicly share these files.
NIMSTIM_ROOT = PROJECT_ROOT / "resources" / "NimStim"
ORIGINAL_PAPER_PATH = PROJECT_ROOT / "original_paper.pdf"

GENERATED_STIMULI_DIR = PROJECT_ROOT / "stimuli_generated"
CONDITIONS_DIR = PROJECT_ROOT / "conditions"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

STIMULUS_MANIFEST_CSV = CONDITIONS_DIR / "stimulus_manifest.csv"
CANDIDATE_IMAGES_CSV = CONDITIONS_DIR / "all_candidate_images.csv"
UNMATCHED_IMAGES_CSV = CONDITIONS_DIR / "unmatched_images.csv"
MANUAL_TEMPLATE_CSV = CONDITIONS_DIR / "manual_actor_selection_template.csv"
TRIAL_SEQUENCE_CSV = CONDITIONS_DIR / "trial_sequence.csv"
BUILD_SUMMARY_JSON = LOGS_DIR / "build_summary.json"

IMAGE_EXTENSIONS = (".bmp", ".png", ".jpg", ".jpeg", ".tif", ".tiff")

REQUIRED_EMOTIONS = ("angry", "fearful", "happy", "neutral")
TARGET_EMOTIONS = REQUIRED_EMOTIONS
NUM_ACTORS = 10
REPETITIONS_PER_ACTOR_EMOTION = 2
DEFAULT_RANDOM_SEED = 20260625
DEFAULT_ACTOR_IDS = (
    "01F",
    "07F",
    "09F",
    "13F",
    "18F",
    "32M",
    "34M",
    "37M",
    "39M",
    "40M",
)
BALANCE_ACTOR_SEX_WHERE_POSSIBLE = False

# NimStim expression codes from the local codebook_faces.csv.
EMOTION_CODE_MAP = {
    "AN": "angry",
    "FE": "fearful",
    "HA": "happy",
    "NE": "neutral",
}

EMOTION_ALIASES = {
    "angry": "angry",
    "anger": "angry",
    "fear": "fearful",
    "fearful": "fearful",
    "happy": "happy",
    "happiness": "happy",
    "neutral": "neutral",
}

NIMSTIM_VARIANT_LABELS = {
    "O": "open_mouth",
    "C": "closed_mouth",
    "X": "exuberant_open_mouth",
    "": "unspecified",
}

# Closed-mouth NimStim variants are required for this task version.
ALLOWED_VARIANTS_BY_EMOTION = {
    "angry": ("C",),
    "fearful": ("C",),
    "happy": ("C",),
    "neutral": ("C",),
}

# Deterministic selection policy when an actor has multiple usable files.
VARIANT_PREFERENCE = {
    "angry": ("C",),
    "fearful": ("C",),
    "happy": ("C",),
    "neutral": ("C",),
}

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
FACE_HEIGHT = 0.75
