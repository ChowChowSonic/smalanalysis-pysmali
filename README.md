# SmalAnalysis

![license:MIT](https://img.shields.io/github/license/v-m/smalanalysis.svg)
![](https://img.shields.io/github/languages/top/v-m/smalanalysis.svg)

**Android Bytecode Analysis Tools**

This repo contains some tools I've built to work with APK and smali files. Mainly, it contains a toolkit for parsing smali output and mapping an APK internal with Python objects.
Best coding practices are not enforced as it is research code.
This code is not highly optimized. It is mainly intended to get a quick insight on whats going on on an APK. 

ℹ️ The tools in this repo work good with **unobfuscated APKs**.
Due to the simplicity of the parser, it can hardly deal with
complex strigs found in latest obfuscations techniques.


Some incoherencies may exists in this `README` and subsequent documentation as some part are took back from old e-mail exchanges and so on. Do not hesitate to report any bug/incoherency.

## Requirements

Originally Tested on MacOS. Should run well on UNIX/Linux systems.
More recently tested on Windows, can verify it works there (so long as you have some way of disassembling the app into smali code).

You will need:

- a working **python3** environement;
- a working version of the `apktool` tool in your system `PATH`.

## Installation

In order ot make this tool work, you will require a working installation of **Python 3.6**.
Moreover, the following tools should be installed and present in the system `PATH` in order to work:

- Android `apktool` command

Then, to proceed with the installation using pip:

```
pip install git+https://github.com/v-m/smalanalysis.git
```

## Disassembling

The `sa-disassemble` command is a short hand script to invoke the `apktool` tool offered by @iBotPeaches. To sum up, it simply:

- Extract the dexes classes from `apk` file using the `apktool` tool;
- Produce a ZIP archive containing all the smali files (just zip the smali folder).

⚠️ This archive is the expected input format for the scripts present in this repo (as it mainly work on smali).

[Learn more in the wiki page.](../../wiki/Disassembling)

## Getting a package name (ID)

A shorthand function is available to get the package name/id.
It simply query the `aapt` tool and parse the output.

```python
>>> from smalanalysis.tools.commands import queryAaptForPackageName
>>> queryAaptForPackageName("/Users/vince/base.apk")
b'com.android.packagename'
```

## Analyzing APKs

This framework proposes a really simple object representation of a smali file.
After disassembling an APK, the structure of the APK is represented based on an internal representation.

```python
>>> from smalanalysis.smali.SmaliProject import SmaliProject
>>> proj = SmaliProject()
>>> proj.parseProject('/Users/vince/base.apk.smali')
```

At this stage `proj` contains a representation of the project (ie a `SmaliProject` class).

[Learn more in the wiki page.](../../wiki/Analyzing-APKs)

## Diffing APKs

A large part of this project proposes a diffing tool which allows to list a set of differences between
two APKs. Here is how to run the differences computation between two versions:

- Disassemble both APKs
- Load two `SmaliProject` as decribed previously;
- Invoke the `differences()` methods to get a list of changes.

[Learn more in the wiki page.](../../wiki/Analyzing-APKs)

## Available Tools

This toolkit provides several command-line utilities for analyzing and comparing Android APK files:

### sa-disassemble
Disassembles APK files using apktool and packages the smali output into ZIP archives.

**Usage:**
```bash
sa-disassemble <apk_file>
```

**Features:**
- Uses apktool to extract and convert APK to smali format
- Creates a ZIP archive containing all smali files
- Automatically cleans up temporary files

**Example:**
```bash
sa-disassemble app.apk
# Creates: app.smali.zip in the same directory
```

### sa-metrics
Computes detailed evolution metrics between two versions of an app.

**Usage:**
`sa-metrics <old_apk.smali> <new_apk.smali> <package_name> [options]`

**Options:**
- `--verbose, -v`: Show detailed metrics output
- `--onlyapppackage, -P`: Include only classes in the specified app package
- `--fulllinesofcode, -f`: Show full lines instead of opcodes for differences
- `--aggregateoperators, -a`: Aggregate operators by their first keyword
- `--include-unpackaged, -U`: Include classes which are not in a package
- `--exclude-lists, -e`: Files containing excluded class lists
- `--include-lists, -i`: Files containing included class lists
- `--no-innerclasses-split, -I`: Do not split metrics for inner/outer classes
- `--use-pysmali`: Use the pysmali parser (faster and more reliable)

**Output:**
- Class and method counts for both versions
- Added/changed/deleted classes and methods
- Field changes statistics
- Added and removed lines of code

### sa-list
Lists all changed functions between two versions of an app.

**Usage:**
`sa-list <old_apk.smali> <new_apk.smali> <package_name> [options]`

**Options:**
Same filtering options as `sa-metrics`

**Output:**
- Simple list of function signatures that have changed between versions

### sa-extract
Extracts the actual smali code for all changed functions between two versions of an app.

**Features:**
- Compares two APK versions and identifies changed functions
- Creates an output directory with `new/` and `old/` subdirectories
- Organizes functions by their Java package structure
- Writes individual `.smali` files for each changed function

**Usage:**
`sa-extract <old_apk.smali> <new_apk.smali> <output_directory> [options]`

**Example:**
```bash
sa-extract older/app.smali latest/app.smali extracted_changes/
```

This will create:
```
extracted_changes/
├── new/
│   └── com/example/app/
│       └── ClassName/
│           └── methodName.smali
└── old/
    └── com/example/app/
        └── ClassName/
            └── methodName.smali
```

**Options:**
- `--verbose, -v`: Show detailed output
- `--fulllinesofcode, -f`: Show full lines instead of opcodes for differences
- `--aggregateoperators, -a`: Aggregate operators by their first keyword
- `--include-unpackaged, -U`: Include classes which are not in a package
- `--exclude-lists, -e`: Files containing excluded class lists
- `--include-lists, -i`: Files containing included class lists
- `--no-innerclasses-split, -I`: Do not split metrics for inner/outer classes
- `--no-pysmali`: Use legacy parser instead of pysmali
- `--filter-classes, -F`: File containing list of classes to filter for (one class per line)

**Class Filtering:**
The `--filter-classes` option allows you to specify a file containing class names to focus the analysis on specific classes only. The file should contain one class name per line. Classes can be specified in various formats:

```
# Example filter_classes.txt
com/example/app/MainActivity
Lcom/example/app/Helper;
com.example.app.Utils
Lcom/example/app/DataModel;
```

**Example with filtering:**
```bash
sa-extract older/app.smali latest/app.smali extracted_changes/ --filter-classes important_classes.txt
```

Each extracted `.smali` file contains:
- Method signature and metadata comments
- The complete smali code for that function version
- Version information (old/new)

### sa-smaldiff
Shows detailed line-by-line differences between changed functions with color highlighting.

**Features:**
- Displays unified diff format with color coding
- Shows added, removed, and changed lines
- Handles added/removed methods in addition to modified ones
- Color-coded output for better readability

**Usage:**
`sa-smaldiff <old_apk.smali> <new_apk.smali> <package_name> [options]`

**Color Legend:**
- **Blue**: Changed methods
- **Green**: Added lines/methods
- **Red**: Removed lines/methods
- **Cyan**: Headers and separators
- **Yellow**: Diff line numbers

**Options:**
Same filtering options as `sa-metrics`

### sa-invokediff
Analyzes differences in function invocations between changed methods.

**Features:**
- Extracts and compares function calls made by changed methods
- Shows which functions are invoked in old vs new versions
- Converts smali signatures to readable Java format
- Helps identify changes in method behavior and dependencies

**Usage:**
`sa-invokediff <old_apk.smali> <new_apk.smali> <package_name> [options]`

**Output Format:**
```
CHANGED: com.example.App.method()
OLD com.example.App.method(): [com.example.Helper.process(), java.util.List.add()]
NEW com.example.App.method(): [com.example.Helper.process(), com.example.Logger.log(), java.util.List.add()]
```

**Options:**
Same filtering options as `sa-metrics`

## Common Options

Most tools support these standard options:

**Filtering Options:**
- `--onlyapppackage, -P`: Limit analysis to specific app package
- `--include-unpackaged, -U`: Include classes without packages
- `--exclude-lists, -e`: Specify files with class exclusion lists
- `--include-lists, -i`: Specify files with class inclusion lists

**Parser Options:**
- `--no-pysmali`: Use legacy parser instead of pysmali
- `--use-pysmali`: Use pysmali parser (sa-metrics only)

**Output Options:**
- `--verbose, -v`: Show detailed output
- `--fulllinesofcode, -f`: Show full lines instead of opcodes
- `--aggregateoperators, -a`: Aggregate operators by keyword
- `--no-innerclasses-split, -I`: Don't separate inner/outer class metrics