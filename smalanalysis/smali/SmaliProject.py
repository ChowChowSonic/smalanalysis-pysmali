# Smali Projects
# Author: Vincenzo Musco (http://www.vmusco.com)
# Creation date: 2017-09-15
"""
Project-level parsing, class matching, and diffing for collections of smali
files.

``SmaliProject`` represents a set of smali classes parsed from a directory
or ZIP archive.  Two projects can be compared to produce a ``diff`` result
that drives the metrics computation.
"""

import logging
import re
import os
import sys
import zipfile
import warnings

import smalanalysis.smali.SmaliObject
from smalanalysis.smali import ComparisonIgnores
from smalanalysis.smali.ChangesTypes import REVISED_METHOD, SAME_NAME


class MATCHERS:
    """
    Compiled regular expressions reused across the legacy (regex-based) parser.

    Each attribute is a ``re.compile`` pattern that matches a specific smali
    construct (class header, method signature, field declaration, etc.).
    """

    obj = "(\\[*(L[a-zA-Z0-9/_$\\-]+;|Z|B|S|C|I|J|F|D|V))"
    method_reg = re.compile("\\.method( [a-z \\-]+?)*( [a-zA-Z0-9<>_$\\-]+){1}\\((.*)\\)(.*)")  # Without obfuscation
    method = re.compile("\\.method( [a-z \\-]+?)*( [^ ]+){1}\\((.*)\\)(.*)")
    method_param = re.compile("%s" % obj)
    field_init = re.compile("%s( = .*)" % obj)
    fields_reg = re.compile("\\.field( [a-z ]+)*( [a-zA-Z0-9_$\\-]*)+?:(.*)")  # Without obfuscation
    fields = re.compile("\\.field( [a-z ]+)*( [^ ]*)+:([^:]*)")
    clazz = re.compile("\\.class( [a-z ]+)*( [a-zA-Z][a-zA-Z0-9_\\-/$]*)+?;")
    annotation = re.compile("\\.annotation( [a-z ]+)*( L[a-zA-Z0-9_/$]*);")
    ressource_classes = re.compile("^.*/R(\\$[a-z]+)?\\.smali$")
    hex_ref = re.compile("0x[0-9abcdef]{2,}")


class SmaliProject(object):
    """
    A collection of smali classes parsed from a directory tree or a ZIP archive.

    Supports parsing, class matching (linking old ↔ new versions), and
    ``differences()`` to produce structured diff data for metric computation.
    """

    def __init__(self):
        self.classes = []
        self.classesdict = {}
        self.ressources_id = set()

    def addClass(self, c):
        self.classes.append(c)
        self.classesdict[c.name] = c

    def parseRessource(self, ctnt):
        for line in ctnt.split('\n'):
            refs = MATCHERS.hex_ref.findall(line)

            for r in refs:
                self.ressources_id.add(r)

        pass

    def getObfuscationScore(self):
        """
        Compute a multi-signal obfuscation score for the project.

        Returns a float in ``[0.0, 1.0]`` where 0 = likely clean,
        1 = likely obfuscated.  Uses a weighted combination of:
          - single-letter package segments (e.g. ``a/a/a``)
          - default (no) package
          - short class names (≤2 characters)
          - numeric suffix in class names (e.g. ``Class1``)
          - missing ``.source`` attribute
          - malformed names (``L;``)
          - methods with short (≤2 char) names
          - fields with short (≤2 char) names
        """
        total = len(list(self.classes))
        if total == 0:
            return 1.0

        single_letter_pkg = 0
        no_pkg = 0
        short_name = 0
        numeric_name = 0
        source_missing = 0
        malformed_name = 0
        short_methods = 0
        total_eligible_methods = 0
        short_fields = 0
        total_fields = 0

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

            for m in c.methods:
                if m.name in ('<init>', '<clinit>'):
                    continue
                if re.match(r'on[A-Z]', m.name):
                    continue
                total_eligible_methods += 1
                if len(m.name) <= 2:
                    short_methods += 1

            total_fields += len(c.fields)
            short_fields += sum(1 for f in c.fields if len(f.name) <= 2)

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
            'short_method_name': scale(
                short_methods / total_eligible_methods if total_eligible_methods else 0,
                0.05, 0.50
            ),
            'short_field_name': scale(
                short_fields / total_fields if total_fields else 0,
                0.05, 0.50
            ),
        }

        weights = {
            'single_letter_pkg': 0.20,
            'no_pkg': 0.10,
            'short_name': 0.12,
            'numeric_name': 0.07,
            'source_missing': 0.07,
            'malformed_name': 0.10,
            'short_method_name': 0.15,
            'short_field_name': 0.07,
        }

        return sum(scores[k] * weights[k] for k in weights)

    def isProjectObfuscated(self, threshold=0.5):
        """
        Return ``True`` when :meth:`getObfuscationScore` exceeds *threshold*.
        """
        return self.getObfuscationScore() > threshold

    @staticmethod
    def isClassObfuscated(clazz):
        """Return ``True`` if a single class appears obfuscated."""
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

        if simple_name and simple_name[-1].isdigit():
            return True

        eligible_methods = [
            m for m in clazz.methods
            if m.name not in ('<init>', '<clinit>')
            and not re.match(r'on[A-Z]', m.name)
        ]
        if eligible_methods:
            short_methods = sum(1 for m in eligible_methods if len(m.name) <= 2)
            if short_methods / len(eligible_methods) > 0.5:
                return True

        if clazz.fields:
            short_fields = sum(1 for f in clazz.fields if len(f.name) <= 2)
            if short_fields / len(clazz.fields) > 0.5:
                return True

        return False

    def removeObfuscatedClasses(self):
        """Remove all obfuscated classes from this project in-place.

        Returns the number of classes removed.
        """
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
        """
        Return ``True`` if *classname* should be analysed based on the
        given inclusion and exclusion sets.

        - If an *includes* pattern matches → ``True``.
        - If a *skips* pattern matches → ``False``.
        - Otherwise return *default*.
        """
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

        if type(fileslist) == str:
            fileslist = [fileslist]

        for f in fileslist:
            rules = rules.union(SmaliProject.loadRulesListFromFile(f))

        return rules

    @staticmethod
    def loadRulesListFromFile(file):
        rules = set()

        for entry in open(file, 'r'):
            rules.add(entry.strip())

        return rules

    # 1 = class / 2 = ressource / 0 = skip
    @staticmethod
    def keepThisFile(fullpath, package, includes, skips, include_unpackaged):
        if fullpath.endswith('.smali'):
            skip = False

            if package is not None and package.replace('.', '/') not in fullpath:
                skip = True

            if MATCHERS.ressource_classes.match(fullpath):
                return 2

            if '/' not in fullpath:
                return 1 if include_unpackaged else 0

            if skips is not None or includes is not None:
                skip = not SmaliProject.shouldAnalyzeThisClass(fullpath, skips, includes, not skip)

            if fullpath.endswith('/BuildConfig.smali'):
                skip = True

            if not skip:
                return 1

        return 0

    def parseProject(self, folder, package=None, skiplists=None, includelist=None, include_unpackaged=False, use_pysmali=True):
        """
        Parse a project from a folder or ZIP file containing smali files.
        
        Args:
            folder: Path to the folder or ZIP file containing smali files
            package: Optional package name to filter classes
            skiplist: List of files containing patterns to skip
            includelist: List of files containing patterns to include
            include_unpackaged: If True, include classes not in the specified package
            use_pysmali: If True, use the pysmali-based parser (faster and more reliable).
                        If False, fall back to the legacy regex-based parser.
        """
        skips = None
        includes = None
        if skiplists is not None:
            skips = set()
            for s in skiplists:
                skips = skips.union(SmaliProject.loadRulesListFromFile(s))
        if includelist is not None:
            includes = set()
            for s in includelist:
                includes = includes.union(SmaliProject.loadRulesListFromFile(s))

        if os.path.exists(folder):
            if os.path.isfile(folder):
                # This is a ZIP
                with zipfile.ZipFile(folder, 'r') as zp:
                    self._parse_zip_project(zp, package, skips, includes, include_unpackaged, use_pysmali)
            else:
                sys.stderr.write("Parsing folder not supported anymore. Please use archive mode.\n")
                # SmaliProject.parseFolderLoop(folder, folder, self, package, skips=skips, includes=includes, include_unpackaged = includeUnpackaged)
        else:
            sys.stderr.write("File {} not found!\n".format(folder))

    def _parse_zip_project(self, zp, package, skips, includes, include_unpackaged, use_pysmali):
        """
        Parse a project from a ZIP file using pysmali.
        
        Args:
            zp: ZipFile object
            package: Optional package name to filter classes
            skips: Set of patterns to skip
            includes: Set of patterns to include
            include_unpackaged: If True, include classes not in the specified package
            use_pysmali: Whether to use pysmali parser
        """
        classes = {}
        inner_classes = []
        # First, process all .smali files
        failed, successful = 0,0
        for n in zp.namelist():
            op = self.keepThisFile(n, package, includes, skips, include_unpackaged) 
            if op == 1:  # This is a smali class file
                try:
                    with zp.open(n) as f:
                        try:
                            ccontent = f.read().decode('utf-8')
                        except UnicodeDecodeError:
                            ccontent = f.read().decode('latin-1')
                        
                        cls = self.parseClass(ccontent, n, use_pysmali=use_pysmali)
                        #print(str(cls))
                        if cls is None:
                            failed+=1
                            continue
                        cls.parent = self
                        successful+=1

                        # Handle inner classes
                        m2 = cls.name[1:-1].split("$")
                        if len(m2) > 1 and m2[0][-1] != '/':
                            inner_classes.append((cls, m2[0], m2[1:]))
                        else:
                            classes[cls.name[1:-1]] = cls
                            self.addClass(cls)
                            
                except Exception as e:
                    import warnings
                    warnings.warn(
                        f"Error parsing {n}: {str(e)}. Skipping file.",
                        RuntimeWarning
                    )
                    continue
                    
            elif op == 2:  # This is a resource file
                with zp.open(n) as f:
                    try:
                        ccontent = f.read().decode('utf-8')
                    except UnicodeDecodeError:
                        ccontent = f.read().decode('latin-1')
                    self.parseRessource(ccontent)
        sys.stderr.write(f"Failed to parse {failed} classes, with {successful} successfully parsed classes\n")
        # Process inner classes
        self._process_inner_classes(classes, inner_classes)

    def searchClass(self, clazzName):
        searchfor = clazzName

        if '/' not in searchfor and '.' in searchfor:
            searchfor = searchfor.replace('/', '.')

        if not (searchfor[0] == 'L' and searchfor[-1] == ';'):
            searchfor = 'L%s;' % (searchfor)

        for c in self.classes:
            if c is None or c.name is None:
                continue

            if searchfor == c.name:
                return c

        return None

    def matchClasses(self, other):
        old = list(self.classes)
        new = list(other.classes)
        old2 = list()

        differents = []
        similars = []

        while len(old) > 0:
            clazz = old.pop()

            found = False
            for c in new:
                if clazz.name == c.name:
                    similars.append([clazz, c])
                    new.remove(c)
                    found = True
                    break

            if not found:
                old2.append(clazz)

        while len(old2) > 0:
            clazz = old2.pop()

            found = False
            for c in new:
                if clazz.name.split('/')[-1] == c.name.split('/')[-1]:
                    similars.append([clazz, c])
                    new.remove(c)
                    found = True
                    break

            if not found:
                differents.append([clazz, None])

        while len(new) > 0:
            c = new.pop()
            differents.append([None, c])

        return similars, differents

    def differences(self, other, ignores, process_inner_classes=True):
        ret = []
        dd = self.matchClasses(other)
        classesMatching = {}

        def appendMatchedCase(sim):
            classesMatching[sim[0].name] = sim[1].name
            rret = list()
            diff = sim[0].differences(sim[1], ignores)
            if len(diff) > 0:
                rret.extend(diff)

            ret.append([sim, rret])

        for sim in dd[0]:
            appendMatchedCase(sim)

        for diff in dd[1]:
            ret.append([diff, None])

        """
        Additional code for handling inner classes
        """
        if process_inner_classes:
            processClasses = []
            for old, new in dd[0]:
                if old.hasInnerClasses() or new.hasInnerClasses():
                    processClasses.append((old, new))
                elif len(old.innerclasses) + len(new.innerclasses) > 0:
                    # Should not happen
                    assert (False)

            while len(processClasses) > 0:
                popped = processClasses.pop()

                old, new = popped
                result = SmaliProject.diffAnonymousInnerClasses(old, new, classesMatching)

                for matched in result[0]:
                    appendMatchedCase(matched)
                    if matched[0].hasInnerClasses() or matched[1].hasInnerClasses():
                        processClasses.append((matched[0], matched[1]))

                for droppedInnerClasses in result[1]:
                    ret.append([[droppedInnerClasses, None], None])

                for insertedInnerClasses in result[2]:
                    ret.append([[None, insertedInnerClasses], None])

                result = SmaliProject.diffNonAnonymousInnerClasses(old, new, classesMatching)
                for matched in result[0]:
                    appendMatchedCase(matched)
                    if matched[0].hasInnerClasses() or matched[1].hasInnerClasses():
                        processClasses.append((matched[0], matched[1]))

                for droppedInnerClasses in result[1]:
                    ret.append([[droppedInnerClasses, None], None])

                for insertedInnerClasses in result[2]:
                    ret.append([[None, insertedInnerClasses], None])

        return ret

    @staticmethod
    def parseClass(ccontent, name, use_pysmali=True):
        """
        Parse a smali class from its content.
        
        Args:
            ccontent: The smali code to parse
            use_pysmali: If True, use the pysmali-based parser (faster and more reliable).
                        If False, fall back to the legacy regex-based parser.
        """
        if use_pysmali:
            try:
                from .pysmali_parser import parse_smali
                return parse_smali(ccontent, name)
            except ImportError:
                # Fall back to legacy parser if pysmali is not available
                import warnings
                warnings.warn(
                    "pysmali not available, falling back to legacy parser. "
                    "Install with: pip install pysmali",
                    RuntimeWarning
                )
            except Exception as e:
                # Fall back to legacy parser on any other error
                import warnings
                warnings.warn(
                    f"Error using pysmali parser: {e}. Falling back to legacy parser.",
                    RuntimeWarning
                )
        print("Using legacy parser")
        # Fall back to legacy parser if pysmali is not available or fails
        return SmaliProject._legacy_parse_class(ccontent)
    
    @staticmethod
    def _legacy_parse_class(ccontent):
        """Legacy regex-based parser for backward compatibility."""
        clazz = smalanalysis.smali.SmaliObject.SmaliClass(None)

        # Class declaration
        readingmethod = None
        readingannotation = None
        currentobj = clazz

        linenr = -1
        for line in ccontent.split('\n'):
            linenr += 1
            if len(line) > 0 and line[0:1] != '#':
                if readingmethod is not None:
                    if line == '.end method':
                        readingmethod = None
                        currentobj = clazz
                    else:
                        readingmethod.addLine(line.strip())
                    continue

                if line == '.end field':
                    currentobj = clazz
                    continue

                if readingannotation is not None:
                    if line.strip() == '.end annotation':
                        currentobj.addAnnotation(readingannotation)
                        readingannotation = None
                    else:
                        readingannotation.addLine(line.strip())
                    continue

                matched = MATCHERS.clazz.match(line)
                if matched is not None:
                    clazz.setName('%s;' % (matched.group(2).strip()))
                    clazz.addModifiersFromList(
                        matched.group(1).strip().split(' ') if matched.group(1) is not None else None)
                    continue

                if line.startswith('.super '):
                    clazz.setSuper(line[len('.super'):].strip())
                    continue

                if line.startswith('.source '):
                    clazz.setSource(line[len('.source'):].replace('"', '').strip())
                    continue

                if line.startswith('.implements '):
                    clazz.addImplementedInterface(line[len('.implements'):].strip())
                    continue

                matched = MATCHERS.annotation.match(line.strip())
                if matched is not None:
                    modifiers = matched.group(1).strip().split(' ')
                    name = matched.group(2)

                    readingannotation = smalanalysis.smali.SmaliObject.SmaliAnnotation(name, modifiers, clazz)
                    continue

                matched = MATCHERS.method.match(line)
                if matched is not None:
                    # Well this is a method...
                    modifiers = None
                    name = matched.group(2)
                    if name is None:
                        name = matched.group(1)
                    else:
                        modifiers = matched.group(1).strip().split(' ') if matched.group(1) is not None else None

                    name = name.strip()
                    parameters = [it[0] for it in MATCHERS.method_param.findall(matched.group(3))]

                    returnval = matched.group(4)

                    readingmethod = smalanalysis.smali.SmaliObject.SmaliMethod(name, parameters, returnval, modifiers, clazz)
                    currentobj = readingmethod
                    clazz.addMethod(readingmethod)
                    continue

                matched = MATCHERS.fields.match(line)
                if matched is not None:
                    type = matched.group(3)
                    init = None

                    matched2 = MATCHERS.field_init.match(type)
                    if matched2 is not None:
                        type = matched2.group(1)
                        init = matched2.group(3)[3:]

                    currentobj = smalanalysis.smali.SmaliObject.SmaliField(matched.group(2).strip(), type,
                                                              matched.group(1).strip().split(' ') if matched.group(
                                                                  1) is not None else None, init, clazz)
                    clazz.addField(currentobj)
                    continue

                sys.stderr.write("Parsing error.\nLine: %s.\n" % line)
                sys.exit(1)

        return clazz

    def _process_inner_classes(self, classes, inner_classes):
        """
        Process inner classes and link them to their parent classes.
        
        Args:
            classes: Dictionary of class names to class objects
            inner_classes: List of (inner_class, parent_name, name_parts) tuples
        """
        looplevel = 0
        processed_at_least_one = True

        while processed_at_least_one:
            processed_at_least_one = False
            looplevel += 1

            for e in inner_classes:
                if e[1] not in classes:
                    missing_class = smalanalysis.smali.SmaliObject.SmaliClass(e[1])
                    missing_class.name = "L{};".format(e[1])
                    classes[e[1]] = missing_class
                    self.addClass(missing_class)

                targetclass = classes[e[1]]

                if len(e[2]) == looplevel:
                    targetclass.innerclasses[e[2][-1]] = e[0]
                    e[0].parent = targetclass
                    e[0].innername = '$'.join(e[2])
                    processed_at_least_one = True
                    
    def parseAddClass(self, file, use_pysmali=True):
        """
        Parse a smali class from a file and add it to the project.
        
        Args:
            file: Path to the smali file to parse
            use_pysmali: If True, use the pysmali-based parser (faster and more reliable).
                        If False, fall back to the legacy regex-based parser.
        """
        with open(file, 'r', encoding='utf-8') as fp:
            ccontent = fp.read()
        cls = SmaliProject.parseClass(ccontent, file, use_pysmali=use_pysmali)
        if cls:
            cls.parent = self
            self.addClass(cls)
        else: 
            print("skipping empty class")

    # def __eq__(self, other):
    #
    #     # FIXIT Do not use __eq__ directly !
    #     assert (False)

    def equals(self, other, mappings=None):
        return smalanalysis.smali.SmaliObject.compareListsBoolean(self.classes, other.classes)

    # def signatureEq(self, other):
    #     return compareListsBoolean(self.classes, other.classes, True)

    @staticmethod
    def diffAnonymousInnerClasses(old, new, mappings):
        """
        Match anonymous inner classes (named ``$1``, ``$2``, …) between two
        versions using diff-based similarity heuristics.

        Returns a 3-tuple ``(matched, unmatched_old, unmatched_new)``.
        """
        def onlyUnmatched(innerclasses, matchState):
            return filter(lambda x: x not in matchState, innerclasses)

        def thisContextDiff(old, new, mappings):
            ret = []
            for r in old.differences(new, [ComparisonIgnores.CLASS_NAME, ComparisonIgnores.FIELD_NAME], mappings):
                if r[2] == SAME_NAME or r[2] == REVISED_METHOD:
                    continue

                if len(r) > 3 and type(r[3]) == list and len(r[3]) == 1 and r[3][0] == "NOT_SAME_NAME":
                    continue

                ret.append(r)

            return ret

        # Let's compare inner classes to try to match them :)
        matches = []
        matchedOld = []
        matchedNew = []

        for oldinnerclassname in old.getAnonymousInnerClasses():
            for newinnerclassname in onlyUnmatched(new.getAnonymousInnerClasses(), matchedNew):
                diffs = thisContextDiff(old.innerclasses[oldinnerclassname], new.innerclasses[newinnerclassname],
                                        mappings)

                if len(diffs) == 0:
                    # print("\tMatched old ${} and new ${}".format(oldinnerclassname, newinnerclassname))
                    matches.append((old.innerclasses[oldinnerclassname], new.innerclasses[newinnerclassname]))
                    matchedOld.append(oldinnerclassname)
                    matchedNew.append(newinnerclassname)
                    # mappings[old.innerclasses[oldinnerclassname].name] = new.innerclasses[newinnerclassname].name
                    # found = True
                    break
                # elif len(diffs) == 1:
                # print("\tUN-Matched old ${} and new ${} = {}".format(oldinnerclassname, newinnerclassname, diffs))
                # thisContextDiff(old.innerclasses[oldinnerclassname], new.innerclasses[newinnerclassname], mappings)

        # OK, let's see what remains now...
        # for oldinnerclassname in onlyUnmatched(old.getAnonymousInnerClasses(), matchedOld):
        #     print("\tUNMATCHED OLD = {}".format(oldinnerclassname))
        #
        # for newinnerclassname in onlyUnmatched(new.getAnonymousInnerClasses(), matchedNew):
        #     print("\tUNMATCHED NEW = {}".format(newinnerclassname))

        return matches, \
               map(lambda x: old.innerclasses[x],
                   onlyUnmatched(old.getAnonymousInnerClasses(), matchedOld)), \
               map(lambda x: new.innerclasses[x],
                   onlyUnmatched(new.getAnonymousInnerClasses(), matchedNew))

    @staticmethod
    def diffNonAnonymousInnerClasses(old, new, mappings):
        """
        Match named inner classes (not anonymous — e.g. ``MyClass$Helper``)
        between two versions by name.

        Returns a 3-tuple ``(matched, unmatched_old, unmatched_new)``.
        """
        oldc = old.getNonAnonymousInnerClasses()
        oldk = set(list(oldc))
        newc = new.getNonAnonymousInnerClasses()
        newk = set(list(newc))

        matched, unmatchedold, unmatchednew = [], [], []

        for k in oldk.intersection(newk):
            matched.append((old.innerclasses[k], new.innerclasses[k]))
            # print(old.innerclasses[k].differences(old.innerclasses[k], mappings))

        for k in oldk - newk:
            unmatchedold.append(old.innerclasses[k])
            # print("REMOVED: {}".format(k))

        for k in newk - oldk:
            unmatchednew.append(new.innerclasses[k])
            # print("ADDED: {}".format(k))

        return matched, unmatchedold, unmatchednew
