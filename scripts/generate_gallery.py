"""
generate_gallery.py
───────────────────
Generates real ApplyEasy resume outputs for the landing-page gallery.

Runs the full pipeline (LLM included) for 4 high-fit profile/job pairs,
renders PDFs, converts first pages to PNG previews, and writes
frontend/public/gallery/manifest.json.

Usage (from repo root):
    cd /path/to/applyeasy
    python -m scripts.generate_gallery
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from pathlib import Path

# ── Load .env so GROQ_API_KEY is available ──────────────────────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

# ── Add repo root to path ────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── Pipeline imports ─────────────────────────────────────────────────────────
from backend.src.analysis.job_description_analyzer import analyze_job_description
from backend.src.extraction.candidate_profile_builder import build_candidate_profile
from backend.src.generation.resume_tailoring_engine import tailor_resume
from backend.src.ingestion.document_ingestion_engine import ingest_text
from backend.src.matching.relevance_ranker import rank_relevance
from backend.src.models.schemas import TailoredCoverLetter
from backend.src.rendering.pdf_renderer import render_resume_pdf
from backend.src.validation.quality_validator import compute_raw_suitability_v2

# ── Directories ───────────────────────────────────────────────────────────────
PROFILES_DIR = ROOT / "test_profiles"
JOBS_DIR     = ROOT / "test_jobs"
OUTPUTS_DIR  = ROOT / "outputs"
GALLERY_DIR  = ROOT / "frontend" / "public" / "gallery"
GALLERY_DIR.mkdir(parents=True, exist_ok=True)

# ── Gallery entries ───────────────────────────────────────────────────────────
# Each entry: (profile_file, job_file, display_name, job_one_liner, template_id)
GALLERY_ENTRIES = [
    (
        "gallery_01_swe_demo.txt",
        "01_software_engineer_backend.txt",
        "Alex Rivera",
        "Backend Software Engineer at Meridian Financial Technology",
        "classic",
    ),
    (
        "gallery_02_datasci_demo.txt",
        "02_data_scientist_healthcare.txt",
        "Sophie Chen",
        "Data Scientist — Clinical Analytics at Veridia Health",
        "polished",
    ),
    (
        "gallery_03_finance_demo.txt",
        "03_investment_banking_analyst.txt",
        "Michael Torres",
        "Investment Banking Analyst, TMT Group at Caldwell & Wren",
        "traditional",
    ),
    (
        "gallery_04_pm_demo.txt",
        "13_product_manager.txt",
        "Jasmine Park",
        "Associate Product Manager at Looper (B2B SaaS)",
        "polished",
    ),
]


def run_pipeline_direct(raw_text: str, job_text: str) -> tuple[int, int, object]:
    """Run the core pipeline steps and return (raw_score, display_score, tailored_resume)."""
    from backend.src.models.schemas import TailoredCoverLetter
    from backend.src.validation.quality_validator import validate

    doc = ingest_text(raw_text)
    profile = build_candidate_profile(doc)
    jd = analyze_job_description(job_text)
    relevance_map = rank_relevance(profile, jd)
    raw_score, score_breakdown = compute_raw_suitability_v2(profile, jd, relevance_map)
    tailored = tailor_resume(profile, jd, relevance_map, raw_score=raw_score)

    # Run validation to get post-tailoring keyword_coverage
    validation = validate(tailored, TailoredCoverLetter(), profile, jd, score_breakdown=score_breakdown)

    # Mirror the frontend computeSuitabilityScore formula exactly
    kw_coverage  = validation.keyword_coverage
    exp_depth    = min(len(profile.experiences) / 3.0, 1.0)
    clarity      = profile.extraction_confidence
    base         = kw_coverage * 50 + exp_depth * 25 + clarity * 25
    severe_flags = sum(
        1 for f in validation.flags
        if "truthfulness" in f.lower() or "fabricat" in f.lower()
    )
    uncapped     = max(0, min(100, round(base - severe_flags * 10)))
    if raw_score < 55:
        display_score = min(uncapped, 70)
    else:
        display_score = min(uncapped, raw_score + 35)

    return raw_score, display_score, tailored


def pdf_first_page_to_png(pdf_path: Path, png_path: Path, scale: float = 2.0) -> None:
    """Rasterize the first page of a PDF to a PNG image."""
    import fitz  # PyMuPDF
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    pix.save(str(png_path))
    doc.close()


def generate_entry(
    idx: int,
    profile_file: str,
    job_file: str,
    display_name: str,
    job_one_liner: str,
    template_id: str,
) -> dict:
    print(f"\n[{idx+1}/4] {display_name} — {job_one_liner}")

    raw_text  = (PROFILES_DIR / profile_file).read_text(encoding="utf-8")
    job_text  = (JOBS_DIR / job_file).read_text(encoding="utf-8")

    print("  Running pipeline…")
    raw_score, display_score, tailored = run_pipeline_direct(raw_text, job_text)

    # Override display name so the PDF shows the gallery persona, not the raw profile name
    tailored.name = display_name

    run_id   = f"gallery_{idx+1:02d}"
    pdf_path = Path(render_resume_pdf(tailored, run_id, template_id))
    print(f"  PDF rendered → {pdf_path}  (raw={raw_score}, display={display_score})")

    # Copy PDF to gallery dir
    dest_pdf = GALLERY_DIR / f"resume_{idx+1:02d}.pdf"
    shutil.copy2(pdf_path, dest_pdf)

    # Convert first page to PNG
    dest_png = GALLERY_DIR / f"resume_{idx+1:02d}.png"
    pdf_first_page_to_png(dest_pdf, dest_png, scale=2.5)
    print(f"  Preview PNG → {dest_png}")

    return {
        "id":      idx + 1,
        "name":    display_name,
        "job":     job_one_liner,
        "score":   display_score,
        "pdf":     f"/gallery/resume_{idx+1:02d}.pdf",
        "preview": f"/gallery/resume_{idx+1:02d}.png",
    }


def main() -> None:
    manifest = []
    for idx, (profile_file, job_file, display_name, job_one_liner, template_id) in enumerate(GALLERY_ENTRIES):
        try:
            entry = generate_entry(idx, profile_file, job_file, display_name, job_one_liner, template_id)
            manifest.append(entry)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            raise

    manifest_path = GALLERY_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n✓ manifest.json written to {manifest_path}")
    print("\nGallery entries:")
    for e in manifest:
        print(f"  [{e['id']}] {e['name']:18s}  score={e['score']:3d}  {e['job']:60s}")


if __name__ == "__main__":
    main()
