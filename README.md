# SmalAnalysis

![license:MIT](https://img.shields.io/github/license/v-m/smalanalysis.svg)
![](https://img.shields.io/github/languages/top/v-m/smalanalysis.svg)

**Android Bytecode Analysis Tools (Androguard-based)**

This repo contains tools for parsing and comparing APK files using Androguard.
No apktool or external disassembly required — Androguard reads DEX bytecode
directly.

## Requirements

- Python 3.6+
- `androguard` (automatically installed via pip)

## Installation

```
pip install .
```

## Usage

All tools accept APK files directly:

```bash
# Compare two APKs and list changed methods
sa-list old.apk new.apk com.example.app -v

# Compute evolution metrics
sa-metrics old.apk new.apk com.example.app

# Extract changed method bytecode
sa-extract old.apk new.apk output_dir/
```

## Available Tools

### sa-metrics
Computes evolution metrics between two APK versions.

**Usage:** `sa-metrics <apk1> <apk2> [package_name] [options]`

**Options:**
- `--verbose, -v`: Show detailed metrics output
- `--onlyapppackage, -P`: Filter to a specific package
- `--include-unpackaged, -U`: Include classes not in a package
- `--exclude-lists, -e`: Files containing excluded class lists
- `--include-lists, -i`: Files containing included class lists
- `--with-innerclasses-split, -I`: Split metrics for inner/outer classes

**Output:** CSV with class, method, and field change counts.

### sa-list
Lists all changed method signatures between two APK versions.

**Usage:** `sa-list <apk1> <apk2> <package_name> [options]`

### sa-extract
Extracts smali code for all changed methods between two APK versions.

**Usage:** `sa-extract <apk1> <apk2> <output_dir> [options]`

Creates `output_dir/old/` and `output_dir/new/` with per-method `.smali` files.

**Options:**
- `--filter-classes, -F`: File with `class_name: function_name` patterns to filter
- `--filter-instructions-regex, -R`: Regex to filter instructions within methods
- `--skip-obfuscated, -s`: Skip classes that appear obfuscated

## Programmatic API

```python
from smalanalysis.smali import SmaliProject

# Parse an APK (single entry point)
project, cff_result = SmaliProject.from_apk("app.apk")
```
