# Metrics Functions
# Author: Vincenzo Musco (http://www.vmusco.com)
# Creation date: 2017-09-15
"""
Metrics computation for APK evolution analysis.

Given a diff result between two versions of a ``SmaliProject``,
this module classifies each change at the class and method level
and produces a dictionary of aggregate counters (added / deleted /
changed / revised classes, methods, fields, and opcode-level
added/removed instruction sets).
"""

from smalanalysis.smali import ChangesTypes, SmaliObject


def isEvolution(l):
    """
    Return ``True`` when *every* diff entry in *l* is either a
    ``REVISED_METHOD`` or a method addition (``[None, new, NOT_FOUND]``),
    with **at least one** addition present.

    A class that only adds new methods and/or revises existing bodies
    (no deletions, no renames, no structural changes) is called an
    "evolution" — it grew without removing anything.
    """
    atLeastOne = False

    for d in l:
        if d[1] is None:
            return False
        elif d[0] is None and d[2] == ChangesTypes.NOT_FOUND:
            atLeastOne = True
        elif d[2] == ChangesTypes.REVISED_METHOD:
            pass
        else:
            return False

    return atLeastOne


def isMethodBodyChangeOnly(l):
    """
    Return ``True`` when *every* entry in *l* is a ``REVISED_METHOD`` —
    i.e. the method signature stayed the same but the body changed.

    A class whose only changes are revised method bodies (no additions,
    no deletions, no renames, no field changes) is called a "branch."
    """
    for d in l:
        if d[2] is not ChangesTypes.REVISED_METHOD:
            return False

    return True


def isChange(l):
    """
    Return ``True`` when *l* contains any structural change — that is,
    changes that are **not** purely "evolution" (additions + revisions)
    and **not** purely "branch" (body-only revisions).

    This covers renamed/deleted methods, changed signatures, field
    modifications, etc.
    """
    return len(l) > 0 and not isEvolution(l) and not isMethodBodyChangeOnly(l)


keys = ["#C-", "#C+", "#M-", "#M+", "E", "B", "A", "D", "C", "MA", "MD", "MR", "MC", "MRev", "FA", "FD", "FC", "FR", "CA", "CD", "CC"]


def initMetricsDict(key, ret):
    """
    Initialise every metric counter in *ret* under the prefix *key* to zero,
    and create empty sets for added/removed opcode lines.

    Args:
        key: A prefix string (e.g. ``""``, ``"IN"``, ``"OUT"``).
        ret: The metrics dictionary to initialise in-place.
    """
    for k in keys:
        ret["{}{}".format(key, k)] = 0

    ret["{}addedLines".format(key)] = set()
    ret["{}removedLines".format(key)] = set()


def computeMetrics(r, out, metricKey="", diffOpOnly=True, aggregateOps=False):
    """
    Walk a diff result list and tally all class-, method-, and field-level
    changes into the *out* dictionary.

    Args:
        r: Result from ``SmaliProject.differences()`` — a list where each
           element is ``[[old_cls, new_cls], [diff_entries]]``.
        out: The metrics dictionary (must already be initialised via
             :func:`initMetricsDict`).
        metricKey: Optional prefix for all metric keys (``""``, ``"IN"``, ``"OUT"``).
        diffOpOnly: If ``True``, only the opcode mnemonic (first word) is
                    recorded for added/removed lines.  Otherwise the full line
                    is stored.
        aggregateOps: If ``True``, opcodes are further aggregated by their
                      first keyword (e.g. ``invoke-virtual``, ``invoke-static``
                      both become ``invoke``).
    """
    changedclass = set()

    for rr in r:
        if rr[1] is None:
            # Class change level here...
            if rr[0][1] is None:
                deleted_class = rr[0][0]
                out["{}CD".format(metricKey)] += 1
                out["{}#C-".format(metricKey)] += 1
                out["{}MD".format(metricKey)] += countMethodsInClass(deleted_class)
                continue
            elif rr[0][0] is None:
                added_class = rr[0][1]
                out["{}CA".format(metricKey)] += 1
                out["{}#C+".format(metricKey)] += 1
                out["{}MA".format(metricKey)] += countMethodsInClass(added_class)
                continue

        out["{}#C-".format(metricKey)] += 1
        out["{}#C+".format(metricKey)] += 1

        if len(rr[1]) == 0:
            continue

        changedclass.add(rr[0][0].name)

        l = rr[1]

        if isEvolution(l):
            out["{}E".format(metricKey)] += 1

        if isMethodBodyChangeOnly(l):
            out["{}B".format(metricKey)] += 1

        if isChange(l):
            out["{}C".format(metricKey)] += 1

        atLeastOneMethodAdded, atLeastOneMethodDeleted = False, False
        for rrr in rr[1]:
            if rrr[0] is not None and rrr[0].isField() and rrr[1] is None:
                out["{}FD".format(metricKey)] += 1
            elif rrr[1] is not None and rrr[1].isField() and rrr[0] is None:
                out["{}FA".format(metricKey)] += 1
            elif rrr[0] is not None and rrr[1] is not None and rrr[0].isField():
                if len(rrr) > 3 and len(rrr[3]) == 1 and rrr[3][0] == SmaliObject.NOT_SAME_NAME:
                    out["{}FR".format(metricKey)] += 1
                else:
                    out["{}FC".format(metricKey)] += 1
            elif rrr[0] is not None and rrr[0].isMethod() and rrr[1] is None:
                out["{}MD".format(metricKey)] += 1
                atLeastOneMethodDeleted = True
            elif rrr[1] is not None and rrr[1].isMethod() and rrr[0] is None:
                out["{}MA".format(metricKey)] += 1
                atLeastOneMethodAdded = True
            elif rrr[0] is not None and rrr[1] is not None and rrr[0].isMethod():
                if rrr[2] == ChangesTypes.RENAMED_METHOD:
                    out["{}MR".format(metricKey)] += 1
                else:
                    out["{}MC".format(metricKey)] += 1
                    if not rrr[0].areSourceCodeSimilars(rrr[1]):
                        out["{}MRev".format(metricKey)] += 1

                    l = set(rrr[1].getCleanLines()) - set(rrr[0].getCleanLines())
                    if diffOpOnly:
                        l = list(map(lambda x: x.split(' ')[0], l))
                    for cmd in l:
                        if aggregateOps:
                            cmd = cmd.split('/')[0].split('-')[0]
                        out["{}addedLines".format(metricKey)].add(cmd)

                    l = set(rrr[0].getCleanLines()) - set(rrr[1].getCleanLines())
                    if diffOpOnly:
                        l = list(map(lambda x: x.split(' ')[0], l))
                    for cmd in l:
                        if aggregateOps:
                            cmd = cmd.split('/')[0].split('-')[0]
                        out["{}removedLines".format(metricKey)].add(cmd)

        out["{}CC".format(metricKey)] += 1
        out["{}A".format(metricKey)] += 1 if atLeastOneMethodAdded else 0
        out["{}D".format(metricKey)] += 1 if atLeastOneMethodDeleted else 0


def splitInnerOuterChanged(diff):
    """
    Split a diff list into two lists — one containing entries whose
    classes have ``$`` in their name (inner classes) and one for the rest.

    Returns:
        A pair ``(innerDiff, outerDiff)``.
    """
    innerDiff, outerDiff = [], []

    for d in diff:
        if (d[0][0] is not None and "$" in d[0][0].name) or (d[0][1] is not None and "$" in d[0][1].name):
            innerDiff.append(d)
        else:
            outerDiff.append(d)

    return innerDiff, outerDiff


def countMethodsInProject(project):
    """
    Count all methods in a ``SmaliProject``.

    Returns:
        A pair ``(outer_count, inner_count)`` where:
        - *outer_count*: methods in top-level classes
        - *inner_count*: methods in inner (nested) classes
    """
    inner_class_ids = set()
    for c in project.classes:
        for ic in c.innerclasses:
            inner_class_ids.add(id(c.innerclasses[ic]))

    cpt = 0
    incpt = 0

    for c in project.classes:
        if id(c) in inner_class_ids:
            incpt += len(c.methods)
        else:
            cpt += len(c.methods)

    return cpt, incpt

def countMethodsInClass(clazz):
    """
    Recursively count all methods defined in a class, including those
    in its nested inner classes.

    Returns:
        The total number of methods.
    """
    cpt = len(clazz.methods)

    for ic in clazz.innerclasses:
        cpt += countMethodsInClass(clazz.innerclasses[ic])

    return cpt
