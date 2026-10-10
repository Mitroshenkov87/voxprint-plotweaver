# Plotweaver command line

`plotweaver --version` and `plotweaver version` print the display label and nothing else:

```text
0.2.0 RC · build dev "Sefer"
```

`BUILD.json` at the repository root is the source for the version, the prerelease, the codename, and the build offset. A packaged CI build replaces `dev` with `GITHUB_RUN_NUMBER + offset`. A final release (`prerelease` null or empty) drops ` RC`.

Other apps call the commands below. Each of them accepts `--json` and `--dry-run`.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | The command finished. A dry-run that only printed a plan is 0. `vxbook validate` is 0 when there is no error (warnings are allowed). |
| 1 | `PlotweaverError`: bad input, a model failure, or `vxbook validate` found an error. |
| 2 | The GPU is not an NVIDIA RTX 40-series or newer. Argparse also uses 2 when the command line itself is rejected. |
| 3 | `scenario-mars` finished in a state other than `completed`. |

With `--json`, stdout is one JSON object. Failures are `{"ok": false, "error": "...", "code": N}` on stdout. Progress lines, when a command has any, go to stderr so they do not break the object. Without `--json`, errors stay on stderr and the existing text format is unchanged.

Argparse usage errors are not JSON.

## `--dry-run`

`--dry-run` checks the inputs and prints the planned actions and output paths. It does not create a project, write an export, rewrite the registry, download a model, or start llama.cpp.

`models list --dry-run` still reads the registry, because the list is the result of that read, and then writes nothing.

## `--json` objects

Every object has `ok` (boolean), `command` (string), and `code` (integer, the process exit code). Commands that accept `--dry-run` also have `dry_run` (boolean).

### `run` and `scenario-mars`

Generate a book and its exports. `run` is the general command. `scenario-mars` writes the short Russian Mars story. `book.vxbook` is always one of the outputs. EPUB 3 is always included. `--fb2`, `--docx`, `--markdown`, `--speaker-marks`, and `--sound` add the extra files.

Dry-run:

```json
{
  "ok": true,
  "command": "run",
  "dry_run": true,
  "code": 0,
  "project": "/absolute/project",
  "resume": false,
  "mock": true,
  "actions": ["create the project", "generate the book with the mock backend", "write the export files, including book.vxbook"],
  "outputs": ["/absolute/project/export/book.vxbook", "/absolute/project/export/book.epub", "/absolute/project/export/overlap-report.json"]
}
```

`scenario-mars` uses `"command": "scenario-mars"` and omits `resume`.

After a real `run`:

```json
{
  "ok": true,
  "command": "run",
  "dry_run": false,
  "code": 0,
  "status": "completed",
  "gate": null,
  "swaps": 0,
  "refusals": 0,
  "placeholders": 0,
  "rewrites": 0,
  "project": "/absolute/project",
  "export_dir": "/absolute/export",
  "outputs": ["/absolute/export/book.vxbook"]
}
```

`status` is `completed` or `waiting`. `gate` is a string while the book is waiting for approval, otherwise null. `scenario-mars` omits `gate`, `refusals`, `placeholders`, and `rewrites`. Its `code` is 3 and `ok` is false when `status` is not `completed`.

Output names, relative to the export directory:

| File | When |
| --- | --- |
| `book.vxbook` | always |
| `book.epub` | always |
| `overlap-report.json` | always |
| `book.fb2` | `--fb2` |
| `book.docx` | `--docx` |
| `book.md` | `--markdown` |
| `audiobook/book.md` and `audiobook/speaker-marks.txt` | `--speaker-marks` |
| `book.sound.vxbook` | `--sound` |

### `export`

Export a project that already has `project.json` and `artefacts/outline.json`. This does not draft. `--sound` is the only flag that runs a model, and a dry-run does not run it.

```json
{
  "ok": true,
  "command": "export",
  "dry_run": true,
  "code": 0,
  "project": "/absolute/project",
  "title": "Title",
  "actions": ["read the generated project", "write the export files, including book.vxbook"],
  "outputs": ["/absolute/project/export/book.vxbook"]
}
```

A finished export has `export_dir` and `outputs`, and no `title` or `actions`.

### `sound add`

```text
plotweaver sound add SOURCE -o OUTPUT [--mirror] [--mock] [--json] [--dry-run]
```

`SOURCE` is a `.vxbook` file or a project directory that contains one. The source is not modified.

```json
{
  "ok": true,
  "command": "sound.add",
  "dry_run": false,
  "code": 0,
  "source": "/absolute/book.vxbook",
  "output": "/absolute/book.sound.vxbook",
  "mirror": false,
  "warnings": []
}
```

A dry-run has `actions` and `outputs` instead of `warnings`. It validates the source book and does not write.

### `vxbook validate`

```text
plotweaver vxbook validate FILE [--json] [--dry-run]
```

```json
{
  "ok": true,
  "command": "vxbook.validate",
  "dry_run": false,
  "code": 0,
  "file": "/absolute/book.vxbook",
  "issues": [{"severity": "warning", "message": "..."}]
}
```

`severity` is `error` or `warning`. Any error sets `ok` to false and `code` to 1. A dry-run checks that `FILE` exists and reports the planned checklist. It does not open the archive:

```json
{
  "ok": true,
  "command": "vxbook.validate",
  "dry_run": true,
  "code": 0,
  "file": "/absolute/book.vxbook",
  "actions": ["run the Voxprint Book validation checklist"],
  "outputs": []
}
```

### `models list`

```text
plotweaver models list [--registry PATH] [--json] [--dry-run]
```

```json
{
  "ok": true,
  "command": "models.list",
  "dry_run": false,
  "code": 0,
  "registry": "/absolute/bakeoff/models.toml",
  "actions": ["read the model registry"],
  "models": [
    {
      "id": "t-pro-it-2.1-q4",
      "enabled": true,
      "tier": "24gb",
      "role": "main",
      "filename": "model.gguf",
      "repo": "org/name",
      "revision": "abc",
      "sha256": "0123...",
      "size": 1,
      "license": "apache-2.0",
      "min_vram_gb": 16,
      "uncensored": false,
      "optional": false,
      "default": true,
      "languages": ["ru"]
    }
  ]
}
```

### `models import-forge-manifest`

```text
plotweaver models import-forge-manifest FILE [--registry PATH] [--json] [--dry-run]
```

`FILE` is JSON `{"models": [{"id", "revision", "sha256", "size", ...}]}`. Without `--dry-run` the matching placeholder rows are enabled. `--dry-run` validates the file and leaves the registry byte for byte.

```json
{
  "ok": true,
  "command": "models.import-forge-manifest",
  "dry_run": true,
  "code": 0,
  "registry": "/absolute/bakeoff/models.toml",
  "manifest": "/absolute/forge.json",
  "models": ["t-lite-it-2.1-forge-abliterated-q4"],
  "writes": false,
  "actions": ["validate the Model Forge manifest", "leave the registry unchanged"]
}
```

`writes` is true when the registry was updated. `models` is the list of ids that were enabled, or that would be enabled.
