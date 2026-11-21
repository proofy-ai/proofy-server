"""서버 시각. DB에는 시간대 없이 UTC로 저장한다(`docs/erd.md` 머리말)."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    # 응답이 초 단위라 저장도 초 단위로 맞춘다
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)
