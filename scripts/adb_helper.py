#!/usr/bin/env python3
"""One-shot ADB installer with Google Play installer metadata.

Usage:
    python adb_helper.py <file.apk|.xapk|.apks|.apkm> [ip[:port] | serial]

Steps: locate adb -> connect -> read device ABI/density -> pick matching
splits -> install with `-i com.android.vending` -> push OBB -> verify.
"""
import argparse
import json
import os
import posixpath
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

PLAY_STORE = "com.android.vending"
DEFAULT_PORT = "5555"

IP_RE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})(?::(\d+))?$")
ABI_RE = re.compile(
    r"(?:^|[._\-])(arm64[_\-]v8a|armeabi[_\-]v7a|armeabi|x86[_\-]64|x86)(?=$|[._\-])", re.I
)
DPI_RE = re.compile(r"(?:^|[._\-])(ldpi|mdpi|tvdpi|hdpi|xhdpi|xxhdpi|xxxhdpi)(?=$|[._\-])", re.I)
DPI_VALUES = {"ldpi": 120, "mdpi": 160, "tvdpi": 213, "hdpi": 240,
              "xhdpi": 320, "xxhdpi": 480, "xxxhdpi": 640}

FAILURE_HINTS = {
    "INSTALL_FAILED_UPDATE_INCOMPATIBLE": "Signature differs from the installed app. Uninstall it first "
                                          "(adb uninstall <package>) - this wipes its data.",
    "INSTALL_FAILED_VERSION_DOWNGRADE": "A newer version is installed. Uninstall it first or install a newer build.",
    "INSTALL_FAILED_USER_RESTRICTED": "Xiaomi/MIUI/HyperOS: enable 'Install via USB' and 'USB debugging "
                                      "(Security settings)' in Developer options, then accept the prompt on the phone.",
    "INSTALL_FAILED_INSUFFICIENT_STORAGE": "Free up storage on the device.",
    "INSTALL_FAILED_MISSING_SPLIT": "This APK is only the base of an app bundle. Use the full XAPK/APKS/APKM.",
    "INSTALL_FAILED_NO_MATCHING_ABIS": "The package has no native libraries for this device's CPU architecture.",
    "INSTALL_FAILED_OLDER_SDK": "The device's Android version is lower than the app's minSdkVersion.",
    "INSTALL_PARSE_FAILED_NO_CERTIFICATES": "The APK is unsigned or corrupted.",
}


class Fail(Exception):
    pass


def log(msg):
    print(msg, flush=True)


def run(cmd, timeout=None):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


# ---------------------------------------------------------------- adb / device

def find_adb():
    found = shutil.which("adb")
    if found:
        return found
    exe = "adb.exe" if os.name == "nt" else "adb"
    home = os.path.expanduser("~")
    roots = [
        os.environ.get("ANDROID_HOME"),
        os.environ.get("ANDROID_SDK_ROOT"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk") if os.name == "nt" else None,
        os.path.join(home, "Library", "Android", "sdk"),
        os.path.join(home, "Android", "Sdk"),
        r"C:\Android\Sdk" if os.name == "nt" else None,
    ]
    candidates = [os.path.join(r, "platform-tools", exe) for r in roots if r]
    candidates += [
        os.path.join(home, "platform-tools", exe),
        os.path.join(home, "Downloads", "platform-tools", exe),
    ]
    if os.name == "nt":
        candidates.append(r"C:\platform-tools\adb.exe")
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise Fail("adb not found. Install Android SDK platform-tools or add adb to PATH.")


def list_devices(adb):
    out = run([adb, "devices"], timeout=30).stdout
    devices = []
    for line in out.splitlines():
        if "\t" in line:
            serial, state = line.split("\t", 1)
            devices.append((serial.strip(), state.strip()))
    return devices


def resolve_device(adb, target):
    if target:
        m = IP_RE.match(target)
        if m:
            serial = target if m.group(2) else f"{target}:{DEFAULT_PORT}"
            res = run([adb, "connect", serial], timeout=30)
            text = (res.stdout + res.stderr).strip()
            if "connected to" not in text:
                raise Fail(
                    f"adb connect {serial} failed: {text}\n"
                    "  - Phone and PC must be on the same network.\n"
                    "  - Android 11+ Wireless debugging uses a random port: pass the IP:port shown on the\n"
                    "    Wireless debugging screen, and pair once first with `adb pair <ip>:<pair_port> <code>`.\n"
                    "  - Classic TCP mode: plug in USB once and run `adb tcpip 5555`."
                )
        else:
            serial = target
    else:
        ready = [s for s, st in list_devices(adb) if st == "device"]
        if len(ready) == 1:
            serial = ready[0]
        elif not ready:
            raise Fail("No device connected. Pass the device IP (or IP:port) as the second argument.")
        else:
            raise Fail("Several devices connected, pass one as the second argument: " + ", ".join(ready))

    try:
        run([adb, "-s", serial, "wait-for-device"], timeout=15)
    except subprocess.TimeoutExpired:
        state = dict(list_devices(adb)).get(serial, "not found")
        hint = ""
        if state == "unauthorized":
            hint = " Accept the 'Allow USB debugging' prompt on the phone and run again."
        raise Fail(f"Device {serial} is not ready (state: {state}).{hint}")
    return serial


def device_props(adb, serial):
    out = run([adb, "-s", serial, "shell", "getprop"], timeout=30).stdout
    props = {}
    for line in out.splitlines():
        m = re.match(r"^\[(.+?)\]: \[(.*)\]\s*$", line)
        if m:
            props[m.group(1)] = m.group(2)
    return props


def norm_abi(abi):
    return abi.strip().lower().replace("-", "_")


def device_abis(props):
    raw = props.get("ro.product.cpu.abilist") or ",".join(
        filter(None, [props.get("ro.product.cpu.abi"), props.get("ro.product.cpu.abi2")]))
    return [norm_abi(a) for a in raw.split(",") if a.strip()]


def device_dpi(props):
    for key in ("ro.sf.lcd_density", "qemu.sf.lcd_density"):
        try:
            return int(props.get(key, ""))
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- package analysis

def _axml_package(d):
    """Read the `package` attribute from a binary AndroidManifest.xml."""
    pos, strings = 8, None
    while pos + 8 <= len(d):
        ctype, hsize, csize = struct.unpack_from("<HHI", d, pos)
        if csize < 8:
            break
        if ctype == 0x0001:  # string pool
            count, _, flags, sstart = struct.unpack_from("<IIII", d, pos + 8)
            utf8, offs, base = bool(flags & 0x100), pos + hsize, pos + sstart

            def strings(i, count=count, utf8=utf8, offs=offs, base=base):
                if i >= count:
                    return None
                o = base + struct.unpack_from("<I", d, offs + 4 * i)[0]
                if utf8:
                    o += 2 if d[o] & 0x80 else 1
                    n = d[o]
                    if n & 0x80:
                        n = ((n & 0x7F) << 8) | d[o + 1]
                        o += 2
                    else:
                        o += 1
                    return d[o:o + n].decode("utf-8", "replace")
                n = struct.unpack_from("<H", d, o)[0]
                o += 2
                if n & 0x8000:
                    n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", d, o)[0]
                    o += 2
                return d[o:o + 2 * n].decode("utf-16-le", "replace")
        elif ctype == 0x0102 and strings:  # first start-element = <manifest>
            astart, asize, acount = struct.unpack_from("<HHH", d, pos + 24)
            for i in range(acount):
                a = pos + 16 + astart + i * asize
                _, name, raw, _, _, dtype, data = struct.unpack_from("<IIIHBBI", d, a)
                if strings(name) == "package":
                    return strings(data if dtype == 3 else raw)
            return None
        pos += csize
    return None


def apk_package_name(apk_path):
    try:
        with zipfile.ZipFile(apk_path) as z:
            return _axml_package(z.read("AndroidManifest.xml"))
    except Exception:
        return None


def apk_lib_abis(apk_path):
    abis = set()
    try:
        with zipfile.ZipFile(apk_path) as z:
            for n in z.namelist():
                parts = n.split("/")
                if len(parts) > 2 and parts[0] == "lib":
                    abis.add(norm_abi(parts[1]))
    except Exception:
        pass
    return abis


def stem(name):
    return posixpath.basename(name)[:-4]


def select_splits(apk_names, abis, dpi):
    """Keep only the ABI and density splits that match the device."""
    notes = []
    abi_groups = {}  # module -> {abi: apk}
    for n in apk_names:
        m = ABI_RE.search(stem(n))
        if m:
            key = stem(n)[:m.start()] + stem(n)[m.end():]
            abi_groups.setdefault(key, {})[norm_abi(m.group(1))] = n
    selected = list(apk_names)
    if abi_groups:
        drop, picked = set(), set()
        for options in abi_groups.values():
            chosen = next((a for a in abis if a in options), None)
            if not chosen:
                raise Fail(
                    f"No matching ABI: package has splits for {sorted(options)}, device supports {abis}. "
                    "Get a build for this architecture.")
            picked.add(chosen)
            drop.update(n for a, n in options.items() if a != chosen)
        selected = [n for n in selected if n not in drop]
        notes.append(f"ABI split: {'/'.join(sorted(picked))}")

    if dpi:
        groups = {}
        for n in selected:
            m = DPI_RE.search(stem(n))
            if m:
                key = stem(n)[:m.start()] + stem(n)[m.end():]
                groups.setdefault(key, {})[m.group(1).lower()] = n
        drop, picked = set(), set()
        for options in groups.values():
            ordered = sorted(options, key=DPI_VALUES.get)
            best = next((b for b in ordered if DPI_VALUES[b] >= dpi), ordered[-1])
            picked.add(best)
            drop.update(n for b, n in options.items() if b != best)
        if picked:
            selected = [n for n in selected if n not in drop]
            notes.append(f"density split: {'/'.join(sorted(picked))} (device {dpi}dpi)")
    return selected, notes


def prepare(path, abis, dpi, workdir):
    """Return (apk_paths, obb_list[(local, remote)], package_name, notes)."""
    if not os.path.isfile(path):
        raise Fail(f"File not found: {path}")
    if not zipfile.is_zipfile(path):
        raise Fail(f"Not a valid APK/XAPK archive: {path}")

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        inner = [n for n in names if n.lower().endswith(".apk")]
        if not inner:  # plain APK
            apks, obbs, package, notes = [path], [], None, ["single APK"]
        else:
            manifest = {}
            if "manifest.json" in names:
                try:
                    manifest = json.loads(z.read("manifest.json").decode("utf-8", "replace"))
                except ValueError:
                    manifest = {}
            package = manifest.get("package_name") if isinstance(manifest, dict) else None
            splits_dir = [n for n in inner if n.startswith("splits/")]  # bundletool .apks
            chosen, notes = select_splits(splits_dir or inner, abis, dpi)
            notes.insert(0, f"bundle: {len(chosen)}/{len(inner)} APKs selected")
            apks = [z.extract(n, workdir) for n in chosen]

            obbs = []
            remote_by_file = {}
            for exp in (manifest.get("expansions") or []) if isinstance(manifest, dict) else []:
                if isinstance(exp, dict) and exp.get("file") and exp.get("install_path"):
                    remote_by_file[exp["file"]] = "/sdcard/" + exp["install_path"].lstrip("/")
            for n in names:
                if n.lower().endswith(".obb"):
                    obbs.append((n, remote_by_file.get(n)))
            obbs = [(z.extract(n, workdir), remote, posixpath.basename(n)) for n, remote in obbs]

    if not package:
        for a in apks:
            package = apk_package_name(a)
            if package:
                break

    libs = set()
    for a in apks:
        libs |= apk_lib_abis(a)
    if libs and abis and not libs & set(abis):
        raise Fail(f"No matching ABI: package ships native libs for {sorted(libs)}, device supports {abis}.")

    obb_plan = []
    for local, remote, base in obbs:
        if not remote:
            if not package:
                raise Fail("Bundle contains OBB data but the package name could not be determined.")
            remote = f"/sdcard/Android/obb/{package}/{base}"
        obb_plan.append((local, remote))
    return apks, obb_plan, package, notes


# ---------------------------------------------------------------- install

def install(adb, serial, apks, installer):
    cmd = [adb, "-s", serial, "install" if len(apks) == 1 else "install-multiple", "-r"]
    if installer:
        cmd += ["-i", installer]
    res = run(cmd + apks)
    text = (res.stdout + res.stderr).strip()
    if res.returncode != 0 or "Success" not in text:
        hint = next((h for code, h in FAILURE_HINTS.items() if code in text), None)
        raise Fail(f"Install failed:\n{text}" + (f"\nHint: {hint}" if hint else ""))


def push_obbs(adb, serial, obbs):
    for local, remote in obbs:
        log(f"Pushing OBB -> {remote}")
        run([adb, "-s", serial, "shell", "mkdir", "-p", posixpath.dirname(remote)], timeout=30)
        res = run([adb, "-s", serial, "push", local, remote])
        if res.returncode != 0:
            raise Fail(f"APK installed but OBB push failed ({remote}):\n{(res.stdout + res.stderr).strip()}")


def verify(adb, serial, package, installer):
    out = run([adb, "-s", serial, "shell", "dumpsys", "package", package], timeout=60).stdout
    got = re.search(r"installerPackageName=(\S+)", out)
    version = re.search(r"versionName=(\S+)", out)
    got = got.group(1) if got else None
    version = version.group(1) if version else "?"
    if installer and got != installer:
        raise Fail(f"Installed {package} {version}, but installerPackageName is {got!r} (expected {installer}).")
    return version, got


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Install an APK/XAPK over ADB with Google Play installer metadata.")
    parser.add_argument("file", help="Path to .apk / .xapk / .apks / .apkm")
    parser.add_argument("device", nargs="?", help="Device IP, IP:port or serial (optional if one device is attached)")
    parser.add_argument("--installer", default=PLAY_STORE, help=f"Installer package (default {PLAY_STORE})")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be installed, do not install")
    args = parser.parse_args()

    workdir = tempfile.mkdtemp(prefix="adb_install_")
    try:
        adb = find_adb()
        serial = resolve_device(adb, args.device)
        props = device_props(adb, serial)
        abis, dpi = device_abis(props), device_dpi(props)
        model = " ".join(filter(None, [props.get("ro.product.brand"), props.get("ro.product.model")])) or "device"
        log(f"Device: {model} ({serial}), Android {props.get('ro.build.version.release', '?')}, "
            f"ABI {','.join(abis) or '?'}, {dpi or '?'}dpi")

        apks, obbs, package, notes = prepare(os.path.abspath(args.file), abis, dpi, workdir)
        log(f"Package: {package or 'unknown'} | " + "; ".join(notes))
        for a in apks:
            log(f"  + {os.path.basename(a)}")
        for _, remote in obbs:
            log(f"  + OBB {remote}")

        if args.dry_run:
            log("Dry run: nothing installed.")
            return 0

        log(f"Installing with installer={args.installer} ...")
        install(adb, serial, apks, args.installer)
        push_obbs(adb, serial, obbs)

        if package:
            version, got = verify(adb, serial, package, args.installer)
            log(f"OK: {package} {version} installed on {model}, installerPackageName={got}")
        else:
            log("OK: installed (package name unknown, installer metadata not verified).")
        return 0
    except Fail as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
