import unittest
import tempfile
import os
import pathlib
from smalanalysis.smali.SmaliProject import SmaliProject
from smalanalysis.smali.SmaliObject import SmaliClass, SmaliMethod, SmaliField


class TestSmaliProject(unittest.TestCase):
    def _make_project(self, classes):
        p = SmaliProject()
        for c in classes:
            p.addClass(c)
        return p

    def _make_class(self, name, methods=None, fields=None):
        c = SmaliClass(None)
        c.name = name
        c.parent = self._make_project([c]) if not hasattr(self, '_proj') else self._proj
        for m in (methods or []):
            c.addMethod(m)
        for f in (fields or []):
            c.addField(f)
        return c

    def _make_method(self, name="m", params=None, ret="V"):
        return SmaliMethod(name, params or [], ret, None, None)

    def _make_field(self, name="f", type_="I"):
        return SmaliField(name, type_, None, None, None)


class TestSearchClass(TestSmaliProject):
    def test_exact_L_format(self):
        p = self._make_project([self._make_class("Lcom/Foo;")])
        self.assertIsNotNone(p.searchClass("Lcom/Foo;"))

    def test_dotted_name(self):
        p = self._make_project([self._make_class("Lcom/Foo;")])
        result = p.searchClass("com.Foo")
        # Dotted name should be converted to L...; format and found
        self.assertIsNotNone(result)

    def test_missing_class(self):
        p = self._make_project([])
        self.assertIsNone(p.searchClass("Lcom/Foo;"))

    def test_none_name_in_classes(self):
        c = self._make_class("Lcom/Foo;")
        c2 = SmaliClass(None)
        c2.name = None
        p = self._make_project([c, c2])
        self.assertIsNotNone(p.searchClass("Lcom/Foo;"))


class TestShouldAnalyzeThisClass(TestSmaliProject):
    def test_default_include(self):
        self.assertTrue(SmaliProject.shouldAnalyzeThisClass("com/Foo"))

    def test_skip_excludes(self):
        self.assertFalse(
            SmaliProject.shouldAnalyzeThisClass(
                "com/Foo", skips={"com.Foo"}
            )
        )

    def test_include_overrides_default(self):
        self.assertFalse(
            SmaliProject.shouldAnalyzeThisClass(
                "com/Bar", includes={"com.Foo"}, default=False
            )
        )

    def test_skip_checked_after_include(self):
        self.assertFalse(
            SmaliProject.shouldAnalyzeThisClass(
                "com/Foo", skips={"com.Foo"}, includes={"com.Bar"}
            )
        )

    def test_leading_slash(self):
        self.assertTrue(
            SmaliProject.shouldAnalyzeThisClass("/com/Foo")
        )

    def test_dot_to_slash(self):
        self.assertTrue(
            SmaliProject.shouldAnalyzeThisClass("com.Foo", includes={"com/Foo"})
        )


class TestLoadRulesListFromFile(TestSmaliProject):
    def test_load_rules(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("com/foo\ncom/bar\n")
            fname = f.name
        try:
            rules = SmaliProject.loadRulesListFromFile(fname)
            self.assertEqual(rules, {"com/foo", "com/bar"})
        finally:
            os.unlink(fname)

    def test_load_rules_list(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f1:
            f1.write("a\nb\n")
            n1 = f1.name
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f2:
            f2.write("c\n")
            n2 = f2.name
        try:
            rules = SmaliProject.loadRulesList([n1, n2])
            self.assertEqual(rules, {"a", "b", "c"})
        finally:
            os.unlink(n1)
            os.unlink(n2)

    def test_load_rules_list_single_string(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("x\n")
            fname = f.name
        try:
            rules = SmaliProject.loadRulesList(fname)
            self.assertEqual(rules, {"x"})
        finally:
            os.unlink(fname)


class TestMatchClasses(TestSmaliProject):
    def test_exact_name_match(self):
        a = self._make_class("Lcom/Foo;")
        b = self._make_class("Lcom/Foo;")
        p1 = self._make_project([a])
        p2 = self._make_project([b])
        similars, differents = p1.matchClasses(p2)
        self.assertEqual(len(similars), 1)
        self.assertEqual(len(differents), 0)

    def test_short_name_fallback(self):
        a = self._make_class("Lcom/Foo;")
        b = self._make_class("Lorg/Foo;")
        p1 = self._make_project([a])
        p2 = self._make_project([b])
        similars, differents = p1.matchClasses(p2)
        self.assertEqual(len(similars), 1)

    def test_deleted_class(self):
        a = self._make_class("Lcom/Foo;")
        p1 = self._make_project([a])
        p2 = self._make_project([])
        similars, differents = p1.matchClasses(p2)
        self.assertEqual(len(differents), 1)
        self.assertEqual(differents[0][0], a)
        self.assertIsNone(differents[0][1])

    def test_added_class(self):
        b = self._make_class("Lcom/Foo;")
        p1 = self._make_project([])
        p2 = self._make_project([b])
        similars, differents = p1.matchClasses(p2)
        self.assertEqual(len(differents), 1)
        self.assertIsNone(differents[0][0])
        self.assertEqual(differents[0][1], b)


class TestGetObfuscationScore(TestSmaliProject):
    def test_empty_project(self):
        p = self._make_project([])
        self.assertEqual(p.getObfuscationScore(), 1.0)

    def test_clean_project(self):
        c = SmaliClass(None)
        c.name = "Lcom/example/MyClass;"
        c.setSource("MyClass.java")
        p = self._make_project([c])
        # All clean, should be low
        self.assertLess(p.getObfuscationScore(), 0.2)

    def test_malformed_name(self):
        c = SmaliClass(None)
        c.name = "L;"
        p = self._make_project([c])
        self.assertEqual(p.getObfuscationScore(), 1.0)

    def test_single_letter_package(self):
        c = SmaliClass(None)
        c.name = "La/b/c/MyClass;"
        c.setSource("MyClass.java")
        p = self._make_project([c])
        self.assertGreater(p.getObfuscationScore(), 0.1)


class TestIsClassObfuscated(TestSmaliProject):
    def test_none_name(self):
        c = SmaliClass(None)
        c.name = None
        self.assertFalse(SmaliProject.isClassObfuscated(c))

    def test_malformed_l_semicolon(self):
        c = SmaliClass(None)
        c.name = "L;"
        self.assertTrue(SmaliProject.isClassObfuscated(c))

    def test_single_letter_package_with_short_name_no_source(self):
        c = SmaliClass(None)
        c.name = "La/b/c/F;"
        self.assertTrue(SmaliProject.isClassObfuscated(c))

    def test_single_letter_package_with_long_name_and_source(self):
        c = SmaliClass(None)
        c.name = "La/b/c/Foo;"
        c.setSource("Foo.java")
        self.assertFalse(SmaliProject.isClassObfuscated(c))

    def test_no_package_short_name(self):
        c = SmaliClass(None)
        c.name = "LF;"
        self.assertTrue(SmaliProject.isClassObfuscated(c))

    def test_no_package_long_name(self):
        c = SmaliClass(None)
        c.name = "LFoo;"
        self.assertFalse(SmaliProject.isClassObfuscated(c))

    def test_single_char_name_no_source(self):
        c = SmaliClass(None)
        c.name = "Lcom/example/F;"
        self.assertTrue(SmaliProject.isClassObfuscated(c))

    def test_single_char_name_with_source(self):
        c = SmaliClass(None)
        c.name = "Lcom/example/F;"
        c.setSource("F.java")
        self.assertFalse(SmaliProject.isClassObfuscated(c))

    def test_clean_class(self):
        c = SmaliClass(None)
        c.name = "Lcom/example/MyClass;"
        c.setSource("MyClass.java")
        self.assertFalse(SmaliProject.isClassObfuscated(c))


class TestRemoveObfuscatedClasses(TestSmaliProject):
    def test_removes_obfuscated(self):
        clean = SmaliClass(None)
        clean.name = "Lcom/example/Foo;"
        clean.setSource("Foo.java")
        bad = SmaliClass(None)
        bad.name = "La/b/F;"
        p = self._make_project([clean, bad])
        removed = p.removeObfuscatedClasses()
        self.assertEqual(removed, 1)
        self.assertEqual(len(p.classes), 1)
        self.assertIn(clean, p.classes)
        self.assertNotIn(bad, p.classes)

    def test_classesdict_sync(self):
        clean = SmaliClass(None)
        clean.name = "Lcom/example/Foo;"
        clean.setSource("Foo.java")
        p = self._make_project([clean])
        p.removeObfuscatedClasses()
        self.assertIn("Lcom/example/Foo;", p.classesdict)

    def test_all_obfuscated(self):
        bad = SmaliClass(None)
        bad.name = "La/b/F;"
        p = self._make_project([bad])
        removed = p.removeObfuscatedClasses()
        self.assertEqual(removed, 1)
        self.assertEqual(len(p.classes), 0)
        self.assertEqual(len(p.classesdict), 0)


class TestFromApk(TestSmaliProject):
    def test_from_apk_invalid_path(self):
        with self.assertRaises(Exception):
            SmaliProject.from_apk("/nonexistent.apk")

    @unittest.skipUnless(
        os.path.exists(os.path.join(os.path.dirname(__file__), "..", "cobos.svgviewer.apk")),
        "Test APK cobos.svgviewer.apk not found",
    )
    def test_from_apk_basic(self):
        apk_path = os.path.join(os.path.dirname(__file__), "..", "cobos.svgviewer.apk")
        project, cff = SmaliProject.from_apk(apk_path)
        self.assertGreater(len(project.classes), 0)
        self.assertIsNone(cff)

    @unittest.skipUnless(
        os.path.exists(os.path.join(os.path.dirname(__file__), "..", "cobos.svgviewer.apk")),
        "Test APK cobos.svgviewer.apk not found",
    )
    def test_from_apk_with_cff(self):
        apk_path = os.path.join(os.path.dirname(__file__), "..", "cobos.svgviewer.apk")
        project, cff = SmaliProject.from_apk(apk_path, load_cff=True)
        self.assertIsNotNone(cff)

    @unittest.skipUnless(
        os.path.exists(os.path.join(os.path.dirname(__file__), "..", "cobos.svgviewer.apk")),
        "Test APK cobos.svgviewer.apk not found",
    )
    def test_from_apk_package_filter(self):
        apk_path = os.path.join(os.path.dirname(__file__), "..", "cobos.svgviewer.apk")
        project, _ = SmaliProject.from_apk(apk_path, package="com.cobos")
        for c in project.classes:
            self.assertIn("com/cobos", c.name)


@unittest.skipUnless(
    os.path.exists(os.path.join(os.path.dirname(__file__), "..", "cobos.svgviewer.apk")),
    "Test APK cobos.svgviewer.apk not found",
)
class TestLoadCffResults(TestSmaliProject):
    def test_load_cff_results(self):
        apk_path = os.path.join(os.path.dirname(__file__), "..", "cobos.svgviewer.apk")
        result = SmaliProject.load_cff_results(apk_path)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
