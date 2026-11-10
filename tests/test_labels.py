"""Tests for regtrace.labels: markers, levels, definitions and fallbacks."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from regtrace.labels import label_paragraphs


def _labels(xml: str) -> list[tuple[str, str]]:
    return [(paragraph.label, paragraph.text) for paragraph in label_paragraphs(ET.fromstring(xml))]


def _ladder(tail: str) -> list[tuple[str, str]]:
    """Label (a)..(g), a headed (h), a nested (1), then one final paragraph."""
    steps = "".join(f"<P>({letter}) {letter.upper()}.</P>" for letter in "abcdefg")
    body = f"{steps}<P>(h)<I>Eighth heading.</I> Text.</P><P>(1) One.</P>{tail}"
    return _labels(f"<DIV8>{body}</DIV8>")


class LabelTests(unittest.TestCase):
    def test_nested_levels(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) First.</P>
              <P>(b) Second.</P>
              <P>(1) One.</P>
              <P>(2) Two.</P>
              <P>(i) Roman one.</P>
              <P>(ii) Roman two.</P>
              <P>(A) Upper.</P>
              <P>(B) Upper two.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            [label for label, _ in labels],
            ["(a)", "(b)", "(b)(1)", "(b)(2)", "(b)(2)(i)", "(b)(2)(ii)", "(b)(2)(ii)(A)", "(b)(2)(ii)(B)"],
        )
        self.assertEqual(labels[2], ("(b)(1)", "(1) One."))

    def test_chained_markers(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) A.</P>
              <P>(b) B.</P>
              <P>(c) C.</P>
              <P>(d)(1) Chained.</P>
            </DIV8>
            """
        )
        self.assertEqual(len(labels), 4)
        self.assertEqual(labels[-1], ("(d)(1)", "(d)(1) Chained."))

    def test_repeated_printed_label_falls_back_to_unique_unlabeled(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) First.</P>
              <P>(a) Second.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            [label for label, _ in labels],
            ["(a)", "(a)~1"],
        )

    def test_marker_chain_that_does_not_fit_is_unlabeled(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a)(2) Not a valid chain.</P>
            </DIV8>
            """
        )
        self.assertEqual(labels, [("~1", "(a)(2) Not a valid chain.")])

    def test_inline_split_with_dash(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) Intro.</P>
              <P>(b) <I>Provider-specific network adequacy standards.</I>-(1) <I>Provider types.</I> At a minimum.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [
                ("(a)", "(a) Intro."),
                ("(b)", "(b) Provider-specific network adequacy standards."),
                ("(b)(1)", "(1) Provider types. At a minimum."),
            ],
        )

    def test_inline_split_with_spaced_dash(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) Intro.</P>
              <P>(b) <I>Provider-specific network adequacy standards.</I> - (1) <I>Provider types.</I> At a minimum.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [
                ("(a)", "(a) Intro."),
                ("(b)", "(b) Provider-specific network adequacy standards."),
                ("(b)(1)", "(1) Provider types. At a minimum."),
            ],
        )

    def test_inline_split_with_em_dash(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) Intro.</P>
              <P>(b) <I>Provider-specific network adequacy standards.</I>—(1) <I>Provider types.</I> At a minimum.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [
                ("(a)", "(a) Intro."),
                ("(b)", "(b) Provider-specific network adequacy standards."),
                ("(b)(1)", "(1) Provider types. At a minimum."),
            ],
        )

    def test_inline_split_without_dash(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) Intro.</P>
              <P>(b) <I>Development of network adequacy standards.</I> (1) States developing standards.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [
                ("(a)", "(a) Intro."),
                ("(b)", "(b) Development of network adequacy standards."),
                ("(b)(1)", "(1) States developing standards."),
            ],
        )

    def test_inline_split_with_italic_marker_after_italic_run_is_unlabeled(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) A.</P>
              <P>(b) <I>Heading text.</I><I>(1)</I> <I>Child heading.</I> Body.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [
                ("(a)", "(a) A."),
                ("(b)", "(b) Heading text."),
                ("(b)~1", "(1) Child heading. Body."),
            ],
        )

    def test_italic_marker_at_level_four_is_a_marker(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) A.</P>
              <P>(1) One.</P>
              <P>(i) Roman.</P>
              <P>(A) Upper.</P>
              <P>(<I>1</I>) Italic digit.</P>
            </DIV8>
            """
        )
        self.assertEqual(labels[-1][0], "(a)(1)(i)(A)(1)")

    def test_italic_marker_forms(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) A.</P>
              <P>(1) One.</P>
              <P>(i) Roman.</P>
              <P>(A) Upper.</P>
              <P>(<I>1</I>) Italic digit.</P>
              <P><I>(i)</I> Italic roman.</P>
              <P>(<I>ii</I>) Italic roman two.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            [label for label, _ in labels],
            [
                "(a)",
                "(a)(1)",
                "(a)(1)(i)",
                "(a)(1)(i)(A)",
                "(a)(1)(i)(A)(1)",
                "(a)(1)(i)(A)(1)(i)",
                "(a)(1)(i)(A)(1)(ii)",
            ],
        )
        self.assertEqual(labels[-1][1], "(ii) Italic roman two.")

    def test_definition_stack(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) Standard.</P>
              <P><I>Abuse</I> means ...</P>
              <P>(1) First child.</P>
              <P>(i) Roman child.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [
                ("(a)", "(a) Standard."),
                ("(a)def:Abuse", "Abuse means ..."),
                ("(a)def:Abuse(1)", "(1) First child."),
                ("(a)def:Abuse(1)(i)", "(i) Roman child."),
            ],
        )

    def test_multiword_definition_term_keeps_spaces_and_parentheses(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P><I>Prepaid inpatient health plan (PIHP)</I> means an entity.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [("def:Prepaid inpatient health plan (PIHP)", "Prepaid inpatient health plan (PIHP) means an entity.")],
        )

    def test_definition_first_child_can_chain(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P><I>Health insuring organization (HIO)</I> means an entity.</P>
              <P>(3)(i) Text.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [
                (
                    "def:Health insuring organization (HIO)",
                    "Health insuring organization (HIO) means an entity.",
                ),
                ("def:Health insuring organization (HIO)(3)(i)", "(3)(i) Text."),
            ],
        )

    def test_failed_definition_falls_back_to_main_stack(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) Intro.</P>
              <P><I>Term</I> means.</P>
              <P>(1) Child.</P>
              <P>(b) Back.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [
                ("(a)", "(a) Intro."),
                ("(a)def:Term", "Term means."),
                ("(a)def:Term(1)", "(1) Child."),
                ("(b)", "(b) Back."),
            ],
        )

    def test_unlabeled_paragraphs(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>Opening text.</P>
              <P>(a) Labeled.</P>
              <P>More text.</P>
              <P>Even more.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [
                ("~1", "Opening text."),
                ("(a)", "(a) Labeled."),
                ("(a)~1", "More text."),
                ("(a)~2", "Even more."),
            ],
        )
        self.assertEqual(len({label for label, _ in labels}), len(labels))

    def test_invalid_marker_is_text(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(ILOS) Not a marker.</P>
            </DIV8>
            """
        )
        self.assertEqual(labels, [("~1", "(ILOS) Not a marker.")])

    def test_acronym_in_a_definition_is_not_a_marker(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P><I>Prepaid inpatient health plan (PIHP)</I> means an entity.</P>
            </DIV8>
            """
        )
        self.assertEqual(labels[0][0], "def:Prepaid inpatient health plan (PIHP)")

    def test_whitespace_and_entities(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>  (a)   First
                     line &amp; more.  </P>
            </DIV8>
            """
        )
        self.assertEqual(labels, [("(a)", "(a) First line & more.")])

    def test_headed_paragraph(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a)<I> Definitions.</I> Text.</P>
              <P>(b)<I> More.</I> Text.</P>
            </DIV8>
            """
        )
        self.assertEqual(
            labels,
            [
                ("(a)", "(a) Definitions. Text."),
                ("(b)", "(b) More. Text."),
            ],
        )

    def test_fp_paragraphs_are_labeled(self) -> None:
        labels = _labels(
            """
            <DIV8>
              <P>(a) First.</P>
              <FP>(b) Flush paragraph.</FP>
            </DIV8>
            """
        )
        self.assertEqual(labels, [("(a)", "(a) First."), ("(b)", "(b) Flush paragraph.")])

    def test_headed_continuation_beats_opening_a_deeper_level(self) -> None:
        labels = _ladder("<P>(i)<I>Ninth heading.</I> Text.</P>")
        self.assertEqual([label for label, _ in labels][-3:], ["(h)", "(h)(1)", "(i)"])

    def test_unheaded_marker_opens_the_deeper_level(self) -> None:
        labels = _ladder("<P>(i) Plain text.</P>")
        self.assertEqual(labels[-1], ("(h)(1)(i)", "(i) Plain text."))


if __name__ == "__main__":
    unittest.main()
