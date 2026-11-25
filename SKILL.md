---
name: adb-apk-installer
description: Locate ADB, diagnose connected Android devices, verify ABI architecture, and install standalone or split APK/XAPK packages with Google Play installer metadata (-i com.android.vending).
metadata:
  short-description: ADB APK and XAPK installer with Play Store metadata
---

# ADB APK & XAPK Installer

Diagnose Android device connections, resolve device architecture and driver mismatches, and install single or split APK (XAPK/APKM) packages with Google Play Store installer attribution.

## Core Capabilities

- **Device Diagnostics:** Detect USB or Wireless ADB devices, identify hardware/OS ABI architecture (32-bit `armeabi-v7a` vs 64-bit `arm64-v8a`), and troubleshoot missing drivers.
- **Package Inspection:** Differentiate between standard monolithic APKs and split APK bundles (AAB / XAPK), extracting native libraries and configuration splits.
- **Installation with Attribution:** Install single or multiple split APKs with `-i com.android.vending` to set Google Play Store as the installer package.

---

## Workflow

### 1. Check Connected Devices & ADB
Locate `adb` executable and query attached devices:
```bash
adb devices -l
```
If using Wireless Debugging (Android 11+):
```bash
adb connect <ip>:<port>
```

### 2. Verify Device Architecture (ABI)
Avoid `INSTALL_FAILED_NO_MATCHING_ABIS` by checking CPU architecture support before installation:
```bash
adb shell getprop ro.product.cpu.abi
adb shell getprop ro.product.cpu.abilist64
```
- If `ro.product.cpu.abilist64` is empty, the device is running a 32-bit OS and cannot execute 64-bit-only (`arm64-v8a`) binaries.

### 3. Handle APK vs XAPK / Split APKs
- **Single APK:** Install directly:
  ```bash
  adb install -r -i com.android.vending <path_to_apk>
  ```
- **XAPK / Split APKs:** If the target is an `.xapk` archive or an app bundle (which throws `INSTALL_FAILED_MISSING_SPLIT` if installed alone):
  1. Extract the `.xapk` archive (it is a standard ZIP file).
  2. Locate `base.apk` (or `<package>.apk`) and architecture splits (`config.<abi>.apk`).
  3. Install all split APKs in a single session:
     ```bash
     adb install-multiple -r -i com.android.vending base.apk config.arm64_v8a.apk
     ```

### 4. Verify Installation
Confirm installation and installer metadata:
```bash
adb shell dumpsys package <package_name> | grep -E -i 'installerPackageName|versionName'
```

---

## Automation Helper Script

The skill includes a deterministic helper script at `scripts/adb_helper.py`:

```bash
# List devices
python scripts/adb_helper.py devices

# Inspect device specs and ABIs
python scripts/adb_helper.py info -s <device_or_ip:port>

# Inspect an APK or XAPK
python scripts/adb_helper.py inspect <path_to_apk_or_xapk>

# Install APK or XAPK (automatically extracts and uses install-multiple for XAPKs)
python scripts/adb_helper.py install <path_to_apk_or_xapk> -s <device_or_ip:port>
```

---

## Troubleshooting & References

For detailed resolutions on `INSTALL_FAILED_MISSING_SPLIT`, `INSTALL_FAILED_NO_MATCHING_ABIS`, Windows USB driver gán `WinUsb Device`, and Xiaomi/MIUI settings, consult [references/troubleshooting.md](references/troubleshooting.md).
