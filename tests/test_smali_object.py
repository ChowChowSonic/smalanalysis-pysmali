import unittest
from smalanalysis.smali.SmaliObject import (
    compareStringSets,
    compareListsSameposition,
    compareLists,
    bidirectCompareLists,
    compareListsBoolean,
    compareWithMapping,
    SmaliAnnotableModifiable,
    SmaliWithLines,
    SmaliField,
    SmaliMethod,
    SmaliClass,
    SELF,
    OTHER,
    NOT_SAME_NAME,
    NOT_SAME_RETURN_TYPE,
    NOT_SAME_MODIFIERS,
    NOT_SAME_PARAMETERS,
    NOT_SAME_TYPE,
    NOT_SAME_SOURCECODE_LINES,
    NOT_SAME_PARENT,
    NOT_SAME_INIT_VALUE,
    NOT_SAME_INTERFACES,
)
from smalanalysis.smali.SmaliProject import SmaliProject


class TestCompareStringSets(unittest.TestCase):
    def test_equal(self):
        self.assertTrue(compareStringSets({"a", "b"}, {"b", "a"}))

    def test_different(self):
        self.assertFalse(compareStringSets({"a"}, {"b"}))

    def test_empty(self):
        self.assertTrue(compareStringSets(set(), set()))


class TestCompareListsSameposition(unittest.TestCase):
    def test_equal_string_lists(self):
        self.assertTrue(compareListsSameposition(["a", "b"], ["a", "b"]))

    def test_different_length(self):
        self.assertFalse(compareListsSameposition(["a"], ["a", "b"]))

    def test_type_mismatch(self):
        self.assertFalse(compareListsSameposition(["a"], [1]))

    def test_with_mappings(self):
        mappings = {"old": "new"}
        self.assertTrue(
            compareListsSameposition(["old"], ["new"], mappings)
        )

    def test_mappings_no_match(self):
        mappings = {"old": "new"}
        self.assertFalse(
            compareListsSameposition(["old"], ["other"], mappings)
        )


class TestCompareListsAndBidirect(unittest.TestCase):
    def test_compare_lists_no_missing(self):
        class FakeObj:
            def differences(self, other, ignores=None, mappings=None):
                return []
        self.assertEqual(compareLists([FakeObj()], [FakeObj()]), [])

    def test_compare_lists_with_missing(self):
        class FakeObj:
            def __init__(self, name):
                self.name = name
            def differences(self, other, ignores=None, mappings=None):
                if self.name == other.name:
                    return []
                return [self.name]
        self.assertEqual(
            len(compareLists([FakeObj("a"), FakeObj("b")], [FakeObj("a")])),
            1,
        )

    def test_bidirect_self_other_prefix(self):
        class FakeObj:
            def __init__(self, name):
                self.name = name
            def differences(self, other, ignores=None, mappings=None):
                if self.name == other.name:
                    return []
                return [self.name]
        result = bidirectCompareLists(
            [FakeObj("a"), FakeObj("b")], [FakeObj("a"), FakeObj("c")]
        )
        self.assertEqual(len(result), 2)
        labels = {r[0] for r in result}
        self.assertEqual(labels, {SELF, OTHER})

    def test_compare_lists_boolean_true(self):
        class FakeObj:
            def differences(self, other, ignores=None, mappings=None):
                return []
        self.assertTrue(
            compareListsBoolean([FakeObj()], [FakeObj()])
        )

    def test_compare_lists_boolean_false(self):
        class FakeObj:
            def __init__(self, name):
                self.name = name
            def differences(self, other, ignores=None, mappings=None):
                return [self.name]
        self.assertFalse(
            compareListsBoolean([FakeObj("a")], [FakeObj("b")])
        )


class TestCompareWithMapping(unittest.TestCase):
    def test_no_mapping_direct_match(self):
        self.assertTrue(compareWithMapping("Lcom/Foo;", "Lcom/Foo;", None))

    def test_no_mapping_different(self):
        self.assertFalse(compareWithMapping("Lcom/Foo;", "Lcom/Bar;", None))

    def test_exact_mapping_match(self):
        mappings = {"Lcom/Old;": "Lcom/New;"}
        self.assertTrue(compareWithMapping("Lcom/Old;", "Lcom/New;", mappings))

    def test_inner_class_anonymous_substitution(self):
        mappings = {"Lcom/Foo;": "Lcom/Bar;"}
        self.assertTrue(
            compareWithMapping(
                "Lcom/Foo$1;", "Lcom/Bar$2;", mappings
            )
        )

    def test_regex_none_regression(self):
        old = "not_a_class_descriptor"
        self.assertFalse(
            compareWithMapping(old, "something", {"x": "y"})
        )


class TestSmaliAnnotableModifiable(unittest.TestCase):
    def test_differences_modifier_match(self):
        a = SmaliAnnotableModifiable(None)
        b = SmaliAnnotableModifiable(None)
        a.modifiers = {"public", "static"}
        b.modifiers = {"public", "static"}
        self.assertEqual(a.differences(b, []), [])

    def test_differences_modifier_mismatch(self):
        a = SmaliAnnotableModifiable(None)
        b = SmaliAnnotableModifiable(None)
        a.modifiers = {"public"}
        b.modifiers = {"private"}
        self.assertIn(NOT_SAME_MODIFIERS, a.differences(b, []))

    def test_differences_ignores_modifiers(self):
        a = SmaliAnnotableModifiable(None)
        b = SmaliAnnotableModifiable(None)
        a.modifiers = {"public"}
        b.modifiers = {"private"}
        self.assertEqual(
            a.differences(b, ["ANOT_MOD_MODIFIERS"]), []
        )


class TestSmaliWithLines(unittest.TestCase):
    def test_differences_name_match(self):
        a = SmaliWithLines("foo", None, None)
        b = SmaliWithLines("foo", None, None)
        self.assertEqual(a.differences(b, []), [])

    def test_differences_name_mismatch(self):
        a = SmaliWithLines("foo", None, None)
        b = SmaliWithLines("bar", None, None)
        diffs = a.differences(b, [])
        self.assertIn(NOT_SAME_NAME, diffs)

    def test_differences_source_code_mismatch(self):
        a = SmaliWithLines("x", None, None)
        b = SmaliWithLines("x", None, None)
        a.addLine("const v0, 1")
        b.addLine("const v0, 2")
        diffs = a.differences(b, [])
        self.assertIn(NOT_SAME_SOURCECODE_LINES, diffs)

    def test_keep_this_line(self):
        self.assertTrue(SmaliWithLines.keepThisLine("const v0, 1"))
        self.assertFalse(SmaliWithLines.keepThisLine(".line 10"))
        self.assertFalse(SmaliWithLines.keepThisLine(":cond_0"))
        self.assertFalse(SmaliWithLines.keepThisLine("    # comment"))

    def test_clean_lines_filters(self):
        a = SmaliWithLines("x", None, None)
        a.addLine(".line 10")
        a.addLine("    const v0, 1")
        a.addLine("")
        cleaned = a.getCleanLines()
        self.assertEqual(cleaned, ["    const v0, 1"])

    def test_clear_r_references(self):
        lines = ["const v0, 0x7f030001", "return-void"]
        result = SmaliWithLines.clearRReferences(lines)
        self.assertIn("<R_REF>", result[0])
        self.assertEqual(result[1], "return-void")

    def test_clear_inner_class_references(self):
        lines = ["Lcom/Foo$1;", "Lcom/Foo$12;"]
        result = SmaliWithLines.clearInnerClassesReferences(lines)
        for l in result:
            self.assertIn("$?", l)

    def test_get_identity_lines_applies_all_transforms(self):
        a = SmaliWithLines("x", None, None)
        a.addLine("    invoke-virtual {v0}, Lcom/Foo;->bar(I)V")
        ids = a.getIdentityLines()
        self.assertEqual(len(ids), 1)
        line = ids[0]
        self.assertNotIn("v0", line)
        self.assertNotIn("Lcom/Foo;->bar(I)V", line)
        self.assertNotIn(":cond", line)


class TestSmaliField(unittest.TestCase):
    def test_equals_match(self):
        a = SmaliField("x", "I", None, None, None)
        b = SmaliField("x", "I", None, None, None)
        self.assertTrue(a.equals(b))

    def test_equals_name_mismatch(self):
        a = SmaliField("x", "I", None, None, None)
        b = SmaliField("y", "I", None, None, None)
        self.assertFalse(a.equals(b))

    def test_differences_name_mismatch(self):
        a = SmaliField("x", "I", None, None, None)
        b = SmaliField("y", "I", None, None, None)
        self.assertIn(NOT_SAME_NAME, a.differences(b, []))

    def test_differences_type_mismatch(self):
        a = SmaliField("x", "I", None, None, None)
        b = SmaliField("x", "J", None, None, None)
        self.assertIn(NOT_SAME_TYPE, a.differences(b, []))

    def test_differences_init_mismatch(self):
        a = SmaliField("x", "I", None, "5", None)
        b = SmaliField("x", "I", None, "10", None)
        self.assertIn(NOT_SAME_INIT_VALUE, a.differences(b, []))

    def test_is_field(self):
        f = SmaliField("x", "I", None, None, None)
        self.assertTrue(f.isField())
        self.assertFalse(f.isMethod())


class TestSmaliMethod(unittest.TestCase):
    def test_equals_match(self):
        a = SmaliMethod("foo", ["I", "J"], "V", None, None)
        b = SmaliMethod("foo", ["I", "J"], "V", None, None)
        self.assertTrue(a.equals(b))

    def test_equals_return_mismatch(self):
        a = SmaliMethod("foo", ["I"], "V", None, None)
        b = SmaliMethod("foo", ["I"], "I", None, None)
        self.assertFalse(a.equals(b))

    def test_equals_param_mismatch(self):
        a = SmaliMethod("foo", ["I"], "V", None, None)
        b = SmaliMethod("foo", ["J"], "V", None, None)
        self.assertFalse(a.equals(b))

    def test_differences_return_type(self):
        a = SmaliMethod("foo", [], "V", None, None)
        b = SmaliMethod("foo", [], "I", None, None)
        self.assertIn(NOT_SAME_RETURN_TYPE, a.differences(b, []))

    def test_differences_params(self):
        a = SmaliMethod("foo", ["I"], "V", None, None)
        b = SmaliMethod("foo", ["J"], "V", None, None)
        self.assertIn(NOT_SAME_PARAMETERS, a.differences(b, []))

    def test_is_method(self):
        m = SmaliMethod("foo", [], "V", None, None)
        self.assertTrue(m.isMethod())
        self.assertFalse(m.isField())

    def test_get_signature(self):
        m = SmaliMethod("foo", ["I", "J"], "V", None, None)
        self.assertEqual(m.getSignature(), "V foo(IJ)")

    def test_get_full_signature_no_parent(self):
        m = SmaliMethod("foo", [], "V", None, None)
        self.assertIn("foo", m.getFullSignature())

    def test_uses_stringbuilder_defaults(self):
        m = SmaliMethod("foo", [], "V", None, None)
        self.assertFalse(m.uses_stringbuilder)
        self.assertFalse(m.uses_bytearray_string)

    def test_more_than_n_instruction(self):
        m = SmaliMethod("foo", [], "V", None, None)
        m.addLine("const v0, 1")
        self.assertFalse(m.moreThanNInstruction(1))
        m.addLine("return v0")
        self.assertTrue(m.moreThanNInstruction(1))


class TestSmaliClass(unittest.TestCase):
    def _make_field(self, name, type_="I", init=None, modifiers=None):
        return SmaliField(name, type_, modifiers, init, None)

    def _make_method(self, name, params=None, ret="V", modifiers=None):
        m = SmaliMethod(name, params or [], ret, modifiers, None)
        return m

    def test_add_and_get_methods(self):
        c = SmaliClass(None)
        c.name = "Lcom/Foo;"
        m = self._make_method("bar")
        c.addMethod(m)
        self.assertIn(m, c.methods)

    def test_add_and_get_fields(self):
        c = SmaliClass(None)
        c.name = "Lcom/Foo;"
        f = self._make_field("x")
        c.addField(f)
        self.assertIn(f, c.fields)

    def test_set_name(self):
        c = SmaliClass(None)
        c.setName("Lcom/Foo;")
        self.assertEqual(c.name, "Lcom/Foo;")

    def test_set_super(self):
        c = SmaliClass(None)
        c.setSuper("Ljava/lang/Object;")
        self.assertEqual(c.zuper, "Ljava/lang/Object;")

    def test_get_super(self):
        c = SmaliClass(None)
        c.setSuper("Ljava/lang/Object;")
        self.assertEqual(c.getSuper(), "java/lang/Object")

    def test_add_implemented_interface(self):
        c = SmaliClass(None)
        c.addImplementedInterface("Ljava/io/Serializable;")
        self.assertIn("Ljava/io/Serializable;", c.implements)

    def test_has_inner_classes(self):
        c = SmaliClass(None)
        self.assertFalse(c.hasInnerClasses())
        c.innerclasses["1"] = None
        self.assertTrue(c.hasInnerClasses())

    def test_get_anonymous_inner_classes(self):
        c = SmaliClass(None)
        c.innerclasses["1"] = None
        c.innerclasses["2"] = None
        c.innerclasses["Foo"] = None
        anon = list(c.getAnonymousInnerClasses())
        self.assertEqual(set(anon), {"1", "2"})

    def test_get_non_anonymous_inner_classes(self):
        c = SmaliClass(None)
        c.innerclasses["1"] = None
        c.innerclasses["Foo"] = None
        non_anon = list(c.getNonAnonymousInnerClasses())
        self.assertEqual(non_anon, ["Foo"])

    def test_get_base_name(self):
        c = SmaliClass(None)
        c.name = "Lcom/example/Foo;"
        self.assertEqual(c.getBaseName(), "com/example/Foo")

    def test_get_base_name_inner(self):
        c = SmaliClass(None)
        c.name = "Lcom/example/Foo$1;"
        self.assertEqual(c.getBaseName(), "com/example/Foo")

    def test_get_display_name(self):
        name = SmaliClass.getDisplayName("Lcom/example/Foo;")
        self.assertEqual(name, "com.example.Foo")

    def test_differences_class_name(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        b = SmaliClass(None)
        b.name = "Lcom/Bar;"
        diffs = a.differences(b, [])
        self.assertTrue(
            any(d[2] == NOT_SAME_NAME for d in diffs if len(d) == 3)
        )

    def test_differences_super(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        a.zuper = "Ljava/lang/Object;"
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        b.zuper = "Ljava/lang/Throwable;"
        diffs = a.differences(b, [])
        self.assertTrue(
            any(d[2] == NOT_SAME_PARENT for d in diffs if len(d) == 3)
        )

    def test_differences_interfaces(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        a.implements = {"LIFace1;"}
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        b.implements = {"LIFace2;"}
        diffs = a.differences(b, [])
        self.assertTrue(
            any(d[2] == NOT_SAME_INTERFACES for d in diffs if len(d) == 4)
        )

    def test_differences_methods(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        a.addMethod(self._make_method("foo"))
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        b.addMethod(self._make_method("bar"))
        diffs = a.differences(b, [])
        # Should find method differences
        self.assertTrue(len(diffs) > 0)

    def test_differences_fields(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        a.addField(self._make_field("x"))
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        b.addField(self._make_field("y"))
        diffs = a.differences(b, [])
        self.assertTrue(len(diffs) > 0)

    def test_methods_comparison_exact_match(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        m_old = self._make_method("foo")
        m_new = self._make_method("foo")
        a.addMethod(m_old)
        b.addMethod(m_new)
        sames, diffs = a.methodsComparison(b, [])
        self.assertEqual(len(sames), 1)
        self.assertEqual(len(diffs), 0)

    def test_methods_comparison_deleted(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        a.addMethod(self._make_method("foo"))
        sames, diffs = a.methodsComparison(b, [])
        self.assertEqual(len(diffs), 1)
        self.assertIsNone(diffs[0][1])

    def test_methods_comparison_added(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        b.addMethod(self._make_method("foo"))
        sames, diffs = a.methodsComparison(b, [])
        added = [d for d in diffs if d[0] is None]
        self.assertEqual(len(added), 1)

    def test_methods_comparison_revised_body(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        ma = self._make_method("foo")
        ma.addLine("const v0, 1")
        mb = self._make_method("foo")
        mb.addLine("const v0, 2")
        a.addMethod(ma)
        b.addMethod(mb)
        sames, diffs = a.methodsComparison(b, [])
        revised = [d for d in diffs if len(d) > 2 and d[2] == "REVISED_METHOD"]
        self.assertEqual(len(revised), 1)

    def test_fields_comparison_exact_match(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        a.addField(self._make_field("x", "I"))
        b.addField(self._make_field("x", "I"))
        sames, diffs = a.fieldsComparison(b, [], [])
        self.assertEqual(len(sames), 1)
        self.assertEqual(len(diffs), 0)

    def test_fields_comparison_deleted(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        a.addField(self._make_field("x"))
        sames, diffs = a.fieldsComparison(b, [], [])
        deleted = [d for d in diffs if d[1] is None]
        self.assertEqual(len(deleted), 1)

    def test_fields_comparison_init_only_change(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        a.addField(self._make_field("x", "I", "5"))
        b.addField(self._make_field("x", "I", "10"))
        sames, diffs = a.fieldsComparison(b, [], [])
        # Should still match as same field (ignore init)
        changed = [d for d in diffs if d[1] is not None]
        self.assertEqual(len(changed), 1)

    def test_find_method(self):
        c = SmaliClass(None)
        c.name = "Lcom/Foo;"
        m = self._make_method("foo", ["I"], "V")
        c.addMethod(m)
        found = c.findMethod("foo", "I", "V")
        self.assertIs(found, m)
        not_found = c.findMethod("bar", "I", "V")
        self.assertIsNone(not_found)

    def test_match_field_and_field_call(self):
        f = SmaliField("x", "I", None, None, None)
        self.assertTrue(
            SmaliClass.matchFieldAndFieldCall(f, "Lcom/Foo;->x:I")
        )
        self.assertFalse(
            SmaliClass.matchFieldAndFieldCall(f, "Lcom/Foo;->y:I")
        )

    def test_where_is_field_used(self):
        c = SmaliClass(None)
        c.name = "Lcom/Foo;"
        c.addMethod(self._make_method("<init>", [], "V"))
        f = self._make_field("counter", "I")
        c.addField(f)
        usages = c.whereIsFieldUsed(f)
        self.assertEqual(usages, [])

    def test_determine_parent_class(self):
        project = SmaliProject()
        parent = SmaliClass(None)
        parent.name = "Lcom/Base;"
        project.addClass(parent)
        child = SmaliClass(None)
        child.name = "Lcom/Child;"
        child.parent = project
        child.zuper = "Lcom/Base;"
        found = child.determineParentClass()
        self.assertIs(found, parent)

    def test_determine_parent_class_hierarchy(self):
        project = SmaliProject()
        base = SmaliClass(None)
        base.name = "Lcom/Base;"
        base.zuper = "Ljava/lang/Object;"
        project.addClass(base)
        mid = SmaliClass(None)
        mid.name = "Lcom/Mid;"
        mid.zuper = "Lcom/Base;"
        mid.parent = project
        project.addClass(mid)
        child = SmaliClass(None)
        child.name = "Lcom/Child;"
        child.zuper = "Lcom/Mid;"
        child.parent = project
        hierarchy = child.determineParentClassHierarchy()
        self.assertEqual(len(hierarchy), 2)
        self.assertIs(hierarchy[0], mid)
        self.assertIs(hierarchy[1], base)

    def test_equals_self(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        b = SmaliClass(None)
        b.name = "Lcom/Foo;"
        self.assertTrue(a.equals(b))

    def test_equals_different_name(self):
        a = SmaliClass(None)
        a.name = "Lcom/Foo;"
        b = SmaliClass(None)
        b.name = "Lcom/Bar;"
        self.assertFalse(a.equals(b))


if __name__ == "__main__":
    unittest.main()
