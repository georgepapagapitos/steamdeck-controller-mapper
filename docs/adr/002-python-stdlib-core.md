# ADR-002: Python 3, stdlib-only core

**Status:** Proposed

## Context

The core must run (a) in the `mh-run` launch wrapper on SteamOS (read-only rootfs, no
package manager by default), (b) inside the Decky backend (Python), and
(c) in CI.

## Decision

Write `mh-core` in Python 3 using only the standard library. Vendor any
unavoidable pure-Python dependency into the package. Minimum Python is **3.11**
(oldest system Python on supported SteamOS releases, spike S12).

Always run mh-core on the **system Python** (`/usr/bin/python3 -I`), never inside
Decky's bundled interpreter. Decky is a PyInstaller binary that ships only the
stdlib modules the loader itself imports (decky-loader issue #968). The Decky
backend talks to an mh-core worker subprocess over JSON on stdin/stdout. See
[14](../14-packaging-permissions.md).

## Consequences

- ➕ One codebase for CLI, wrapper and Decky backend; nothing to install beyond our own files.
- ➖ An extra process boundary between the Decky backend and the core.
- ➕ Easy for contributors.
- ➖ Must write round-trip parsers ourselves (INI dialects, RA cfg, minimal YAML, TOML editing, XML via `xml.etree` with care about formatting).
- ➖ Startup time matters for the hook. Keep imports lazy and adapters loaded on demand.
