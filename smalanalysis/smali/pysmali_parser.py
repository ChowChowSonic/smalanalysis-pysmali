"""
pysmali-based parser bridge.

Wraps the external ``pysmali`` library (``SmaliReader``, ``ClassVisitor``,
``MethodVisitor``) to produce the project's native ``SmaliClass`` objects.

When pysmali is unavailable or fails, the codebase falls back to the
legacy regex-based parser in ``SmaliProject._legacy_parse_class``.
"""

from smali import SmaliReader, ClassVisitor, MethodVisitor
from typing import Optional, List, Dict, Any
import smalanalysis.smali.SmaliObject
import logging
import traceback
import sys


def access_flags_to_list(flags):
    """
    Convert an integer bitmask of access flags into a list of human-readable
    modifier strings (e.g. ``0x1`` → ``["public"]``).

    When *flags* is not an integer (e.g. already a list of strings), it is
    returned as-is — this supports both the pysmali (int bitmask) and legacy
    (list of strings) calling conventions.
    """
    if not isinstance(flags, int):
        return flags
    
    flag_map = {
        0x1: 'public',
        0x2: 'private',
        0x4: 'protected',
        0x8: 'static',
        0x10: 'final',
        0x20: 'synchronized',
        0x40: 'volatile',
        0x80: 'transient',
        0x100: 'native',
        0x200: 'interface',
        0x400: 'abstract',
        0x1000: 'synthetic',
        0x2000: 'annotation',
        0x4000: 'enum',
        0x8000: 'unused',
        0x10000: 'constructor',
        0x20000: 'declared_synchronized',
    }
    
    modifiers = []
    for flag_value, flag_name in flag_map.items():
        if flags & flag_value:
            modifiers.append(flag_name)
    
    return modifiers

class PysmaliClassVisitor(ClassVisitor):
    """
    Visitor that walks the pysmali AST and builds a ``SmaliClass`` object
    (from ``SmaliObject``) with all its methods, fields, and annotations
    populated.

    Usage::

        reader = SmaliReader(comments=True, validate=True, snippet=False)
        visitor = PysmaliClassVisitor()
        reader.visit(smali_content, visitor)
        cls = visitor.get_parsed_class()
    """

    def __init__(self):
        super().__init__()
        self.current_class: Optional[smalanalysis.smali.SmaliObject.SmaliClass] = None
        self.current_method: Optional[smalanalysis.smali.SmaliObject.SmaliMethod] = None
        self.current_field: Optional[smalanalysis.smali.SmaliObject.SmaliField] = None
        self.current_annotation: Optional[Any] = None
        self.method_lines: Dict[str, List[str]] = {}

    def visit(self, content: str, parser: Any = None) -> None:
        return super().visit(content, parser)

    def visit_class(self, name: str, access_flags: List[str]) -> None:
        """Called when the parser enters a ``.class`` declaration."""
        self.current_class = smalanalysis.smali.SmaliObject.SmaliClass(None)
        self.current_class.setName(f"L{name};")
        self.current_class.addModifiersFromList(access_flags_to_list(access_flags))

    def visit_inner_class(self, name: str, access_flags: List[str], outer_name: Optional[str], inner_name: Optional[str]) -> None:
        """
        Called when the parser encounters a ``.inner class`` directive.
        Currently a no-op; inner-class linkage is handled at the
        ``SmaliProject`` level.
        """
        pass

    def visit_super(self, name: str) -> None:
        """Called for the ``.super`` directive — sets the superclass name."""
        if self.current_class:
            self.current_class.setSuper(f"L{name};")

    def visit_source(self, name: str) -> None:
        """Called for the ``.source`` directive — stores the source file name."""
        if self.current_class:
            self.current_class.setSource(name)

    def visit_implements(self, name: str) -> None:
        """Called for each ``.implements`` directive — records an implemented interface."""
        if self.current_class:
            self.current_class.addImplementedInterface(f"L{name};")

    def visit_annotation(self, name: str, access_flags: List[str]) -> None:
        """Called when entering an ``.annotation`` block — creates a ``SmaliAnnotation``."""
        if not self.current_class:
            return
        self.current_annotation = smalanalysis.smali.SmaliObject.SmaliAnnotation(
            f"L{name};", access_flags, self.current_class
        )

    def visit_annotation_end(self) -> None:
        """Called when leaving an ``.annotation`` block — finalises and attaches the annotation."""
        if self.current_annotation and self.current_class:
            self.current_class.addAnnotation(self.current_annotation)
            self.current_annotation = None

    def visit_field(self, name: str, access_flags: List[str], field_type: str, value: Any) -> None:
        """Called for each ``.field`` declaration — creates and registers a ``SmaliField``."""
        if not self.current_class:
            return

        if field_type.startswith('L') and field_type.endswith(';'):
            internal_type = field_type
        else:
            type_map = {
                'void': 'V', 'boolean': 'Z', 'byte': 'B', 'short': 'S',
                'char': 'C', 'int': 'I', 'long': 'J', 'float': 'F', 'double': 'D'
            }
            internal_type = type_map.get(field_type, f"L{field_type};")

        field = smalanalysis.smali.SmaliObject.SmaliField(
            name=name, type=internal_type, modifiers=access_flags,
            init=repr(value) if value is not None else None, clazz=self.current_class
        )
        self.current_class.addField(field)
        self.current_field = field

    def visit_method(self, name: str, access_flags: List[str], parameters: List[str], return_type: str) -> MethodVisitor:
        """
        Called for each ``.method`` declaration.

        Creates a ``SmaliMethod``, attaches it to the current class, and returns
        a ``MethodBodyCollector`` that will receive the method's instruction lines.
        """
        if not self.current_class:
            return None

        if not isinstance(parameters, (list, tuple)):
            parameters = []

        internal_params = []
        for param in parameters:
            if not param:
                continue
            if param.startswith('L') and param.endswith(';'):
                internal_params.append(param)
            else:
                type_map = {
                    'void': 'V', 'boolean': 'Z', 'byte': 'B', 'short': 'S',
                    'char': 'C', 'int': 'I', 'long': 'J', 'float': 'F', 'double': 'D'
                }
                internal_params.append(type_map.get(param, f"L{param};"))

        if return_type in ['V', 'Z', 'B', 'S', 'C', 'I', 'J', 'F', 'D']:
            internal_return = return_type
        elif return_type.startswith('['):
            internal_return = return_type
        else:
            internal_return = f"L{return_type};"

        method = smalanalysis.smali.SmaliObject.SmaliMethod(
            name=name, params=internal_params, ret=internal_return,
            modifiers=access_flags, clazz=self.current_class
        )

        self.current_class.addMethod(method)
        self.current_method = method
        self.method_lines[method.getSignature()] = []

        return self.MethodBodyCollector(self)

    def get_parsed_class(self) -> 'smalanalysis.smali.SmaliObject.SmaliClass':
        """Return the fully built ``SmaliClass`` (or ``None`` if parsing failed)."""
        return self.current_class

    class MethodBodyCollector(MethodVisitor):
        """
        Receives individual method-body instructions and appends them
        as raw text lines to the parent ``SmaliMethod``.
        """

        def __init__(self, parent_visitor):
            super().__init__()
            self.parent = parent_visitor
            self.current_method = parent_visitor.current_method
            self.signature = self.current_method.getSignature()

        def _record(self, opcode: str, full_instruction: str):
            """Store an instruction line in both the per-method line list and the parent visitor's tracking dict."""
            if self.signature in self.parent.method_lines:
                self.parent.method_lines[self.signature].append(opcode)
                if self.current_method:
                    self.current_method.addLine(full_instruction)

        def visit_instruction(self, opcode: str, *args, **kwargs) -> None:
            """
            Handles basic instructions (``move``, ``return``, ``add-int``, etc.).
            Concatenates positional arguments into a single text line.
            """
            args_str = " ".join([str(a) for a in args if a is not None])
            self._record(opcode, f"{opcode} {args_str}".strip())

        def visit_subannotation(self, name: str, access_flags: List[str], *args, **kwargs) -> None:
            """Called when visiting a subannotation — currently a no-op."""

        def visit_invoke(self, inv_type: str, args: list, owner: str, method: str):
            """
            Handles ``invoke-*`` instructions.  Formats the output as::

                invoke-{type} {registers}, {owner}->{method}
            """
            if not owner.startswith('L'):
                owner = f"L{owner};"
            target = f"{owner}->{method}"
            self._record("invoke-"+str(inv_type),
                         f"invoke-{inv_type} " + '{' + f" {', '.join(args)} " + '}' + f", {target}")

        def visit_method_instruction(self, *args, **kwargs):
            """Alias for :meth:`visit_invoke` — ensures coverage across pysmali versions."""
            self.visit_invoke(*args, **kwargs)

        def visit_field_instruction(self, opcode: str, register: str, object_reg: Optional[str],
                                    class_name: str, field_name: str, field_type: str) -> None:
            """
            Handles field-access instructions (``iget``, ``iput``, ``sget``, ``sput``).
            Instance-field instructions include a second register; static-field
            instructions use only one.
            """
            regs = f"{register}, {object_reg}" if object_reg else register
            target = f"{class_name};->{field_name}:{field_type}"
            self._record(opcode, f"{opcode} {regs}, {target}")

        def visit_type_instruction(self, opcode: str, register: str, type_name: str) -> None:
            """Handles type-reference instructions (``check-cast``, ``new-instance``, etc.)."""
            self._record(opcode, f"{opcode} {register}, L{type_name};")

def parse_smali(content: str, name: str) -> 'smalanalysis.smali.SmaliObject.SmaliClass':
    """
    Parse raw smali source text using the pysmali library and return a
    ``SmaliClass`` object.

    Args:
        content: The full text of a ``.smali`` file.
        name: A human-readable file name used only in error messages.

    Returns:
        A populated ``SmaliClass`` with methods, fields, and annotations,
        or ``None`` if the content is empty or parsing raised any exception.

    .. note::
        A ``bare except Exception`` is intentional: pysmali can throw
        many different errors across versions, and a failed parse for one
        class should never crash the whole analysis.
    """
    try:
        #print(content)
        if not content or not content.strip():
            return None
        reader = SmaliReader(comments=True, validate=True, snippet=False)
        visitor = PysmaliClassVisitor()    
        #logging.debug("DEBUG - Starting to parse smali content")
        #logging.debug(content)
        reader.visit(content, visitor)
        #logging.debug("DEBUG - Finished parsing smali content")
        return visitor.get_parsed_class()
    except Exception as e:
        print(f"ERROR in parse_smali when reading file {name}: {str(e)}", file=sys.stderr)
        print(f"Error type: {type(e).__name__}", file=sys.stderr)
        traceback.print_exc()
        #logging.debug(f"Content length: {len(content)}")
        #logging.debug(f"Content preview: {content[:200]}")
        return None 
