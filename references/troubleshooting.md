# Android ADB Installation & Troubleshooting Guide

This reference details error patterns, device incompatibility, driver detection fixes, and split APK mechanics.

---

## 1. Installation Errors

### `INSTALL_FAILED_MISSING_SPLIT`
- **Cause:** The application was built as an Android App Bundle (AAB). The APK file being installed is only the `base.apk` with `android:isSplitRequired="true"`, or the device requires resource/ABI splits.
- **Solution:**
  1. Obtain the full **XAPK** or **APKM** package instead of a standalone base APK.
  2. Unpack the XAPK (it is a ZIP archive) to locate all split APKs:
     - `base.apk` (or `<package>.apk`)
     - `config.<abi>.apk` (e.g. `config.arm64_v8a.apk`)
     - `config.<density>.apk`
  3. Install all split APKs together using `adb install-multiple`:
     ```bash
     adb install-multiple -r -i com.android.vending base.apk config.arm64_v8a.apk
     ```

### `INSTALL_FAILED_NO_MATCHING_ABIS`
- **Cause:** The APK contains native libraries compiled for an architecture not supported by the target device's operating system (e.g., 64-bit `arm64-v8a` app installed on a 32-bit `armeabi-v7a` OS).
- **Diagnosis:**
  Check device ABI capabilities:
  ```bash
  adb shell getprop ro.product.cpu.abi
  adb shell getprop ro.product.cpu.abilist
  adb shell getprop ro.product.cpu.abilist64
  ```
  If `ro.product.cpu.abilist64` is empty, the device is running a 32-bit OS and cannot run 64-bit-only applications.
- **Solution:** Obtain an APK build targeting `armeabi-v7a` if provided by the publisher, or install on a 64-bit Android device.

---

## 2. Setting Google Play Installer Metadata

To set the local installer source to Google Play Store (CH Play):
```bash
adb install -r -i com.android.vending app.apk
```
Or for multiple split APKs:
```bash
adb install-multiple -r -i com.android.vending base.apk split1.apk
```

### Verification
Verify the installer source after installation:
```bash
adb shell dumpsys package <package_name> | grep -E -i 'installerPackageName|versionName'
```

*Note:* Setting `installerPackageName=com.android.vending` sets the local `getInstallerPackageName()` attribute in Android's PackageManager. It does not forge server-signed Google Play Integrity API / SafetyNet hardware attestation tokens.

---

## 3. Connection & Driver Issues (Windows)

### Device Not Listed (`adb devices` is empty)
1. **Developer Options:**
   - Tap **Build Number** 7 times in *Settings > About Phone*.
   - Enable **USB Debugging**.
   - On Xiaomi / MIUI / HyperOS: also enable **Install via USB** and **USB debugging (Security settings)**.
2. **Windows Device Driver (WinUsb vs Android ADB Interface):**
   - MediaTek / generic devices may default to a generic `WinUsb Device` without the Android ADB Interface class GUID (`{F72DE06D-451B-4b42-9C08-F4221DCC5F24}`).
   - Fix: Open **Device Manager** > Right-click device > **Update driver** > **Browse my computer...** > **Let me pick from a list...** > Select **Android Device** > **Android Composite ADB Interface**.
3. **Wireless Debugging (Alternative):**
   - On Android 11+, enable **Wireless Debugging** under Developer Options.
   - Connect directly using:
     ```bash
     adb connect <device_ip>:<port>
     ```

