import argparse
import os
import re
import subprocess
import sys
import urllib.request
import zipfile

def find_adb():
    # Check PATH first
    try:
        res = subprocess.run(["adb", "version"], capture_output=True, text=True)
        if res.returncode == 0:
            return "adb"
    except Exception:
        pass

    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        os.path.expandvars(r"%ANDROID_HOME%\platform-tools\adb.exe"),
        os.path.expandvars(r"%ANDROID_SDK_ROOT%\platform-tools\adb.exe"),
        r"C:\Android\Sdk\platform-tools\adb.exe",
        r"C:\platform-tools\adb.exe",
        os.path.expandvars(r"%USERPROFILE%\platform-tools\adb.exe"),
        os.path.expandvars(r"%USERPROFILE%\Downloads\platform-tools\adb.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None

def run_adb(adb_path, args, device=None):
    cmd = [adb_path]
    if device:
        cmd.extend(["-s", device])
    cmd.extend(args)
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res

def list_devices(adb_path):
    res = run_adb(adb_path, ["devices", "-l"])
    devices = []
    for line in res.stdout.strip().splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "state": parts[1], "info": " ".join(parts[2:])})
    return devices

def get_device_info(adb_path, device=None):
    props = {}
    keys = [
        "ro.product.model",
        "ro.product.brand",
        "ro.product.manufacturer",
        "ro.product.marketname",
        "ro.product.cpu.abi",
        "ro.product.cpu.abilist",
        "ro.product.cpu.abilist64",
        "ro.build.version.release",
        "ro.build.version.sdk"
    ]
    cmd = "; ".join([f"getprop {k}" for k in keys])
    res = run_adb(adb_path, ["shell", cmd], device=device)
    lines = [l.strip() for l in res.stdout.strip().splitlines() if l.strip()]
    for i, k in enumerate(keys):
        if i < len(lines):
            props[k] = lines[i]
    return props

def inspect_apk(path):
    info = {"is_valid": False, "is_xapk": False, "apks": [], "abis": set()}
    if not os.path.exists(path):
        return info

    try:
        with zipfile.ZipFile(path, "r") as z:
            names = z.namelist()
            info["is_valid"] = True
            apk_in_zip = [n for n in names if n.endswith(".apk")]
            if apk_in_zip:
                info["is_xapk"] = True
                info["apks"] = apk_in_zip
            else:
                info["apks"] = [os.path.basename(path)]

            for n in names:
                if n.startswith("lib/"):
                    parts = n.split("/")
                    if len(parts) > 1:
                        info["abis"].add(parts[1])
    except Exception as e:
        info["error"] = str(e)

    return info

def install_app(adb_path, apk_paths, device=None, installer="com.android.vending"):
    if not isinstance(apk_paths, list):
        apk_paths = [apk_paths]

    if len(apk_paths) == 1:
        args = ["install", "-r"]
        if installer:
            args.extend(["-i", installer])
        args.append(apk_paths[0])
    else:
        args = ["install-multiple", "-r"]
        if installer:
            args.extend(["-i", installer])
        args.extend(apk_paths)

    return run_adb(adb_path, args, device=device)

def main():
    parser = argparse.ArgumentParser(description="ADB APK & Device Management Helper")
    parser.add_argument("--device", "-s", help="Target device serial or IP:port")
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("devices", help="List connected devices")
    subparsers.add_parser("info", help="Get device specs and ABI compatibility")

    install_p = subparsers.add_parser("install", help="Install APK or XAPK")
    install_p.add_argument("file", help="Path to APK or XAPK file")
    install_p.add_argument("--installer", default="com.android.vending", help="Installer package name")

    inspect_p = subparsers.add_parser("inspect", help="Inspect APK/XAPK ABIs and structure")
    inspect_p.add_argument("file", help="Path to APK or XAPK")

    args = parser.parse_args()

    adb_path = find_adb()
    if not adb_path:
        print("ERROR: adb executable not found. Please install Android SDK platform-tools.")
        sys.exit(1)

    if args.action == "devices":
        devs = list_devices(adb_path)
        print(f"ADB: {adb_path}")
        print(f"Connected devices ({len(devs)}):")
        for d in devs:
            print(f" - {d['serial']} [{d['state']}] {d['info']}")

    elif args.action == "info":
        info = get_device_info(adb_path, args.device)
        print("Device Information:")
        for k, v in info.items():
            print(f"  {k}: {v}")

    elif args.action == "inspect":
        info = inspect_apk(args.file)
        print(f"File: {args.file}")
        print(f"Valid archive: {info.get('is_valid')}")
        print(f"Is bundle/XAPK: {info.get('is_xapk')}")
        print(f"Contained APKs: {info.get('apks')}")
        print(f"Native ABIs: {list(info.get('abis', []))}")

    elif args.action == "install":
        target = args.file
        inspect_res = inspect_apk(target)
        if inspect_res.get("is_xapk"):
            extract_dir = target + "_extracted"
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(target, "r") as z:
                z.extractall(extract_dir)
            apks = [os.path.join(extract_dir, f) for f in os.listdir(extract_dir) if f.endswith(".apk")]
            print(f"Extracted {len(apks)} APKs from bundle. Installing...")
            res = install_app(adb_path, apks, device=args.device, installer=args.installer)
        else:
            print(f"Installing single APK {target}...")
            res = install_app(adb_path, [target], device=args.device, installer=args.installer)

        print(res.stdout)
        if res.stderr:
            print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)

if __name__ == "__main__":
    main()

