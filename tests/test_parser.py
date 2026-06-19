from app.parsing.pdf_parser import split_sections

SAMPLE = """
Indian Penal Code

302. Punishment for murder
Whoever commits murder shall be punished with death, or imprisonment for life, and shall also be liable to fine.
Provided that the sentence shall be recorded with reasons.
Explanation. Murder is defined in section 300.

420. Cheating and dishonestly inducing delivery of property
(1) Whoever cheats and dishonestly induces delivery of property shall be punished.
(a) imprisonment up to seven years
(b) fine
"""


def test_splits_sections():
    doc = split_sections(SAMPLE, title="IPC")
    numbers = [s.number for s in doc.sections]
    assert "302" in numbers and "420" in numbers


def test_preserves_hierarchy():
    doc = split_sections(SAMPLE, title="IPC")
    s302 = next(s for s in doc.sections if s.number == "302")
    assert s302.provisos, "proviso not captured"
    assert s302.explanations, "explanation not captured"

    s420 = next(s for s in doc.sections if s.number == "420")
    labels = {sc.label for sc in s420.subclauses}
    assert {"1", "a", "b"} <= labels


def test_full_text_roundtrip():
    doc = split_sections(SAMPLE, title="IPC")
    s302 = next(s for s in doc.sections if s.number == "302")
    assert "murder" in s302.full_text().lower()
