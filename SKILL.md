---
name: adb-apk-installer
description: Cài file APK / XAPK / APKS / APKM lên thiết bị Android qua ADB (USB hoặc IP) kèm metadata "cài từ CH Play" (installer com.android.vending). Dùng khi người dùng gọi "/adb-apk-installer <đường dẫn file> [IP]", hoặc nhắc "cài apk", "cài xapk", "install apk qua adb", "sideload", "adb install", "giả installer CH Play / Google Play".
argument-hint: "<đường dẫn .apk|.xapk|.apks|.apkm> [IP[:port] | serial]"
metadata:
  short-description: One-shot ADB APK/XAPK installer with Play Store installer metadata
---

# ADB APK & XAPK Installer

Arguments: `$ARGUMENTS` = `<file path> [device IP, IP:port or serial]`.

## Do this

Run the helper once, quoting the path. It lives in `scripts/adb_helper.py` next to this file
(Claude Code: `${CLAUDE_SKILL_DIR}/scripts/adb_helper.py`):

```bash
python "<skill dir>/scripts/adb_helper.py" "<file path>" [ip[:port] | serial]
```

That single command does everything:

1. Finds `adb` (PATH, `ANDROID_HOME`, default SDK locations).
2. Connects: an IP gets `adb connect` (port defaults to `5555`); with no device argument it uses the only attached device.
3. Reads the device ABI list and screen density.
4. For XAPK/APKS/APKM: picks the base APK, all language/feature splits, and only the ABI and density splits that match the device. Stops before installing if no ABI matches.
5. Installs with `-r -i com.android.vending` (`install` or `install-multiple`).
6. Pushes OBB files from the bundle to `/sdcard/Android/obb/<package>/`.
7. Verifies `installerPackageName` via `dumpsys package` and prints an `OK: ...` line.

Exit code 0 and the `OK:` line mean success: report package, version, device and installer to the user.
On `ERROR:` relay the message and its hint; do not retry blindly.

Options: `--dry-run` (show the plan, install nothing), `--installer <package>` (default `com.android.vending`).

## If arguments are missing

- No file path: ask for it.
- No device and the script reports zero or several devices: ask for the IP or serial.

## Do not do without asking

- Uninstalling the existing app (needed for `INSTALL_FAILED_UPDATE_INCOMPATIBLE` / `VERSION_DOWNGRADE`): it wipes app data.

## Connection notes

- Android 11+ Wireless debugging uses a random port and needs one-time pairing:
  `adb pair <ip>:<pair_port> <code>`, then pass the `IP:port` shown on the Wireless debugging screen.
- Classic TCP mode: connect USB once, run `adb tcpip 5555`, then the bare IP works.

More error patterns, Windows driver fixes and Xiaomi settings: [references/troubleshooting.md](references/troubleshooting.md).

Note: the installer attribute only sets what `PackageManager.getInstallSourceInfo()` / `getInstallerPackageName()` returns locally. It does not affect Play Integrity verdicts or Play licensing.
