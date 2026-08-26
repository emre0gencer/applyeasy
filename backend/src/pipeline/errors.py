"""Expected pipeline failures that can be reported without a traceback leak."""


class PipelineStageError(RuntimeError):
    """A generation stage returned unusable structured data."""

    public_message = "Generation could not complete. Please try again."


class ProfileExtractionError(PipelineStageError):
    public_message = (
        "We couldn't extract usable profile information. Add at least one role, "
        "project, education entry, or skill and try again."
    )


class JobAnalysisError(PipelineStageError):
    public_message = (
        "We couldn't analyze that job description. Paste the complete posting "
        "and try again."
    )
