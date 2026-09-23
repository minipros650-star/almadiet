"""UserFiles ORM model — metadata for objects in Supabase Storage.

Only object paths and metadata live in Postgres; the bytes live in Storage.
Never store permanent signed URLs here.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, GUID


class UserFile(Base):
    __tablename__ = "user_files"
    __table_args__ = (UniqueConstraint("bucket", "object_path", name="uq_user_files_path"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    bucket: Mapped[str] = mapped_column(String(50), nullable=False)
    object_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UserFile {self.bucket}/{self.object_path}>"
