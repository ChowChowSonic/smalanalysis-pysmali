import unittest
from smalanalysis.smali import Metrics


def _diff_entry(old, new, ctype):
    return [old, new, ctype]


def _field_entry(old, new, ctype, subdiffs=None):
    e = [old, new, ctype]
    if subdiffs is not None:
        e.append(subdiffs)
    return e


class TestIsEvolution(unittest.TestCase):
    def test_empty_list(self):
        self.assertFalse(Metrics.isEvolution([]))

    def test_all_revised_at_least_one_added(self):
        l = [
            [None, "new_method", "NOT_FOUND"],
            ["old", "new", "REVISED_METHOD"],
        ]
        self.assertTrue(Metrics.isEvolution(l))

    def test_no_addition(self):
        l = [["old", "new", "REVISED_METHOD"]]
        self.assertFalse(Metrics.isEvolution(l))

    def test_deletion(self):
        l = [
            [None, "new_method", "NOT_FOUND"],
            ["deleted", None, "NOT_FOUND"],
        ]
        self.assertFalse(Metrics.isEvolution(l))

    def test_other_change_type(self):
        l = [
            [None, "new_method", "NOT_FOUND"],
            ["old", "new", "RENAMED_METHOD"],
        ]
        self.assertFalse(Metrics.isEvolution(l))


class TestIsMethodBodyChangeOnly(unittest.TestCase):
    def test_empty_list(self):
        self.assertTrue(Metrics.isMethodBodyChangeOnly([]))

    def test_all_revised(self):
        l = [
            ["a", "b", "REVISED_METHOD"],
            ["c", "d", "REVISED_METHOD"],
        ]
        self.assertTrue(Metrics.isMethodBodyChangeOnly(l))

    def test_any_other_type(self):
        l = [["a", "b", "REVISED_METHOD"], ["c", None, "NOT_FOUND"]]
        self.assertFalse(Metrics.isMethodBodyChangeOnly(l))


class TestIsChange(unittest.TestCase):
    def test_empty(self):
        self.assertFalse(Metrics.isChange([]))

    def test_evolution_returns_false(self):
        l = [[None, "new", "NOT_FOUND"], ["a", "b", "REVISED_METHOD"]]
        self.assertFalse(Metrics.isChange(l))

    def test_branch_returns_false(self):
        l = [["a", "b", "REVISED_METHOD"]]
        self.assertFalse(Metrics.isChange(l))

    def test_structural_change_returns_true(self):
        l = [["old", None, "NOT_FOUND"]]
        self.assertTrue(Metrics.isChange(l))


class TestInitMetricsDict(unittest.TestCase):
    def test_all_keys_initialized(self):
        out = {}
        Metrics.initMetricsDict("", out)
        for key in Metrics.keys:
            self.assertEqual(out[key], 0, f"key {key} should be 0")
        self.assertEqual(out["addedLines"], set())
        self.assertEqual(out["removedLines"], set())

    def test_prefixed_keys(self):
        out = {}
        Metrics.initMetricsDict("IN_", out)
        for key in Metrics.keys:
            self.assertIn(f"IN_{key}", out)
            self.assertEqual(out[f"IN_{key}"], 0)
        self.assertEqual(out["IN_addedLines"], set())
        self.assertEqual(out["IN_removedLines"], set())


class TestComputeMetrics(unittest.TestCase):
    def setUp(self):
        self.metrics = {}
        Metrics.initMetricsDict("", self.metrics)

    def _make_class(self, name):
        from smalanalysis.smali.SmaliObject import SmaliClass
        c = SmaliClass(None)
        c.name = name
        return c

    def test_deleted_class(self):
        c = self._make_class("Lcom/Old;")
        diff = [[[c, None], None]]
        Metrics.computeMetrics(diff, self.metrics)
        self.assertEqual(self.metrics["CD"], 1)
        self.assertEqual(self.metrics["#C-"], 1)

    def test_added_class(self):
        c = self._make_class("Lcom/New;")
        diff = [[[None, c], None]]
        Metrics.computeMetrics(diff, self.metrics)
        self.assertEqual(self.metrics["CA"], 1)
        self.assertEqual(self.metrics["#C+"], 1)


class TestSplitInnerOuterChanged(unittest.TestCase):
    def _make_class(self, name):
        from smalanalysis.smali.SmaliObject import SmaliClass
        c = SmaliClass(None)
        c.name = name
        return c

    def test_inner_vs_outer(self):
        inner = [[[self._make_class("Lcom/Foo$1;"), self._make_class("Lcom/Foo$1;")], []]]
        outer = [[[self._make_class("Lcom/Bar;"), self._make_class("Lcom/Bar;")], []]]
        combined = inner + outer
        inner_res, outer_res = Metrics.splitInnerOuterChanged(combined)
        self.assertEqual(len(inner_res), 1)
        self.assertEqual(len(outer_res), 1)


class TestCountMethodsInProject(unittest.TestCase):
    def _make_method(self, name="m"):
        from smalanalysis.smali.SmaliObject import SmaliMethod
        return SmaliMethod(name, [], "V", None, None)

    def _make_class(self, name, methods=None):
        from smalanalysis.smali.SmaliObject import SmaliClass
        c = SmaliClass(None)
        c.name = name
        for m in (methods or []):
            c.addMethod(m)
        return c

    def _make_project(self, classes):
        from smalanalysis.smali.SmaliProject import SmaliProject
        p = SmaliProject()
        for c in classes:
            p.addClass(c)
        return p

    def test_no_double_count_inner_classes(self):
        m1 = self._make_method("m1")
        m2 = self._make_method("m2")
        inner = self._make_class("Lcom/Foo$1;", [m1])
        outer = self._make_class("Lcom/Foo;", [m2])
        outer.innerclasses["1"] = inner
        # Both appear in project.classes (as happens after _process_inner_classes)
        project = self._make_project([outer, inner])
        cpt, incpt = Metrics.countMethodsInProject(project)
        self.assertEqual(cpt, 1)   # only outer's method
        self.assertEqual(incpt, 1)  # only inner's method
        self.assertEqual(cpt + incpt, 2)  # total unique methods

    def test_no_inner_classes(self):
        m = self._make_method("m")
        c = self._make_class("Lcom/Foo;", [m])
        project = self._make_project([c])
        cpt, incpt = Metrics.countMethodsInProject(project)
        self.assertEqual(cpt, 1)
        self.assertEqual(incpt, 0)


class TestCountMethodsInClass(unittest.TestCase):
    def test_counts_methods_recursively(self):
        from smalanalysis.smali.SmaliObject import SmaliClass, SmaliMethod
        inner = SmaliClass(None)
        inner.name = "Lcom/Foo$1;"
        inner.addMethod(SmaliMethod("a", [], "V", None, None))
        outer = SmaliClass(None)
        outer.name = "Lcom/Foo;"
        outer.addMethod(SmaliMethod("b", [], "V", None, None))
        outer.innerclasses["1"] = inner
        self.assertEqual(Metrics.countMethodsInClass(outer), 2)


if __name__ == "__main__":
    unittest.main()
