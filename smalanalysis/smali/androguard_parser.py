"""
Androguard-based parser bridge.

Uses androguard to parse APK files directly (no apktool required) and
populate ``SmaliProject`` with native ``SmaliClass``, ``SmaliMethod``,
and ``SmaliField`` objects.
"""

import re
import sys
import logging
from typing import List, Optional

import smalanalysis.smali.SmaliObject
from smalanalysis.smali.SmaliProject import SmaliProject

log = logging.getLogger(__name__)

_CONST_STRING_RE = re.compile(
    r'^const-string(?:/jumbo)?\s+\w+\s*,\s*"(.*)"\s*$'
)
_INVOKE_SB_RE = re.compile(
    r'invoke-[\w-]+\s*\{.*\}\s*,\s*Ljava/lang/String(Builder|Buffer);->'
)
_NEW_SB_RE = re.compile(
    r'new-instance\s+\w+,\s*Ljava/lang/String(Builder|Buffer);'
)
_BYTEARRAY_STRING_RE = re.compile(
    r'invoke-[\w-]+\s*\{.*\}\s*,\s*Ljava/lang/String;-><init>\(.*\[B'
)


def access_flags_to_list(flags):
    if not isinstance(flags, int):
        return flags
    flag_map = {
        0x1: 'public', 0x2: 'private', 0x4: 'protected',
        0x8: 'static', 0x10: 'final', 0x20: 'synchronized',
        0x40: 'volatile', 0x80: 'transient', 0x100: 'native',
        0x200: 'interface', 0x400: 'abstract', 0x1000: 'synthetic',
        0x2000: 'annotation', 0x4000: 'enum', 0x8000: 'unused',
        0x10000: 'constructor', 0x20000: 'declared_synchronized',
    }
    return [name for val, name in flag_map.items() if flags & val]


def _parse_descriptor(descriptor: str):
    if not descriptor or descriptor[0] != '(':
        return [], descriptor or ''
    end_paren = descriptor.index(')')
    params_str = descriptor[1:end_paren]
    return_type = descriptor[end_paren + 1:]

    params: List[str] = []
    i = 0
    while i < len(params_str):
        c = params_str[i]
        if c == '[':
            start = i
            i += 1
            while i < len(params_str) and params_str[i] == '[':
                i += 1
            if i < len(params_str) and params_str[i] == 'L':
                i += 1
                while i < len(params_str) and params_str[i] != ';':
                    i += 1
                i += 1
            else:
                i += 1
            params.append(params_str[start:i])
        elif c == 'L':
            start = i
            i += 1
            while i < len(params_str) and params_str[i] != ';':
                i += 1
            i += 1
            params.append(params_str[start:i])
        else:
            params.append(c)
            i += 1
    return params, return_type


def _split_access_flags(flags_str: Optional[str]) -> Optional[List[str]]:
    if not flags_str or not flags_str.strip():
        return None
    return flags_str.strip().split()


def _create_smali_class(cls_def, project) -> Optional['smalanalysis.smali.SmaliObject.SmaliClass']:
    clazz = smalanalysis.smali.SmaliObject.SmaliClass(None)
    clazz.setName(cls_def.get_name())

    modifiers = _split_access_flags(cls_def.get_access_flags_string())
    clazz.addModifiersFromList(modifiers)

    super_name = cls_def.get_superclassname()
    if super_name:
        clazz.setSuper(super_name)

    try:
        source = cls_def.get_source()
        if source:
            clazz.setSource(source)
    except Exception:
        pass

    try:
        ifaces = cls_def.get_interfaces()
        if ifaces:
            for iface in ifaces:
                clazz.addImplementedInterface(iface)
    except Exception:
        pass

    try:
        anns = cls_def.get_annotations()
        if anns:
            for ann in anns:
                name = str(ann) if not isinstance(ann, str) else ann
                clazz.addAnnotation(
                    smalanalysis.smali.SmaliObject.SmaliWithLines(name, None, clazz)
                )
    except Exception:
        pass

    try:
        fields = cls_def.get_fields()
        if fields:
            for f in fields:
                smali_field = _create_smali_field(f, clazz)
                if smali_field:
                    clazz.addField(smali_field)
    except Exception:
        pass

    try:
        methods = cls_def.get_methods()
        if methods:
            for m in methods:
                smali_method = _create_smali_method(m, clazz)
                if smali_method:
                    clazz.addMethod(smali_method)
    except Exception:
        pass

    return clazz


def _create_smali_field(enc_field, parent_class) -> Optional['smalanalysis.smali.SmaliObject.SmaliField']:
    name = enc_field.get_name()
    descriptor = enc_field.get_descriptor()
    modifiers = _split_access_flags(enc_field.get_access_flags_string())

    init_repr = None
    try:
        raw = enc_field.get_value()
        if raw is not None:
            init_repr = repr(raw) if isinstance(raw, bytes) else raw
    except Exception:
        pass

    return smalanalysis.smali.SmaliObject.SmaliField(
        name=name, type=descriptor, modifiers=modifiers, init=init_repr, clazz=parent_class,
    )


def _create_smali_method(enc_method, parent_class) -> Optional['smalanalysis.smali.SmaliObject.SmaliMethod']:
    name = enc_method.get_name()
    descriptor = enc_method.get_descriptor()
    modifiers = _split_access_flags(enc_method.get_access_flags_string())
    params, ret = _parse_descriptor(descriptor)

    smali_method = smalanalysis.smali.SmaliObject.SmaliMethod(
        name=name, params=params, ret=ret, modifiers=modifiers, clazz=parent_class,
    )

    try:
        instructions = enc_method.get_instructions()
        if instructions:
            for instr in instructions:
                disasm_line = instr.disasm()
                if not disasm_line:
                    continue
                smali_method.addLine(disasm_line)

                m = _CONST_STRING_RE.match(disasm_line)
                if m:
                    parent_class.strings.append(m.group(1))

                if disasm_line.startswith(('invoke-', 'new-instance')):
                    if _INVOKE_SB_RE.search(disasm_line) or _NEW_SB_RE.search(disasm_line):
                        smali_method.uses_stringbuilder = True
                    if _BYTEARRAY_STRING_RE.search(disasm_line):
                        smali_method.uses_bytearray_string = True
    except Exception:
        pass

    return smali_method


def _should_include_class(
    name: str, package: Optional[str] = None, skips: Optional[set] = None,
    includes: Optional[set] = None, include_unpackaged: bool = False,
) -> bool:
    if package is not None:
        if package.replace('.', '/') not in name:
            return False
    if '/' not in name[1:-1]:
        return include_unpackaged
    if skips is not None or includes is not None:
        return SmaliProject.shouldAnalyzeThisClass(name[1:-1], skips, includes, default=True)
    return True


def _process_inner_classes(project):
    classes = {}
    inner_classes = []

    for name, clazz in project.classesdict.items():
        internal = name[1:-1] if name.startswith('L') and name.endswith(';') else name
        classes[internal] = clazz
        m2 = internal.split("$")
        if len(m2) > 1 and m2[0][-1] != '/':
            inner_classes.append((clazz, m2[0], m2[1:]))

    project._process_inner_classes(classes, inner_classes)


def parse_apk(
    dex_list, project, package: Optional[str] = None,
    skiplists: Optional[List[str]] = None, includelist: Optional[List[str]] = None,
    include_unpackaged: bool = False,
):
    skips = None
    includes = None
    if skiplists is not None:
        skips = set()
        for s in skiplists:
            skips |= SmaliProject.loadRulesListFromFile(s)
    if includelist is not None:
        includes = set()
        for s in includelist:
            includes |= SmaliProject.loadRulesListFromFile(s)

    failed = 0
    successful = 0

    for dex in dex_list:
        try:
            class_names = dex.get_classes_names()
        except Exception:
            continue

        for name in class_names:
            cls_def = dex.get_class(name)
            if cls_def is None:
                failed += 1
                continue
            if not _should_include_class(name, package, skips, includes, include_unpackaged):
                continue

            try:
                smali_class = _create_smali_class(cls_def, project)
                if smali_class is None:
                    failed += 1
                    continue
                smali_class.parent = project
                project.addClass(smali_class)
                successful += 1
            except Exception as e:
                log.warning("Failed to parse class %s: %s", name, e)
                failed += 1

    sys.stderr.write(
        f"Failed to parse {failed} classes, "
        f"{successful} successfully parsed via androguard\n"
    )

    _process_inner_classes(project)
