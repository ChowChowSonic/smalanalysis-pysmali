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

## Diffing Metrics

The tool `sa-metrics` can be used to compute different evolution metrics between two versions of an app.
It works on output archived produced by the `sa-disassemble` tool.
Same inclusion/exclusion parameters can be passed to this function.
**Usage:**
`sa-metrics <old_apk.smali> <new_apk.smali> --use-pysmali`

[Learn more in the wiki page.](../../wiki/Diffing-Metrics)

## Listing changed functions
The tool `sa-list` can be used to list all the changed functions between two versions of an app.
It works on output archived produced by the `sa-disassemble` tool.
Same inclusion/exclusion parameters can be passed to this function.
**Usage:**
`sa-list <old_apk.smali> <new_apk.smali> --use-pysmali`