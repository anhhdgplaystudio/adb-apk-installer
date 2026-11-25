# ADB APK Installer (Codex Skill)

A Codex skill and CLI helper for Android device management, package architecture verification, and APK / XAPK sideloading with Play Store installer metadata attribution.

## Features

- **Device Architecture Inspection:** Detects CPU ABI (`armeabi-v7a` vs `arm64-v8a`) to avoid installation failures.
- **Split APK & XAPK Support:** Automatically extracts and handles Android App Bundle splits via `adb install-multiple`.
- **Installer Attribution:** Installs packages with `-i com.android.vending` and verifies metadata via `dumpsys package`.
- **Connection Helper:** Supports both USB and Android 11+ Wireless Debugging.

## Structure

- `SKILL.md`: Main instructions and workflow definition for Codex.
- `agents/openai.yaml`: Codex interface configuration.
- `scripts/adb_helper.py`: Automation script for device queries, inspection, and installation.
- `references/troubleshooting.md`: Technical guide for common ADB errors and device driver fixes.

## Quick Usage

```bash
# List connected devices
python scripts/adb_helper.py devices

# Check device CPU architecture
python scripts/adb_helper.py info -s <device_id_or_ip:port>

# Inspect an APK or XAPK package
python scripts/adb_helper.py inspect <file_path>

# Install APK or XAPK
python scripts/adb_helper.py install <file_path> -s <device_id_or_ip:port>
```
