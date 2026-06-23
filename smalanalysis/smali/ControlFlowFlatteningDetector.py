"""
Control Flow Flattening (CFF) detection using Androguard.

Control flow flattening replaces a method's original control-flow graph
with a state-machine pattern: a central dispatcher block reads a state
variable and branches to the appropriate case block; each case block
does work, updates the state, and jumps back to the dispatcher.

Three weighted heuristics are combined into a [0, 1] confidence score:

  1. Switch dispatch (50 %) -- presence of ``packed-switch`` / ``sparse-switch``
     with many child basic blocks.
  2. Back-edge topology (30 %) -- proportion of blocks that branch back to
     the dispatcher.
  3. Dispatcher register (20 %) -- proportion of non-dispatcher blocks that
     write to the register used by the switch instruction.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class CFFMethodResult:
    """Per-method CFF detection result."""
    class_name: str
    method_name: str
    method_descriptor: str
    confidence: float = 0.0
    block_count: int = 0
    switch_count: int = 0
    max_case_count: int = 0
    dispatcher_register: str = ""

    @property
    def signature(self) -> str:
        return f"{self.class_name}->{self.method_name}{self.method_descriptor}"

    @property
    def display_name(self) -> str:
        cls = self.class_name.replace("/", ".").lstrip("L").rstrip(";")
        return f"{cls}.{self.method_name}"


@dataclass
class CFFAnalysisResult:
    """Aggregated CFF detection results for an APK."""
    apk_path: str
    methods: List[CFFMethodResult] = field(default_factory=list)
    project_score: float = 0.0

    def by_class(self) -> dict:
        grouped = {}
        for m in self.methods:
            grouped.setdefault(m.class_name, []).append(m)
        return grouped

    def class_max_confidence(self, class_name: str) -> float:
        return max(
            (m.confidence for m in self.methods if m.class_name == class_name),
            default=0.0,
        )

    def method_confidence(self, signature: str) -> float:
        for m in self.methods:
            if m.signature == signature:
                return m.confidence
        return 0.0


WEIGHT_DISPATCH = 0.50
WEIGHT_TOPOLOGY = 0.30
WEIGHT_REGISTER = 0.20


def analyze_apk(dex_list, analysis) -> CFFAnalysisResult:
    """
    Analyze DEX objects for control flow flattening using Androguard.

    Args:
        dex_list: A list of androguard DEX objects.
        analysis: An androguard Analysis object.

    Returns:
        A CFFAnalysisResult with per-method scores.
    """
    result = CFFAnalysisResult(apk_path="")

    high_confidence_count = 0
    total_methods_with_code = 0

    for dex in dex_list:
        for method in dex.get_encoded_methods():
            code = method.get_code()
            if code is None:
                continue

            total_methods_with_code += 1
            ma = analysis.get_method_analysis(method)
            if ma is None:
                continue

            triple = method.get_triple()
            cff_result = _analyze_method(triple, method, ma)
            if cff_result is None:
                continue

            result.methods.append(cff_result)
            if cff_result.confidence > 0.5:
                high_confidence_count += 1

    result.project_score = (
        high_confidence_count / total_methods_with_code
        if total_methods_with_code > 0
        else 0.0
    )
    return result


def _analyze_method(
    triple: Tuple[str, str, str],
    method,
    method_analysis,
) -> Optional[CFFMethodResult]:
    """
    Detect CFF in a single method using Androguard's CFG.

    Returns a CFFMethodResult or None if the method has
    too few basic blocks to be considered.
    """
    class_name, method_name, descriptor = triple
    bbs = list(method_analysis.get_basic_blocks())
    total_blocks = len(bbs)

    if total_blocks < 4:
        return None

    # 1. Identify dispatcher blocks (those containing switch instructions)
    dispatcher_blocks = []
    for bb in bbs:
        for insn in bb.get_instructions():
            if insn.get_name() in ("packed-switch", "sparse-switch"):
                dispatcher_blocks.append(bb)
                break

    if not dispatcher_blocks:
        return None

    main_dispatcher = max(dispatcher_blocks, key=lambda bb: len(bb.childs))
    case_count = len(main_dispatcher.childs)
    num_switches = len(dispatcher_blocks)

    # Heuristic 1: Switch dispatch score (50 %)
    case_score = min(case_count / 10.0, 1.0)
    switch_score_val = min(num_switches / 3.0, 1.0)
    dispatch_score = case_score * 0.6 + switch_score_val * 0.4

    # Heuristic 2: Back-edge topology score (30 %)
    back_edges = sum(
        1 for bb in bbs if bb is not main_dispatcher and main_dispatcher in bb.childs
    )
    topology_score = back_edges / (total_blocks - 1) if total_blocks > 1 else 0.0

    # Heuristic 3: Dispatcher register score (20 %)
    dispatcher_reg = None
    for insn in main_dispatcher.get_instructions():
        if insn.get_name() in ("packed-switch", "sparse-switch"):
            dispatcher_reg = getattr(insn, "AA", None)
            break

    if dispatcher_reg is not None:
        blocks_writing_reg = 0
        for bb in bbs:
            if bb is main_dispatcher:
                continue
            for insn in bb.get_instructions():
                reg = getattr(insn, "AA", None)
                if reg is not None and reg == dispatcher_reg:
                    blocks_writing_reg += 1
                    break
        reg_score = blocks_writing_reg / (total_blocks - 1) if total_blocks > 1 else 0.0
    else:
        reg_score = 0.0

    confidence = (
        dispatch_score * WEIGHT_DISPATCH
        + topology_score * WEIGHT_TOPOLOGY
        + reg_score * WEIGHT_REGISTER
    )

    if confidence < 0.05:
        return None

    return CFFMethodResult(
        class_name=class_name,
        method_name=method_name,
        method_descriptor=descriptor,
        confidence=round(confidence, 4),
        block_count=total_blocks,
        switch_count=num_switches,
        max_case_count=case_count,
        dispatcher_register=f"v{dispatcher_reg}" if dispatcher_reg is not None else "",
    )
