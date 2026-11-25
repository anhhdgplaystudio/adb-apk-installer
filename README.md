# ADB APK Installer (agent skill)

A skill for Claude Code / Codex plus a standalone CLI: install an APK, XAPK, APKS or APKM over ADB with Google Play installer metadata in one command.

## Usage

As a skill:

```
/adb-apk-installer <file path> [ip[:port] | serial]
```

As a CLI:

```bash
python scripts/adb_helper.py <file path> [ip[:port] | serial]
python scripts/adb_helper.py app.xapk 192.168.1.50            # port defaults to 5555
python scripts/adb_helper.py app.apk 192.168.1.50:37123       # Android 11+ wireless debugging
python scripts/adb_helper.py app.xapk                         # the only attached device
python scripts/adb_helper.py app.xapk 192.168.1.50 --dry-run  # show the plan only
```

## What it does

- Locates `adb` and connects to the device (USB serial or IP).
- Reads the device ABI list and density, then selects only the matching splits.
- Aborts before installing when the package has no native libraries for the device.
- Installs with `-r -i com.android.vending` (`install` / `install-multiple`).
- Pushes OBB expansion files found in the bundle.
- Verifies `installerPackageName` with `dumpsys package`.

Requires Python 3.8+ and Android SDK platform-tools. No third-party packages.

## Structure

- `SKILL.md`: skill instructions.
- `agents/openai.yaml`: Codex interface configuration.
- `scripts/adb_helper.py`: the installer.
- `references/troubleshooting.md`: common ADB errors and driver fixes.

## Install the skill

Copy this folder to `~/.claude/skills/adb-apk-installer` (Claude Code) or your Codex skills directory.
