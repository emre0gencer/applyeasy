"""
Tests for the RenderCV/Typst rendering path.

The adapter tests cover the four mapping bugs the head-to-head content-parity
check caught, each of which produced silently wrong output rather than an error:
lone dates rendering as "May 2022 - present", skills bypassing canonical
categories, "4 years 2 months" time spans, and inconsistent month abbreviations.

The render tests actually compile PDFs through Typst, so they are slower than
the rest of the suite and are marked `slow`.
"""

from __future__ import annotations

import pytest

from backend.src.models.schemas import (
    AwardEntry, Bullet, BulletChange, EducationEntry, ProjectEntry, Skill,
    TailoredBullet, TailoredExperience, TailoredResume,
)
from backend.src.rendering.rendercv_renderer import (
    BASE_DESIGN, FIT_LADDER, FLOOR_RUNG, LOCALE,
    _exact_date, _point_date, _range_dates, _valid_email,
    build_sections, deep_merge, trim_once,
)


def _bullet(text: str, score: float = 0.5) -> TailoredBullet:
    return TailoredBullet(
        text=text, source_text=text, relevance_score=score,
        change=BulletChange(original_text=text, revised_text=text,
                            change_reason="unchanged"),
    )


def _resume(**overrides) -> TailoredResume:
    base = dict(
        name="Alex Rivera",
        email="alex@example.com",
        summary="Backend engineer building payment infrastructure.",
        experiences=[
            TailoredExperience(
                company="PayCore", role_title="Software Engineer",
                start_date="Jul 2022", end_date="Present",
                bullets=[_bullet("Designed PostgreSQL schemas.")],
            )
        ],
    )
    base.update(overrides)
    return TailoredResume(**base)


class TestDateMapping:
    def test_exact_dates_use_rendercv_iso_format(self):
        assert _exact_date("Jun 2022") == "2022-06"
        assert _exact_date("June 2022") == "2022-06"
        assert _exact_date("2022") == "2022"
        assert _exact_date("Present") == "present"

    def test_seasons_and_junk_fall_back_to_free_text(self):
        """RenderCV rejects anything that is not YYYY / YYYY-MM / YYYY-MM-DD."""
        assert _exact_date("Summer 2022") is None
        assert _exact_date("whenever") is None
        assert _exact_date(None) is None

    def test_range_needs_both_endpoints(self):
        assert _range_dates("Jun 2022", "Aug 2023") == {
            "start_date": "2022-06", "end_date": "2023-08",
        }

    def test_lone_date_never_becomes_an_open_range(self):
        """A graduation date in start_date rendered as 'May 2022 - present'."""
        assert _range_dates("May 2022", None) == {"date": "May 2022"}
        assert _point_date("May 2022") == {"date": "May 2022"}
        assert _point_date(None) == {}

    def test_season_range_degrades_to_readable_text(self):
        assert _range_dates("Summer 2022", "Fall 2022") == {
            "date": "Summer 2022 - Fall 2022"
        }


class TestSectionMapping:
    def test_summary_is_a_text_entry(self):
        sections = build_sections(_resume())
        assert sections["Summary"] == ["Backend engineer building payment infrastructure."]

    def test_skills_use_canonical_categories(self):
        """The adapter must not bypass normalize_skills the way the spike did."""
        resume = _resume(skills=[
            Skill(name="Python", category="Programming Languages", source_text="s"),
            Skill(name="React", category="Frontend", source_text="s"),
            Skill(name="Docker", category="DevOps", source_text="s"),
        ])
        labels = [entry["label"] for entry in build_sections(resume)["Technical Skills"]]
        assert labels == ["Languages", "Frameworks & Libraries", "Tools & Platforms"]

    def test_experience_highlights_carry_bullet_text(self):
        sections = build_sections(_resume())
        assert sections["Experience"][0]["highlights"] == ["Designed PostgreSQL schemas."]

    def test_education_details_become_highlights(self):
        resume = _resume(education=[EducationEntry(
            institution="BU", degree="B.S.", field_of_study="CS",
            graduation_date="May 2022", gpa="3.8",
            honors=["Dean's List"], coursework="Algorithms", source_text="s",
        )])
        entry = build_sections(resume)["Education"][0]
        assert entry["highlights"] == [
            "GPA: 3.8", "Dean's List", "Relevant Coursework: Algorithms",
        ]
        assert entry["date"] == "May 2022"

    def test_awards_and_leadership_merge_without_duplicates(self):
        resume = _resume(
            leadership_items=["Dean's List (4 semesters)"],
            awards=[AwardEntry(title="Dean's List", issuer="BU", source_text="s")],
        )
        assert len(build_sections(resume)["Leadership & Awards"]) == 1

    def test_both_render_when_distinct(self):
        resume = _resume(
            leadership_items=["President, ACM Chapter"],
            awards=[AwardEntry(title="Dean's List", issuer="BU", source_text="s")],
        )
        assert len(build_sections(resume)["Leadership & Awards"]) == 2

    def test_empty_sections_are_omitted_entirely(self):
        # TailoredResume.summary is a plain str — absent means empty, not None.
        sections = build_sections(_resume(summary=""))
        assert "Summary" not in sections
        assert "Education" not in sections


class TestEmailGuard:
    def test_malformed_email_is_dropped_not_rendered(self):
        """RenderCV validates emails; a bad one would fail the whole render."""
        assert _valid_email("not an email") is None
        assert _valid_email("") is None
        assert _valid_email("a@b.co") == "a@b.co"


class TestDesignDefaults:
    def test_cv_conventions_are_off(self):
        assert BASE_DESIGN["page"]["show_footer"] is False
        assert BASE_DESIGN["page"]["show_top_note"] is False
        assert BASE_DESIGN["sections"]["show_time_spans_in"] == []

    def test_month_abbreviations_are_uniform_width(self):
        """RenderCV ships 'Jan'/'June'/'Sept' — reintroducing date drift."""
        assert all(len(m) == 3 for m in LOCALE["month_abbreviations"])

    def test_ladder_never_shrinks_the_name(self):
        """The old engine scaled the name from 17pt to 13.13pt along with body."""
        for _rung, patch in FIT_LADDER:
            assert "name" not in patch.get("typography", {}).get("font_size", {})

    def test_ladder_floor_is_9pt(self):
        floor_patch = FIT_LADDER[-1][1]
        assert floor_patch["typography"]["font_size"]["body"] == "9pt"
        assert FIT_LADDER[-1][0] == FLOOR_RUNG


class TestDeepMerge:
    def test_patch_overrides_only_named_keys(self):
        merged = deep_merge(BASE_DESIGN, {"typography": {"line_spacing": "0.4em"}})
        assert merged["typography"]["line_spacing"] == "0.4em"
        assert merged["typography"]["font_size"]["body"] == "10pt"   # untouched

    def test_base_is_not_mutated(self):
        before = BASE_DESIGN["page"]["top_margin"]
        deep_merge(BASE_DESIGN, {"page": {"top_margin": "0.1in"}})
        assert BASE_DESIGN["page"]["top_margin"] == before


class TestTrimming:
    def test_projects_go_before_bullets(self):
        resume = _resume(projects=[
            ProjectEntry(name="A", description="d", source_text="s"),
            ProjectEntry(name="B", description="d", source_text="s"),
        ])
        trimmed, what = trim_once(resume)
        assert [p.name for p in trimmed.projects] == ["A"]
        assert "project 'B'" in what

    def test_lowest_relevance_bullet_is_the_one_dropped(self):
        resume = _resume(experiences=[TailoredExperience(
            company="C", role_title="Engineer", start_date="2022", end_date="2023",
            bullets=[_bullet("keep high", 0.9), _bullet("drop me", 0.1),
                     _bullet("keep mid", 0.5)],
        )])
        trimmed, what = trim_once(resume)
        texts = [b.text for b in trimmed.experiences[0].bullets]
        assert texts == ["keep high", "keep mid"]
        assert "lowest-relevance" in what

    def test_last_project_and_two_bullets_are_protected(self):
        resume = _resume(
            projects=[ProjectEntry(name="only", description="d", source_text="s")],
            experiences=[TailoredExperience(
                company="C", role_title="Engineer", start_date="2022", end_date="2023",
                bullets=[_bullet("a"), _bullet("b")],
            )],
        )
        assert trim_once(resume) is None

    def test_trimming_does_not_mutate_the_input(self):
        resume = _resume(projects=[
            ProjectEntry(name="A", description="d", source_text="s"),
            ProjectEntry(name="B", description="d", source_text="s"),
        ])
        trim_once(resume)
        assert len(resume.projects) == 2


# ── Real Typst compilation (slow) ───────────────────────────────────────────

pytest.importorskip("rendercv", reason="rendercv not installed")
pytest.importorskip("typst", reason="typst not installed")


@pytest.mark.slow
class TestRealRender:
    def _measure(self, pdf_bytes: bytes) -> dict:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        sizes: dict[float, int] = {}
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if span["text"].strip():
                        key = round(span["size"], 2)
                        sizes[key] = sizes.get(key, 0) + len(span["text"].strip())
        pages, text = len(doc), page.get_text()
        doc.close()
        return {"pages": pages, "body": max(sizes, key=sizes.get),
                "max": max(sizes), "text": text}

    def test_typical_resume_renders_once_at_full_size(self, tmp_path):
        from backend.src.rendering.rendercv_renderer import render_fitted

        resume = _resume(
            education=[EducationEntry(institution="BU", degree="B.S.",
                                      graduation_date="May 2022", source_text="s")],
            skills=[Skill(name="Python", category="Languages", source_text="s")],
        )
        result = render_fitted(resume, tmp_path)
        metrics = self._measure(result.pdf_bytes)

        assert result.fitted and result.rung == "baseline"
        assert result.renders == 1          # fast path: no re-render
        assert result.trims == []
        assert metrics["pages"] == 1
        assert metrics["body"] == 10.0      # full size, not shrunk to fit

    def test_oversized_resume_trims_instead_of_shrinking_below_floor(self, tmp_path):
        from backend.src.rendering.rendercv_renderer import render_fitted

        pad = (" Delivered the work end to end with schema validation, integration "
               "testing, staged rollout across three environments, structured logging, "
               "alerting runbooks, and a documented rollback path reviewed by the "
               "platform team before release, with dashboards and on-call handover "
               "notes maintained for every downstream consumer of the service.")
        resume = _resume(
            experiences=[
                TailoredExperience(
                    company=f"Company {i}", role_title=f"Engineer {i}",
                    start_date=f"Jul 20{22 - i}",
                    end_date="Present" if i == 0 else f"Aug 20{22 - i}",
                    bullets=[_bullet(f"Designed schemas and caching.{pad}", 0.9),
                             _bullet(f"Built idempotent REST APIs.{pad}", 0.7),
                             _bullet(f"Maintained job pipelines.{pad}", 0.2)],
                ) for i in range(5)
            ],
            projects=[ProjectEntry(name=f"Project {i}", description="d",
                                   bullets=[Bullet(text=f"Built a ledger.{pad}",
                                                   source_text="s")],
                                   source_text="s") for i in range(4)],
        )
        result = render_fitted(resume, tmp_path)
        metrics = self._measure(result.pdf_bytes)

        assert metrics["pages"] == 1
        assert result.trims, "should have trimmed content rather than overflow"
        # The whole point: body bottoms out at the 9pt floor and the name never
        # shrinks. xhtml2pdf rendered this same input at 6.95pt body / 13.13pt name.
        assert metrics["body"] >= 9.0
        assert metrics["max"] == 20.0
        assert result.renders < 15          # O(trims + rungs), not O(trims x rungs)
