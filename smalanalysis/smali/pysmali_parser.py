from smali import SmaliReader, ClassVisitor, MethodVisitor
from typing import Optional, List, Dict, Any
import smalanalysis.smali.SmaliObject
import logging
import traceback
import sys 

def access_flags_to_list(flags):
    """Convert access flags integer to a list of string modifiers."""
    if not isinstance(flags, int):
        return []
    
    # Common access flags in smali
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
    """A visitor class that builds a SmaliClass object from pysmali's AST."""
    
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
        """Called when visiting a class definition."""
        #logging.debug("DEBUG - visit_class called for class: " + name)
        self.current_class = smalanalysis.smali.SmaliObject.SmaliClass(None)
        self.current_class.setName(f"L{name};")  # Add L and ; for consistency
        self.current_class.addModifiersFromList(access_flags_to_list(access_flags))

    def visit_inner_class(self, name: str, access_flags: List[str], outer_name: Optional[str], inner_name: Optional[str]) -> None:
        """
        Called when the parser encounters:
        .inner class public static final Lcom/package/MyClass$1; 
        """
        pass
            
    
    def visit_super(self, name: str) -> None:
        """Called when visiting the superclass definition."""
        #logging.debug("DEBUG - visit_super called for superclass: " + name)
        if self.current_class:
            self.current_class.setSuper(f"L{name};")  # Add L and ; for consistency
    
    def visit_source(self, name: str) -> None:
        """Called when visiting the source file definition."""
        #logging.debug("DEBUG - visit_source called for source: " + name)
        if self.current_class:
            self.current_class.setSource(name)
    
    def visit_implements(self, name: str) -> None:
        """Called when visiting an implemented interface."""
        #logging.debug("DEBUG - visit_implements called for interface: " + name)
        if self.current_class:
            self.current_class.addImplementedInterface(f"L{name};")
    
    def visit_annotation(self, name: str, access_flags: List[str]) -> None:
        """Called when visiting an annotation."""
        #logging.debug("DEBUG - visit_annotation called for annotation: " + str(name))
        if not self.current_class:
            return
            
        # Create a new annotation
        self.current_annotation = smalanalysis.smali.SmaliObject.SmaliAnnotation(
            f"L{name};",  # Add L and ; for consistency
            access_flags,
            self.current_class
        )
    
    def visit_annotation_end(self) -> None:
        """Called when finishing visiting an annotation."""
        #logging.debug("DEBUG - visit_annotation_end called")
        if self.current_annotation and self.current_class:
            self.current_class.addAnnotation(self.current_annotation)
            self.current_annotation = None
    
    def visit_field(self, name: str, access_flags: List[str], field_type: str, value: Any) -> None:
        """Called when visiting a field definition."""
        #logging.debug("DEBUG - visit_field called for field: " + name)
        if not self.current_class:
            return
            
        # Convert type to internal format
        if field_type.startswith('L') and field_type.endswith(';'):
            # Already in internal format
            internal_type = field_type
        else:
            # Convert primitive type to internal format
            type_map = {
                'void': 'V', 'boolean': 'Z', 'byte': 'B', 'short': 'S',
                'char': 'C', 'int': 'I', 'long': 'J', 'float': 'F', 'double': 'D'
            }
            internal_type = type_map.get(field_type, f"L{field_type};")
        
        # Create and add the field
        field = smalanalysis.smali.SmaliObject.SmaliField(
            name=name,
            type=internal_type,
            modifiers=access_flags,
            init=repr(value) if value is not None else None,
            clazz=self.current_class
        )
        self.current_class.addField(field)
        self.current_field = field
    
    def visit_method(self, name: str, access_flags: List[str], parameters: List[str], return_type: str) -> MethodVisitor:
        """Called when visiting a method definition."""
        #logging.debug("DEBUG - visit_method called for method: " + name)
        if not self.current_class:
            return None
            
        # Ensure parameters is always a list
        if not isinstance(parameters, (list, tuple)):
            parameters = []
        
        # Convert parameter types to internal format
        internal_params = []
        for param in parameters:
            if not param:  # Skip empty parameters
                continue
            if param.startswith('L') and param.endswith(';'):
                internal_params.append(param)
            else:
                # Handle primitive types and arrays
                type_map = {
                    'void': 'V', 'boolean': 'Z', 'byte': 'B', 'short': 'S',
                    'char': 'C', 'int': 'I', 'long': 'J', 'float': 'F', 'double': 'D'
                }
                internal_params.append(type_map.get(param, f"L{param};"))
        
        # Convert return type to internal format
        if return_type in ['V', 'Z', 'B', 'S', 'C', 'I', 'J', 'F', 'D']:
            internal_return = return_type
        elif return_type.startswith('['):  # Array type
            internal_return = return_type
        else:
            internal_return = f"L{return_type};"
        
        # Create the method
        method = smalanalysis.smali.SmaliObject.SmaliMethod(
            name=name,
            params=internal_params,
            ret=internal_return,
            modifiers=access_flags,
            clazz=self.current_class
        )
        
        self.current_class.addMethod(method)
        self.current_method = method
        self.method_lines[method.getSignature()] = []
        
        # Return a method visitor to handle the method body
        return self.MethodBodyCollector(self)
    
    def get_parsed_class(self) -> 'smalanalysis.smali.SmaliObject.SmaliClass':
        """Returns the parsed SmaliClass object."""
        #logging.debug("DEBUG - get_parsed_class called, returning: " + str(self.current_class))
        return self.current_class
    
    class MethodBodyCollector(MethodVisitor):
        """Collects method body instructions."""
        
        def __init__(self, parent_visitor):
            super().__init__()
            #logging.debug("DEBUG - MethodBodyCollector initialized")
            self.parent = parent_visitor
            self.current_method = parent_visitor.current_method
            self.signature = self.current_method.getSignature()
        
        def _record(self, opcode: str, full_instruction: str):
            """Helper to save the instruction to all tracking lists."""
            if self.signature in self.parent.method_lines:
                self.parent.method_lines[self.signature].append(opcode)
                if self.current_method:
                    self.current_method.addLine(full_instruction)

        def visit_instruction(self, opcode: str, *args, **kwargs) -> None:
            """Handles basic instructions (e.g., move, return, add-int)."""
            args_str = " ".join([str(a) for a in args if a is not None])
            self._record(opcode, f"{opcode} {args_str}".strip())

        def visit_subannotation(self, name: str, access_flags: List[str], *args, **kwargs) -> None:
            """Called when visiting a subannotation."""
            #logging.debug("DEBUG - visit_subannotation called for subannotation: " + str(name))
            if not self.current_class:
                return

        def visit_invoke(self, inv_type: str, args: list, owner: str, method: str):
                """Standard handler for invoke instructions in most pysmali versions."""
                # Ensure class_name has proper Smali formatting if not already present
                if not owner.startswith('L'):
                    owner = f"L{owner};"
                
                target = f"{owner}->{method}"
                self._record("invoke-"+str(inv_type), f"invoke-{inv_type} "+'{'+f" {', '.join(args)} "+'}'+f", {target}")

        def visit_method_instruction(self, *args, **kwargs):
            """Redirect this to visit_invoke to ensure coverage."""
            self.visit_invoke(*args, **kwargs)

        def visit_field_instruction(self, opcode: str, register: str, object_reg: Optional[str], 
                                    class_name: str, field_name: str, field_type: str) -> None:
            """Specifically captures 'sget', 'sput', 'iget', 'iput' instructions."""
            # Static fields use one register, Instance fields use two
            regs = f"{register}, {object_reg}" if object_reg else register
            target = f"{class_name};->{field_name}:{field_type}"
            self._record(opcode, f"{opcode} {regs}, {target}")

        def visit_type_instruction(self, opcode: str, register: str, type_name: str) -> None:
            """Captures 'check-cast', 'new-instance', etc."""
            self._record(opcode, f"{opcode} {register}, L{type_name};")

def parse_smali(content: str, name: str) -> 'smalanalysis.smali.SmaliObject.SmaliClass':
    """
    Parse smali code using pysmali and return a SmaliClass object.
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
