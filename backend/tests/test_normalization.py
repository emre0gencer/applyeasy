"""
Tests for the deterministic normalization layer and the style rules it feeds.

The cases below are taken from the four shipped gallery PDFs, which is where
each defect was actually observed — resume_03's out-of-order experience block,
resume_04's "2021-2023" packed into one date field, the "June 2022" / "Jun 2022"
drift, and the third-person summaries that appeared in all four.
"""

from __future__ import annotations

from backend.src.models.schemas import (
    AwardEntry,
    Bullet,
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    Skill,
    TailoredBullet,
    TailoredExperience,
    BulletChange,
    TailoredResume,
)
from backend.src.normalization.dates import (
    canonicalize_range,
    parse_date,
    range_sort_key,
    split_range,
)
from backend.src.normalization.ordering import (
    normalize_education,
    normalize_experiences,
    normalize_projects,
)
from backend.src.normalization.skills import (
    canonical_category,
    normalize_skills,
    order_skill_groups,
)
from backend.src.validation.style_rules import (
    find_hedges,
    find_repeated_verbs,
    has_third_person_pronoun,
    leading_verb,
    opens_with_name,
)


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

class TestDates:
    def test_month_name_variants_render_identically(self):
        """The exact drift seen in resume_03: 'June 2022' beside 'Jun 2022'."""
        assert parse_date("June 2022").render() == "Jun 2022"
        assert parse_date("Jun 2022").render() == "Jun 2022"
        assert parse_date("Jun. 2022").render() == "Jun 2022"

    def test_numeric_forms_normalize(self):
        assert parse_date("06/2022").render() == "Jun 2022"
        assert parse_date("2022-06").render() == "Jun 2022"

    def test_present_variants(self):
        for token in ("Present", "present", "Current", "now", "ongoing"):
            assert parse_date(token).render() == "Present"

    def test_seasons_keep_their_label(self):
        """Converting 'Summer 2022' to 'Jun 2022' would claim a month the
        candidate never wrote, which the truthfulness rules forbid."""
        assert parse_date("Summer 2022").render() == "Summer 2022"
        assert parse_date("fall 2021").render() == "Fall 2021"
        # ...but it still sorts as if it were the representative month.
        assert parse_date("Summer 2022").sort_key == (2022, 6)

    def test_year_only_and_unparseable(self):
        assert parse_date("2022").render() == "2022"
        assert parse_date("sometime later").render() == "sometime later"
        assert parse_date("").render() == ""

    def test_present_sorts_newest_unknown_sorts_oldest(self):
        assert parse_date("Present").sort_key > parse_date("Dec 2030").sort_key
        assert parse_date("").sort_key < parse_date("Jan 1990").sort_key

    def test_split_range_recovers_packed_field(self):
        """resume_04 shipped a whole range inside the start_date field."""
        assert split_range("2021-2023") == ("2021", "2023")
        assert split_range("Jun 2021 – Aug 2021") == ("Jun 2021", "Aug 2021")
        assert split_range("Jun 2022") is None

    def test_canonicalize_range_unpacks_and_renders(self):
        assert canonicalize_range("2021-2023", None) == ("2021", "2023")
        assert canonicalize_range("June 2022", "Present") == ("Jun 2022", "Present")

    def test_range_sort_key_orders_by_end_then_start(self):
        current = range_sort_key("Jul 2022", "Present")
        older = range_sort_key("Jun 2021", "Aug 2021")
        assert current > older


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

def _exp(role: str, start: str, end: str | None) -> ExperienceEntry:
    return ExperienceEntry(
        company="Co", role_title=role, start_date=start, end_date=end, source_text="s"
    )


class TestOrdering:
    def test_reverse_chronological_fixes_shipped_sample(self):
        """resume_03 rendered Jan 2022 -> Jun 2022 -> Jun 2021."""
        entries = [
            _exp("Equity Research Intern", "Jan 2022", "May 2022"),
            _exp("IB Analyst Intern", "Jun 2022", "Aug 2022"),
            _exp("Earlier Intern", "Jun 2021", "Aug 2021"),
        ]
        ordered = [e.role_title for e in normalize_experiences(entries)]
        assert ordered == ["IB Analyst Intern", "Equity Research Intern", "Earlier Intern"]

    def test_current_role_sorts_first(self):
        entries = [_exp("Old", "Jun 2020", "Aug 2020"), _exp("Current", "Jul 2022", "Present")]
        assert normalize_experiences(entries)[0].role_title == "Current"

    def test_dates_are_canonicalized_in_place(self):
        entries = [_exp("A", "June 2022", "Present"), _exp("B", "06/2020", "12/2020")]
        result = normalize_experiences(entries)
        assert (result[0].start_date, result[0].end_date) == ("Jun 2022", "Present")
        assert (result[1].start_date, result[1].end_date) == ("Jun 2020", "Dec 2020")

    def test_packed_range_is_unpacked_into_two_fields(self):
        result = normalize_experiences([_exp("Packed", "2021-2023", None)])
        assert (result[0].start_date, result[0].end_date) == ("2021", "2023")

    def test_undated_entries_keep_order_and_sort_last(self):
        entries = [_exp("NoDate1", "", None), _exp("Dated", "Jan 2022", "Feb 2022"), _exp("NoDate2", "", None)]
        ordered = [e.role_title for e in normalize_experiences(entries)]
        assert ordered == ["Dated", "NoDate1", "NoDate2"]

    def test_education_orders_most_recent_first(self):
        edus = [
            EducationEntry(institution="Old U", graduation_date="2019", source_text="s"),
            EducationEntry(institution="New U", graduation_date="May 2023", source_text="s"),
        ]
        assert [e.institution for e in normalize_education(edus)] == ["New U", "Old U"]

    def test_projects_dated_first_undated_keep_relevance_order(self):
        projs = [
            ProjectEntry(name="Undated A", description="d", source_text="s"),
            ProjectEntry(name="Old", description="d", date="2021", source_text="s"),
            ProjectEntry(name="New", description="d", date="March 2024", source_text="s"),
            ProjectEntry(name="Undated B", description="d", source_text="s"),
        ]
        assert [p.name for p in normalize_projects(projs)] == [
            "New", "Old", "Undated A", "Undated B",
        ]

    def test_empty_lists_round_trip(self):
        assert normalize_experiences([]) == []
        assert normalize_education([]) == []
        assert normalize_projects([]) == []


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

class TestSkills:
    def test_label_variants_collapse_to_one_category(self):
        for label in ("Languages", "Programming Languages", "programming language"):
            assert canonical_category(label, "Python") == "Languages"

    def test_specific_label_beats_generic_substring(self):
        assert canonical_category("Data Science", "pandas") == "Data & ML"
        assert canonical_category("Web Frameworks", "React") == "Frameworks & Libraries"

    def test_unmappable_label_falls_back_to_skill_lexicon(self):
        assert canonical_category("Miscellaneous Stuff", "Bloomberg Terminal") == "Tools & Platforms"
        assert canonical_category(None, "PyTorch") == "Data & ML"

    def test_unknown_skill_and_label_becomes_other(self):
        assert canonical_category("Wibble", "Fnordling") == "Other"

    def test_normalize_skills_dedupes_case_insensitively(self):
        skills = [
            Skill(name="Python", category="Languages", source_text="s"),
            Skill(name="python", category="Programming Languages", source_text="s"),
            Skill(name="React", category="Frontend", source_text="s"),
        ]
        result = normalize_skills(skills)
        assert [s.name for s in result] == ["Python", "React"]
        assert [s.category for s in result] == ["Languages", "Frameworks & Libraries"]

    def test_group_ordering_is_canonical_with_unknowns_last(self):
        grouped = {"Other": ["x"], "Data & ML": ["pandas"], "Languages": ["Python"], "Wibble": ["y"]}
        assert list(order_skill_groups(grouped)) == ["Languages", "Data & ML", "Other", "Wibble"]

    def test_empty_categories_are_dropped(self):
        assert list(order_skill_groups({"Languages": [], "Other": ["x"]})) == ["Other"]


# ---------------------------------------------------------------------------
# Style rules
# ---------------------------------------------------------------------------

class TestStyleRules:
    def test_leading_verb_skips_bullet_glyphs_and_adverbs(self):
        assert leading_verb("• Designed a schema") == "designed"
        assert leading_verb("Successfully built an API") == "built"
        assert leading_verb("") is None

    def test_repeated_verbs_match_shipped_sample(self):
        """resume_03 opened four bullets with 'Built'."""
        bullets = [
            "Built 3-statement models",
            "Built comparable analyses",
            "Prepared pitch books",
        ]
        assert find_repeated_verbs(bullets) == {"built": 2}

    def test_no_repetition_returns_empty(self):
        assert find_repeated_verbs(["Designed X", "Built Y", "Migrated Z"]) == {}

    def test_hedges_catch_metric_substitutes(self):
        text = "Built a pipeline handling a large volume of daily jobs"
        assert "a large volume of" in find_hedges(text)
        assert find_hedges("Reduced p99 latency from 400ms to 120ms") == []

    def test_common_words_are_not_flagged_as_hedges(self):
        """'multiple'/'several' are too often legitimate to flag."""
        assert find_hedges("Served multiple financial institution clients") == []

    def test_third_person_summary_detection(self):
        summary = "Alex Rivera has experience as a Software Engineer. He brings backend depth."
        assert opens_with_name(summary, "Alex Rivera")
        assert has_third_person_pronoun(summary)

    def test_first_person_implied_summary_passes(self):
        summary = "Backend engineer with three years building payment infrastructure."
        assert not opens_with_name(summary, "Alex Rivera")
        assert not has_third_person_pronoun(summary)


# ---------------------------------------------------------------------------
# Renderer: leadership + awards merge
# ---------------------------------------------------------------------------

def _resume(**overrides) -> TailoredResume:
    base = dict(
        name="Jane Smith",
        summary="Backend engineer.",
        experiences=[
            TailoredExperience(
                company="Co",
                role_title="Engineer",
                start_date="Jan 2022",
                end_date="Present",
                bullets=[
                    TailoredBullet(
                        text="Designed a schema",
                        source_text="s",
                        change=BulletChange(
                            original_text="s", revised_text="Designed a schema",
                            change_reason="unchanged",
                        ),
                    )
                ],
            )
        ],
    )
    base.update(overrides)
    return TailoredResume(**base)


class TestLeadershipAndAwards:
    def test_both_lists_render_when_both_present(self):
        """The template used to render one OR the other, silently dropping awards."""
        from backend.src.rendering.pdf_renderer import _leadership_and_awards

        resume = _resume(
            leadership_items=["President, Robotics Club"],
            awards=[AwardEntry(title="Dean's List", issuer="BU", source_text="s")],
        )
        items = _leadership_and_awards(resume)
        assert [i["kind"] for i in items] == ["text", "award"]

    def test_award_already_named_in_leadership_line_is_dropped(self):
        from backend.src.rendering.pdf_renderer import _leadership_and_awards

        resume = _resume(
            leadership_items=["Dean's List (4 semesters)"],
            awards=[AwardEntry(title="Dean's List", issuer="BU", source_text="s")],
        )
        items = _leadership_and_awards(resume)
        assert len(items) == 1
        assert items[0]["kind"] == "text"

    def test_empty_sections_produce_nothing(self):
        from backend.src.rendering.pdf_renderer import _leadership_and_awards

        assert _leadership_and_awards(_resume()) == []
