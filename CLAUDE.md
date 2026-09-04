# tt-disco

Local catalog and launcher for gradio demo apps on scarce Tenstorrent
hardware. Original prompt: novel model demos built as gradio apps
(`tt-vjepa2`, `tt-animatediff`, ...) get built once, shown off, and then
forgotten because there's no easy way to bring them back up — build a
one-click "what demos do I have, can I run one now" catalog. Named after,
and loosely inspired by, the open-source [Disco](https://disco.cloud/) PaaS,
but deliberately **not** a reimplementation of it: Disco's daemon is
Docker-Swarm-only, and that conflicts head-on with how this hardware
actually gets used — `gozer` (the chip-leasing tool) tracks leases by host
PID, `/dev/tenstorrent/*` passthrough into Swarm services means
`--privileged` or fragile custom cgroup rules, and tt-metal wheels are
tightly coupled to the host kernel driver version. tt-disco borrows Disco's
UX idea (a catalog of apps you can bring up/down) without the container
requirement.

## Key decisions from brainstorming

- **Native `systemd --user` processes, not Docker.** Sidesteps all of the
  container/device-passthrough/gozer-PID problems above; the existing apps
  already have working venvs.
- **Manifest-per-repo (`.disco/app.yaml`), not a central registry.** Adding
  an app is just committing a manifest to its own repo; no file elsewhere to
  keep in sync.
- **`gozer` as a soft/optional dependency.** Wrap the launch command with
  `gozer run` only when the binary is on `$PATH` *and* the manifest declares
  `chips`; otherwise `launch` runs unmodified. The same install works for
  someone without Tenstorrent hardware at all.
- **htmx web catalog, not CLI-only.** One FastAPI page, htmx fragment swaps
  for Start/Stop, no JSON API and no frontend build step — a page you can
  leave open in a tab is a better fit for "hardware sits idle, bring a demo
  back up in one click" than a CLI you have to remember to invoke.

## Bugs found during the Task 8 hardware smoke test

- **gozer PATH resolution.** `gozer` resolved bare in the generated
  `ExecStart`, but `systemd --user`'s default PATH excludes `~/.local/bin`,
  so systemd failed with `203/EXEC`. Fixed by resolving `gozer` via
  `shutil.which()` to an absolute path in `build_launch_command`, with a
  fallback to the bare name if `which()` fails (commit `ce9642f`).
- **`GRADIO_SERVER_PORT` mismatch.** The catalog's "Open" link is built from
  the manifest's declared `port`, but `tt-vjepa2` didn't hardcode its own
  `server_port` — when the declared port was busy, gradio silently
  auto-picked a different one, and the "Open" link pointed at nothing. Fixed
  at the manifest level (not core tt-disco code): `tt-vjepa2`'s `launch`
  command now does `export GRADIO_SERVER_PORT=<port>; exec ...` so the
  declared and actual ports always match. Documented in README.md as a
  gotcha for anyone onboarding a new app.

## Final-review fix wave (post-Task-8, all 8 plan tasks already individually reviewed)

A whole-branch review caught issues the per-task reviews missed:

- **Unloadable no-gozer unit (critical).** `build_launch_command` emitted the
  manifest's `launch` verbatim when gozer wasn't wrapping it — e.g.
  `.venv/bin/python app.py`, a relative path containing a slash, which
  systemd's `ExecStart=` rejects outright. Masked previously because gozer's
  own `subprocess.Popen` resolves relative paths fine when it *is* wrapping
  the command. Fixed by resolving the launch command's first token against
  `app.source_dir` whenever it's a slash-containing relative path, applied
  in both the gozer-wrapped and unwrapped cases. Regression test added that
  actually shells out to `systemd-analyze verify` on a rendered unit file
  (skipped if the binary isn't on `PATH`).
- **Templates not packaged.** `disco/templates/*.html` had no
  `[tool.setuptools.package-data]` entry, so a non-editable wheel install
  would raise `TemplateNotFound` on every route. Fixed in `pyproject.toml`.
- **Silent start/stop failures.** `units.start_app()`/`stop_app()` already
  returned a `CompletedProcess` with captured stderr, but the FastAPI routes
  discarded it — a failed `systemctl start` (e.g. from the unit-file bug
  above) redrew the table with no error shown. Fixed by checking
  `returncode` in the routes and rendering the failing row through the same
  "broken" path used for a `BrokenManifest`, with the command's stderr as
  the message.
- **Manifest `name` validation.** An unvalidated `name` flows straight into
  a systemd unit filename and a shell-quoted `gozer --who` argument. Added a
  `re.fullmatch(r"[A-Za-z0-9_.-]+", name)` check in `parse_manifest`.
- **Duplicate app names across manifests.** Two repos declaring the same
  `name` used to collide silently on one systemd unit. `discover_apps` now
  keeps only the first (by existing sort order) as valid and turns every
  later duplicate into a `BrokenManifest` naming the manifest it collided
  with.
