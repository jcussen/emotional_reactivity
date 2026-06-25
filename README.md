# Masked NimStim Face Task

PsychoPy experiment for a masked emotional-face task using private `NimStim_ER` face images.

Important: do not commit or publicly upload `NimStim_ER.zip`, `resources/NimStim_ER/`, data, or logs.

## Add The Private Faces

You should have a separate private file:

```text
NimStim_ER.zip
```

Without using the command line:

1. Double-click `NimStim_ER.zip` to unzip it.
2. You should now have a folder called `NimStim_ER`.
3. Drag that `NimStim_ER` folder into the repo's existing `resources` folder.

The final layout should be:

```text
emotional_reactivity/
  resources/
    NimStim_ER/
      01F_NE_C.BMP
      01F_NE_C_MIRROR.BMP
      ...
```

## Create The Environment

Run this once from the repo root:

```bash
conda env create -p ./.conda_env -f environment.yml
```

## Run The Experiment

Windowed test run:

```bash
./run_with_env.sh --windowed
```

Fullscreen run:

```bash
./run_with_env.sh
```

Results are saved locally in:

```text
data/
logs/
```

## Task Summary

- 80 trials total
- 20 trials per emotion: happy, angry, neutral, fearful
- 10 actors: `01F, 07F, 09F, 13F, 18F, 32M, 34M, 37M, 39M, 40M`
- Closed-mouth expressions only: `AN_C`, `FE_C`, `HA_C`, `NE_C`
- Neutral targets use `NE_C_MIRROR` images
- Neutral masks use unmirrored `NE_C` images
- Trial timing: 800 ms fixation, 33 ms target, 467 ms mask, 7.7 s response
- Response keys: `1 = happy`, `2 = angry`, `3 = neutral`, `4 = fearful`

The fixed trial order is already included in `conditions/trial_sequence.csv`; runtime does not reshuffle it.
