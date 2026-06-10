import subprocess
import re
import tempfile
import os
import shutil
import xml.etree.ElementTree as ET
import zipfile

PACKAGEMATCHER = re.compile(b'package: name=\'(.*?)\'')
dexfiles = re.compile('^classes[0-9]*.dex$')

# Common Android system/library package prefixes to ignore when inferring
ANDROID_NS = 'http://schemas.android.com/apk/res/android'


class MainActivityNotFoundError(Exception):
    pass


def _get_attrib(elem, name):
    val = elem.get(f'{{{ANDROID_NS}}}{name}')
    return val if val is not None else elem.get(name)


def _find_main_activity_package(tree, base_pkg):
    root = tree.getroot()
    application = root.find('application')
    if application is None:
        raise MainActivityNotFoundError(
            "No <application> tag found in AndroidManifest.xml"
        )

    for child in application:
        tag = child.tag.split('}', 1)[-1]
        if tag not in ('activity', 'activity-alias'):
            continue

        for intent_filter in child.findall('intent-filter'):
            has_main = False
            has_launcher = False

            for sub in intent_filter:
                sub_tag = sub.tag.split('}', 1)[-1]
                if sub_tag == 'action':
                    name = _get_attrib(sub, 'name')
                    if name == 'android.intent.action.MAIN':
                        has_main = True
                elif sub_tag == 'category':
                    name = _get_attrib(sub, 'name')
                    if name in (
                        'android.intent.category.LAUNCHER',
                        'android.intent.category.LEANBACK_LAUNCHER',
                    ):
                        has_launcher = True

            if has_main and has_launcher:
                activity_name = _get_attrib(child, 'name')
                if activity_name:
                    if activity_name.startswith('.'):
                        activity_name = base_pkg + activity_name
                    return activity_name.rsplit('.', 1)[0]

    raise MainActivityNotFoundError(
        "No activity with MAIN/LAUNCHER intent-filter "
        "found in AndroidManifest.xml"
    )


SYSTEM_PACKAGES = {
    'android', 'dalvik', 'java', 'javax', 'kotlin', 'kotlinx',
    'okhttp', 'okio', 'retrofit2', 'rx', 'rxjava',
}


def queryAaptForPackageName(apk_or_zip_path):
    """
    Extract the package name from an APK or smali ZIP file.
    
    For APK files: uses apktool to decode the manifest XML, then extracts
                   the ``package`` attribute from the ``<manifest>`` element.
                   Falls back to ``aapt dump badging`` if apktool fails.
    For smali ZIP files: infers the most common package prefix from the
                         directory structure of ``.smali`` files, skipping
                         known system/library directories.
    
    Args:
        apk_or_zip_path: Path to an APK file, a ``.zip``, or a ``.smali.zip``.
    
    Returns:
        The package name as a string (e.g. ``"com.example.app"``),
        or ``None`` if it could not be determined.
    """
    path_lower = apk_or_zip_path.lower()
    if path_lower.endswith('.apk'):
        return _get_package_from_apk(apk_or_zip_path)
    else:
        return _get_package_from_smali_zip(apk_or_zip_path)


def _get_package_from_apk(apk_path):
    """Try apktool first, then fall back to aapt."""
    # ---- Method 1: apktool ------------------------------------------------
    temp_dir = tempfile.mkdtemp(prefix='sa_pkg_')
    try:
        result = subprocess.run(
            ['apktool', 'd', '-s', '-f', '-o', temp_dir, apk_path],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            manifest_path = os.path.join(temp_dir, 'AndroidManifest.xml')
            if os.path.isfile(manifest_path):
                tree = ET.parse(manifest_path)
                pkg = tree.getroot().get('package')
                if pkg:
                    return _find_main_activity_package(tree, pkg)
    except (subprocess.TimeoutExpired, FileNotFoundError, ET.ParseError):
        pass
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # ---- Method 2 (fallback): aapt ----------------------------------------
    try:
        task = subprocess.Popen(
            "aapt dump badging \"%s\"" % apk_path,
            shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        it = PACKAGEMATCHER.findall(task.stdout.read())
        if it:
            return it[0].decode('utf-8')
    except Exception:
        pass

    return None


def _get_package_from_smali_zip(zip_path):
    """Infer app package name from a smali ZIP's directory layout.

    Scans ``.smali`` file paths, counts the most common top-two-level
    directory prefix, and returns it as a dot-separated package name.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            entries = zf.namelist()
    except Exception:
        return None

    # ---- Quick check: decoded AndroidManifest.xml bundled in the ZIP ----
    if 'AndroidManifest.xml' in entries:
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                raw = zf.read('AndroidManifest.xml')
            tree = ET.ElementTree(ET.fromstring(raw))
            pkg = tree.getroot().get('package')
            if pkg:
                return _find_main_activity_package(tree, pkg)
        except ET.ParseError:
            pass
        except MainActivityNotFoundError:
            raise

        # ---- Fallback: regex for binary AXML (package name only) ----
        try:
            m = re.search(rb'package="([^"]+)"', raw)
            if m:
                return m.group(1).decode('utf-8')
        except Exception:
            pass

    # ---- Infer from file paths -------------------------------------------
    counter = {}
    for name in entries:
        if not name.endswith('.smali') or '/' not in name:
            continue
        parts = name.split('/')
        top = parts[0]
        # Skip known system / library packages
        if top in SYSTEM_PACKAGES or top.startswith('com/google') or \
           top.startswith('com/android') or top.startswith('org/apache'):
            continue
        # Need at least pkg/path/Class.smali (3+ parts)
        if len(parts) >= 3:
            # Use at most 3 directory levels as the package key
            levels = min(len(parts) - 1, 3)
            candidate = '.'.join(parts[:levels])
            counter[candidate] = counter.get(candidate, 0) + 1

    if not counter:
        return None

    # Return the package path that covers the most smali files
    best = max(counter, key=counter.get)
    return best