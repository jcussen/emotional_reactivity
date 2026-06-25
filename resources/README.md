# Private NimStim Folder

Place `NimStim.zip` at the project root and unzip it with:

```bash
mkdir -p resources
unzip -q NimStim.zip -d resources
```

The final private folder should be:

```text
resources/NimStim/
```

Check it with:

```bash
test -d resources/NimStim && echo "NimStim folder found"
```

`NimStim.zip`, `NimStim/`, and `resources/NimStim/` are gitignored. Do not commit or publicly share them.
