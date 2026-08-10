from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InterviewPrepResult(Base):
    __tablename__ = "interview_preps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_posting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job_postings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    prep_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<InterviewPrepResult id={self.id} job_posting_id={self.job_posting_id}>"


class CoverLetterResult(Base):
    __tablename__ = "cover_letters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_posting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job_postings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    letter_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<CoverLetterResult id={self.id} job_posting_id={self.job_posting_id}>"
