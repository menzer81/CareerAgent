from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ResumePlanResult(Base):
    """Persisted output of the resume strategy/generation pipeline for a job posting."""

    __tablename__ = "resume_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_posting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job_postings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    plan_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<ResumePlanResult id={self.id} job_posting_id={self.job_posting_id}>"
