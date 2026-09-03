# tt-disco design

Date: 2026-09-03
Status: approved, pending implementation plan

## Purpose

A local catalog and launcher for gradio demo apps built on Tenstorrent
hardware. Tenstorrent hardware is scarce, and novel models/experiments built
as gradio apps (e.g. `tt-vjepa2`, `tt-animatediff`) tend to get built once,
demoed, and then forgotten because there's no easy way to bring them back up
later. tt-disco exists to make "what demos do I have, and can I pull one up
right now" a one-click question instead of a "how did I run that again"
archaeology exercise.

Named after, and loosely inspired by, [Disco](https://disco.cloud/) — an
open-source self-hosted PaaS (git-push deploys, Docker Swarm-based). tt-disco
is **not** the Disco daemon: Disco's execution model is Docker Swarm-only,
which conflicts with how this hardware actually gets used (see
"Why not real Disco" below). tt-disco borrows Disco's UX idea — a catalog of
apps you can bring up and down — without the container requirement.

Built to be useful beyond this one box: the manifest convention and launcher
are generic enough that anyone else with a gradio app (Tenstorrent-backed or
not) can adopt the same pattern in their own repo.

## Why not real Disco (Docker Swarm)

Considered and rejected for this use case:

- Disco's daemon orchestrates only via Docker Swarm — there's no
  non-container execution mode to opt into.
- Swarm services don't support arbitrary `--device` passthrough the way
  `docker run` does; getting `/dev/tenstorrent/*` into a container means
  `--privileged` (broad) or custom cgroup device rules in the Docker daemon
  config (fragile, easy to break on a kernel/driver update).
- `gozer` (the chip-leasing tool used on this box) tracks leases by host PID.
  A containerized process lives in a different PID namespace, so gozer would
  need to become container-aware, or leases would need to be acquired outside
  the container and threaded in — new plumbing that doesn't exist today.
- tt-metal wheels are tightly coupled to the host kernel driver (KMD/UMD)
  version; baking that into an image means keeping the image in lockstep with
  whatever's on the host.
- The existing apps already have working venvs. Docker would mean
  re-solving those dependency chains inside Dockerfiles for no functional
  gain here.

None of this rules out revisiting Docker later if isolation or multi-host
deploys become real requirements — it's just not worth the cost today.

## Someday: networking catalogs together

Out of scope for this design, but worth recording the direction so later
work doesn't have to rediscover it: MCP is the wrong protocol for this (it's
built for LLM tool/resource access, not for syndicating a feed of apps and
saved states). AT Protocol's model — portable records via a personal data
server, custom lexicons, firehose/feed-generator discovery — is a much
closer conceptual match for "a feed of demos and the states people saved
them in" across boxes or people. Nothing in this design should depend on
that, but state that tt-disco persists (see below) should stay in plain,
easily-migratable formats (YAML/JSON) so a future federation layer could
ingest it without a rewrite.

## Architecture

### 1. Manifest convention

Each app repo declares itself via `.disco/app.yaml` at its root:

```yaml
name: vjepa2
description: V-JEPA2 video embedding demo
port: 7860
chips: 1          # optional; advisory only, see gozer integration below
launch: .venv/bin/python gradio_app/app.py
```

- `path` is implicit — wherever the manifest file was found.
- `chips` is optional metadata. tt-disco does not require or validate it
  beyond passing it to gozer when gozer is present (see below).
- `launch` is run with cwd set to the manifest's directory.

### 2. Discovery

tt-disco scans a configured parent directory (default `~/code`) for any
`*/.disco/app.yaml` and treats each match as a catalog entry. Adding a new
app later is just dropping a manifest into its repo — no central registry
to edit. A manifest that fails to parse produces a "broken" entry in the
catalog (with the parse error shown) rather than aborting discovery.

### 3. Launch and supervision

Starting an app renders and installs a `systemd --user` unit named
`disco-<name>.service`, with `ExecStart` set to the manifest's `launch`
command (run from the app's directory):

- If the `gozer` binary is found on `$PATH` **and** the manifest declares
  `chips`, the generated `ExecStart` wraps the launch command:
  `gozer run --chips <N> --who "disco:<name>" --reason "gradio demo" -- <launch>`.
- Otherwise `launch` runs directly, unmodified.

This makes gozer a soft dependency: the same tt-disco install works
unchanged for someone without Tenstorrent hardware or without gozer
installed — `chips` is simply ignored in that case.

Stopping an app is `systemctl --user stop disco-<name>.service`. Status is
read via `systemctl --user is-active`. Logs are read via
`journalctl --user -u disco-<name>.service`.

### 4. Catalog web page

A small FastAPI app serves:

- A list page: each discovered app's name, description, and status
  (running / stopped / broken), with Start/Stop buttons and — once
  running — a link to `http://localhost:<port>`.
- A JSON API underneath the page (list apps, start, stop, status) that the
  page itself calls.
- htmx handles in-page status/button updates without a full reload or any
  frontend build step.

No reverse proxy or custom hostnames for now — links are plain
`localhost:<port>` using the manifest's declared port.

## Data flow

1. On page load / refresh, the FastAPI app re-scans `~/code/*/.disco/app.yaml`
   and queries `systemctl --user is-active` for each known unit name to build
   the current status table.
2. Clicking Start: FastAPI writes/updates the unit file from the manifest,
   runs `systemctl --user daemon-reload` + `start`, and returns updated status.
3. Clicking Stop: FastAPI runs `systemctl --user stop`.
4. Clicking the app's link opens `http://localhost:<port>` in a new tab —
   this is just the gradio app's own UI, untouched by tt-disco.

## Error handling

- Manifest parse errors: surfaced per-entry as "broken", discovery continues
  for other apps.
- Missing `gozer` binary: silent degrade, no lease wrapping, `chips` ignored.
- Port already in use / launch command fails: surfaces as the unit's failed
  status in the catalog; full detail available via the logs
  (`journalctl --user -u disco-<name>.service`), not duplicated into the web
  UI in this design.
- Missing `systemd --user` support (e.g. no lingering user session): treated
  as an environment precondition, not handled specially by tt-disco.

## Testing

- Unit tests: manifest parsing (valid, malformed, missing fields), directory
  discovery, and systemd unit-file generation (with and without gozer
  wrapping).
- Manual smoke test: stand up the two real apps (`tt-vjepa2`, `tt-animatediff`)
  end-to-end through the catalog page, since the systemd/gozer interaction
  isn't practically unit-testable.

## Scope for this pass

- Onboard exactly two apps: `tt-vjepa2` and `tt-animatediff`.
- No reverse proxy / custom hostnames.
- No multi-host networking or federation (see "Someday" above).
- No saved-session/input-state persistence yet — out of scope until a
  concrete need for it shows up.
