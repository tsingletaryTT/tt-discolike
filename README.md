# tt-disco

tt-disco is a local catalog and launcher for gradio demo apps built on
Tenstorrent hardware. Tenstorrent chips are scarce, and one-off gradio demos
(e.g. `tt-vjepa2`, `tt-animatediff`) tend to get built once, shown off, and
then forgotten because there's no easy way to bring them back up later.
tt-disco turns "what demos do I have, and can I pull one up right now" into
a one-click question: it scans your repos for a small manifest file, lists
what it finds in a web page, and lets you start/stop each app as a
`systemd --user` unit, with an optional handoff to `gozer` for chip leasing.

## The manifest: `.disco/app.yaml`

Any repo becomes a catalog entry by dropping a `.disco/app.yaml` file at its
root:

```yaml
name: vjepa2
description: V-JEPA2 video embedding demo
port: 7860
chips: 1          # optional; advisory only, passed to gozer if present
launch: .venv/bin/python gradio_app/app.py
```

| Field         | Required | Meaning                                                                 |
|---------------|----------|--------------------------------------------------------------------------|
| `name`        | yes      | Catalog identifier. Must match `[A-Za-z0-9_.-]+` — it becomes the systemd unit name (`disco-<name>.service`) and is shell-quoted into a `gozer --who` argument, so path separators and quote characters are rejected. |
| `description` | yes      | Free text shown in the catalog table.                                   |
| `port`        | yes      | The port the app's own server listens on. Used to build the catalog's "Open" link (`http://localhost:<port>`). |
| `launch`      | yes      | Shell command that starts the app, run with cwd set to the app's own directory (the manifest's parent's parent). A relative executable path (e.g. `.venv/bin/python`) is resolved to an absolute path against that directory before being placed in the generated systemd unit — systemd's `ExecStart=` rejects a relative path containing a slash. |
| `chips`       | no       | Number of Tenstorrent chips this app wants. Purely advisory: tt-disco does not validate or reserve anything itself. If `gozer` is on `$PATH` *and* `chips` is set, the launch command is wrapped with `gozer run --chips <N> ...` (see below). If either condition is false, `launch` runs completely unmodified. |

Two names cannot collide: if two manifests under the scanned root declare
the same `name`, only the first one found (by manifest path sort order) is
treated as valid — every later one is shown in the catalog as a broken entry
naming the manifest it collided with, rather than silently sharing one
systemd unit.

## Discovery

On every page load, tt-disco scans a configured parent directory for
`*/.disco/app.yaml` (one level deep) and treats each match as a catalog
entry:

- Scan root: `DISCO_SCAN_ROOT` environment variable, default `~/code`.
- A manifest that fails to parse (bad YAML, missing required field, invalid
  `port`/`chips`, invalid `name`) shows up as a "broken" row with the parse
  error, instead of aborting discovery for every other app.

There is no central registry to edit — adding an app is just committing a
manifest to its own repo.

## Running the catalog

Install the package (editable, for development: `pip install -e .`) and run
the `disco` console-script entry point:

```bash
disco
```

Configuration is via environment variables:

- `DISCO_HOST` — interface to bind, default `127.0.0.1`.
- `DISCO_CATALOG_PORT` — port to serve the catalog page on, default `8760`.
- `DISCO_SCAN_ROOT` — parent directory to scan for manifests, default `~/code`.

The catalog is a small FastAPI app (`disco/main.py` → `disco/app.py`)
serving one page (`GET /`) built from htmx fragments — clicking Start/Stop
(`POST /apps/{name}/start` / `POST /apps/{name}/stop`) re-renders just the
table via an HTML partial, no full page reload and no frontend build step.
There is no separate JSON API; the page and its buttons are the only
interface.

Starting an app renders and installs a `systemd --user` unit
(`disco-<name>.service`) from the manifest's `launch` command, then runs
`systemctl --user daemon-reload` + `start`. Stopping runs
`systemctl --user stop`. Status is read via `systemctl --user is-active`,
and deeper diagnostics are a `journalctl --user -u disco-<name>.service`
away — tt-disco itself only reflects the immediate start/stop command's
success or failure in the catalog row, it does not tail logs.

## gozer: a soft dependency

[`gozer`](https://en.wikipedia.org/wiki/Gozer) is this box's chip-leasing
tool. tt-disco treats it as entirely optional:

- If the `gozer` binary is found on `$PATH` **and** the manifest declares
  `chips`, the generated `ExecStart` wraps the launch command:
  `gozer run --chips <N> --who "disco:<name>" --reason "gradio demo" -- <launch>`.
- Otherwise `launch` runs directly, unmodified.

This means the exact same tt-disco install works unchanged for someone
without Tenstorrent hardware, or without gozer installed — `chips` is
simply ignored in that case. Both the `gozer` binary itself and the wrapped
launch command are resolved to absolute paths before being written into the
unit file, since systemd's user manager runs with a restricted `$PATH` that
does not include `~/.local/bin` (a real bug hit during integration testing:
`gozer` resolved bare in `ExecStart` and systemd failed with `203/EXEC`
because it couldn't find it).

## Gotcha: `GRADIO_SERVER_PORT` and the "Open" link

The catalog's "Open" link is built from the manifest's declared `port` —
tt-disco never asks the running app what port it actually bound. Most
gradio apps respect `server_port` as passed by their own code, but an app
that does **not** hardcode `server_port` will fall back to gradio's own
"find a free port" behavior if the declared port happens to be busy when it
starts. When that happens, the app ends up listening on some other port
entirely, silently diverging from what the catalog's link expects — the
"Open" link then points at nothing (or at an unrelated service on that
port).

This bit `tt-vjepa2` during integration testing. The fix belongs at the
manifest/app level, not in tt-disco itself: force the port via an
environment variable in the `launch` command so the declared and actual
ports are always the same, e.g.:

```yaml
launch: bash -c 'export GRADIO_SERVER_PORT=7861; exec .venv/bin/python gradio_app/app.py'
```

If you're onboarding a new gradio app to tt-disco, either hardcode
`server_port=<manifest port>` in the app's own `demo.launch(...)` call, or
use the `GRADIO_SERVER_PORT=<port>` pattern above in `launch` — whichever
is easier to keep in sync with the manifest's `port` field.
