"""
Project-level parsing, class matching, and diffing for collections of smali
files.

``SmaliProject`` represents a set of smali classes parsed from an APK via
androguard.  Two projects can be compared to produce a ``diff`` result
that drives the metrics computation.
"""

import os

import smalanalysis.smali.SmaliObject
from smalanalysis.smali import ComparisonIgnores
from smalanalysis.smali.ChangesTypes import REVISED_METHOD, SAME_NAME

# Cache the most recent ``AnalyzeAPK`` result so that repeated calls for
# the same APK path (common when old / new are compared side-by-side) do
# not re-parse the same file.  Keyed by ``os.path.realpath()``.
_init_cache: dict = {}


def _init_androguard(apk_path):
    """Import androguard and return ``(dex_list, dx_analysis)``."""
    import logging

    resolved = os.path.realpath(apk_path)
    cached = _init_cache.get(resolved)
    if cached is not None:
        return cached

    os.environ.setdefault("LOGURU_LEVEL", "CRITICAL")

    logging.getLogger('androguard').setLevel(logging.CRITICAL)
    logging.getLogger('androwarn').setLevel(logging.CRITICAL)

    from androguard.misc import AnalyzeAPK
    _, dex_list, dx = AnalyzeAPK(apk_path)
    result = (dex_list, dx)
    _init_cache[resolved] = result
    return result


class SmaliProject(object):
    """
    A collection of smali classes parsed from an APK via androguard.

    Supports parsing, class matching (linking old ↔ new versions), and
    ``differences()`` to produce structured diff data for metric computation.
    """

    def __init__(self):
        self.classes = []
        self.classesdict = {}

    def addClass(self, c):
        self.classes.append(c)
        self.classesdict[c.name] = c

    def getObfuscationScore(self):
        total = len(list(self.classes))
        if total == 0:
            return 1.0

        single_letter_pkg = no_pkg = short_name = numeric_name = source_missing = malformed_name = 0

        for c in self.classes:
            if c.name is None:
                continue
            if len(c.name) >= 2 and c.name[0:2] == 'L;':
                malformed_name += 1
                continue

            internal = c.name[1:-1]
            if '/' in internal:
                pkg_path = internal[:internal.rfind('/')]
                simple_name = internal[internal.rfind('/') + 1:]
            else:
                pkg_path = ''
                simple_name = internal

            if '$' in simple_name:
                simple_name = simple_name.split('$')[-1]

            if not pkg_path:
                no_pkg += 1
            if pkg_path and all(len(s) == 1 for s in pkg_path.split('/')):
                single_letter_pkg += 1
            if len(simple_name) <= 2:
                short_name += 1
            if simple_name and simple_name[-1].isdigit():
                numeric_name += 1
            if not c.source:
                source_missing += 1

        valid = total - malformed_name
        if valid == 0:
            return 1.0

        def scale(val, low, high):
            if val <= low:
                return 0.0
            if val >= high:
                return 1.0
            return (val - low) / (high - low)

        scores = {
            'single_letter_pkg': scale(single_letter_pkg / valid, 0.05, 0.60),
            'no_pkg': scale(no_pkg / valid, 0.02, 0.20),
            'short_name': scale(short_name / valid, 0.05, 0.50),
            'numeric_name': scale(numeric_name / valid, 0.05, 0.30),
            'source_missing': scale(source_missing / valid, 0.10, 0.80),
            'malformed_name': scale(malformed_name / total, 0.0, 0.05),
        }
        weights = {
            'single_letter_pkg': 0.30, 'no_pkg': 0.15, 'short_name': 0.20,
            'numeric_name': 0.10, 'source_missing': 0.10, 'malformed_name': 0.15,
        }
        return sum(scores[k] * weights[k] for k in weights)

    @staticmethod
    def isClassObfuscated(clazz):
        if clazz.name is None:
            return False
        if len(clazz.name) >= 2 and clazz.name[0:2] == 'L;':
            return True

        internal = clazz.name[1:-1]
        if '/' in internal:
            pkg_path = internal[:internal.rfind('/')]
            simple_name = internal[internal.rfind('/') + 1:]
        else:
            pkg_path = ''
            simple_name = internal
        if '$' in simple_name:
            simple_name = simple_name.split('$')[-1]

        if pkg_path and all(len(s) == 1 for s in pkg_path.split('/')):
            if len(simple_name) <= 2 or not clazz.source:
                return True
        if not pkg_path and len(simple_name) <= 2:
            return True
        if len(simple_name) == 1 and not clazz.source:
            return True
        return False

    def removeObfuscatedClasses(self):
        removed = 0
        remaining = []
        for c in self.classes:
            if SmaliProject.isClassObfuscated(c):
                removed += 1
            else:
                remaining.append(c)
        self.classes = remaining
        self.classesdict = {c.name: c for c in remaining}
        return removed

    @staticmethod
    def shouldAnalyzeThisClass(classname, skips=None, includes=None, default=True):
        clazz = classname
        if '/' in classname:
            clazz = classname.replace('/', '.')
        if clazz[0] == '/':
            clazz = clazz[1:]

        if includes is not None:
            for include in includes:
                if include in clazz:
                    return True
        if skips is not None:
            for skip in skips:
                if skip in clazz:
                    return False
        return default

    @staticmethod
    def loadRulesList(fileslist):
        rules = set()
        if isinstance(fileslist, str):
            fileslist = [fileslist]
        for f in fileslist:
            rules |= SmaliProject.loadRulesListFromFile(f)
        return rules

    @staticmethod
    def loadRulesListFromFile(file):
        with open(file, 'r') as f:
            return {entry.strip() for entry in f}

    def searchClass(self, clazzName):
        searchfor = clazzName
        if '/' not in searchfor and '.' in searchfor:
            searchfor = searchfor.replace('.', '/')
        if not (searchfor[0] == 'L' and searchfor[-1] == ';'):
            searchfor = 'L%s;' % searchfor
        for c in self.classes:
            if c is None or c.name is None:
                continue
            if searchfor == c.name:
                return c
        return None

    def matchClasses(self, other):
        similars = []
        old_matched = set()
        new_matched = set()

        # Phase 1: exact name match via classesdict (O(n) vs O(n*m))
        for c in self.classes:
            c2 = other.classesdict.get(c.name)
            if c2 is not None and id(c2) not in new_matched:
                similars.append([c, c2])
                old_matched.add(id(c))
                new_matched.add(id(c2))

        old_rem = [c for c in self.classes if id(c) not in old_matched]
        new_rem = [c for c in other.classes if id(c) not in new_matched]

        # Phase 2: simple name match — precompute simple names to avoid
        # repeated split() and O(n*m) scanning.
        new_by_simple = {}
        for c in new_rem:
            new_by_simple.setdefault(c.name.split('/')[-1], []).append(c)

        for c in old_rem:
            matches = new_by_simple.get(c.name.split('/')[-1])
            if matches:
                c2 = matches.pop(0)
                similars.append([c, c2])
                new_rem.remove(c2)
                if not matches:
                    del new_by_simple[c.name.split('/')[-1]]

        differents = ([[c, None] for c in old_rem] +
                      [[None, c] for c in new_rem])

        return similars, differents

    def differences(self, other, ignores, process_inner_classes=True):
        ret = []
        dd = self.matchClasses(other)
        classesMatching = {}

        def appendMatchedCase(sim):
            classesMatching[sim[0].name] = sim[1].name
            diff = sim[0].differences(sim[1], ignores)
            ret.append([sim, diff if diff else []])

        for sim in dd[0]:
            appendMatchedCase(sim)
        for diff in dd[1]:
            ret.append([diff, None])

        if process_inner_classes:
            processClasses = [(o, n) for o, n in dd[0] if o.hasInnerClasses() or n.hasInnerClasses()]

            while processClasses:
                old, new = processClasses.pop()
                result = SmaliProject.diffAnonymousInnerClasses(old, new, classesMatching)
                for matched in result[0]:
                    appendMatchedCase(matched)
                    if matched[0].hasInnerClasses() or matched[1].hasInnerClasses():
                        processClasses.append((matched[0], matched[1]))
                for c in result[1]:
                    ret.append([[c, None], None])
                for c in result[2]:
                    ret.append([[None, c], None])

                result = SmaliProject.diffNonAnonymousInnerClasses(old, new, classesMatching)
                for matched in result[0]:
                    appendMatchedCase(matched)
                    if matched[0].hasInnerClasses() or matched[1].hasInnerClasses():
                        processClasses.append((matched[0], matched[1]))
                for c in result[1]:
                    ret.append([[c, None], None])
                for c in result[2]:
                    ret.append([[None, c], None])

        return ret

    def _process_inner_classes(self, classes, inner_classes):
        looplevel = 0
        processed_at_least_one = True

        while processed_at_least_one:
            processed_at_least_one = False
            looplevel += 1

            for e in inner_classes:
                if e[1] not in classes:
                    missing_class = smalanalysis.smali.SmaliObject.SmaliClass(self)
                    missing_class.name = "L{};".format(e[1])
                    classes[e[1]] = missing_class
                    self.addClass(missing_class)

                targetclass = classes[e[1]]
                if len(e[2]) == looplevel:
                    targetclass.innerclasses[e[2][-1]] = e[0]
                    e[0].parent = targetclass
                    e[0].innername = '$'.join(e[2])
                    processed_at_least_one = True

    @staticmethod
    def _ic_fingerprint(ic):
        """Cheap pre-filter fingerprint for an anonymous inner class."""
        return (len(ic.methods), len(ic.fields))

    @staticmethod
    def diffAnonymousInnerClasses(old, new, mappings):
        def thisContextDiff(old, new, mappings):
            ret = []
            for r in old.differences(new, [ComparisonIgnores.CLASS_NAME, ComparisonIgnores.FIELD_NAME], mappings):
                if r[2] in (SAME_NAME, REVISED_METHOD):
                    continue
                if len(r) > 3 and isinstance(r[3], list) and len(r[3]) == 1 and r[3][0] == "NOT_SAME_NAME":
                    continue
                ret.append(r)
            return ret

        matches = []
        matchedOld = set()
        matchedNew = set()

        old_anon = list(old.getAnonymousInnerClasses())
        new_anon = list(new.getAnonymousInnerClasses())

        for oldinnerclassname in old_anon:
            oldic = old.innerclasses[oldinnerclassname]
            oldfp = SmaliProject._ic_fingerprint(oldic)
            for newinnerclassname in new_anon:
                if newinnerclassname in matchedNew:
                    continue
                newic = new.innerclasses[newinnerclassname]
                # Cheap fingerprint check before full diff
                if SmaliProject._ic_fingerprint(newic) != oldfp:
                    continue
                diffs = thisContextDiff(oldic, newic, mappings)
                if not diffs:
                    matches.append((oldic, newic))
                    matchedOld.add(oldinnerclassname)
                    matchedNew.add(newinnerclassname)
                    break

        unmatched_old = [old.innerclasses[x] for x in old_anon
                         if x not in matchedOld]
        unmatched_new = [new.innerclasses[x] for x in new_anon
                         if x not in matchedNew]

        return matches, unmatched_old, unmatched_new

    @staticmethod
    def diffNonAnonymousInnerClasses(old, new, mappings):
        oldk = set(old.getNonAnonymousInnerClasses())
        newk = set(new.getNonAnonymousInnerClasses())

        matched = [(old.innerclasses[k], new.innerclasses[k]) for k in oldk & newk]
        unmatchedold = [old.innerclasses[k] for k in oldk - newk]
        unmatchednew = [new.innerclasses[k] for k in newk - oldk]

        return matched, unmatchedold, unmatchednew

    @classmethod
    def from_apk(cls, apk_path, package=None, skiplists=None, includelist=None,
                 include_unpackaged=False, load_cff=False):
        """
        Parse an APK directly via androguard and return a populated
        ``SmaliProject``.

        Args:
            apk_path: Path to the ``.apk`` file.
            package: Optional package name to filter classes.
            skiplists: List of file paths containing skip patterns.
            includelist: List of file paths containing include patterns.
            include_unpackaged: Include classes not in any package.
            load_cff: If True, also run the CFF detector.

        Returns:
            A tuple ``(SmaliProject, Optional[CFFAnalysisResult])``.
        """
        from smalanalysis.smali.androguard_parser import parse_apk

        dex_list, dx = _init_androguard(apk_path)
        project = cls()

        parse_apk(
            dex_list=dex_list, project=project, package=package,
            skiplists=skiplists, includelist=includelist,
            include_unpackaged=include_unpackaged,
        )

        cff_result = None
        if load_cff:
            from smalanalysis.smali.ControlFlowFlatteningDetector import analyze_apk as cff_analyze
            cff_result = cff_analyze(dex_list, dx)

        return project, cff_result

    @classmethod
    def load_cff_results(cls, apk_path):
        """
        Run the CFF detector on an APK and return the results.

        Uses the shared ``_init_androguard`` cache, so calling this after
        ``from_apk(apk_path)`` will **not** re-parse the APK.

        Returns an ``Optional[CFFAnalysisResult]``.
        """
        from smalanalysis.smali.ControlFlowFlatteningDetector import analyze_apk as cff_analyze

        dex_list, dx = _init_androguard(apk_path)
        return cff_analyze(dex_list, dx)
