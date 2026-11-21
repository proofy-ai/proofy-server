"""사건 토큰(`caseToken`). 서버 로그인 없이 사건을 보호한다(계약 1절 인증)."""

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, Header

from app.db import DbSession
from app.errors import ApiError
from app.models import Case
from app.services.clock import utc_now

TOKEN_PREFIX = "pk_"


def issue_token() -> tuple[str, str]:
    """(토큰 원문, 저장할 해시). 원문은 생성 응답에서 한 번만 준다."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _token_invalid() -> ApiError:
    return ApiError(
        401, "CASE_TOKEN_INVALID", "사건에 접근할 수 없습니다. 처음부터 다시 시작해 주세요."
    )


def _case_not_found() -> ApiError:
    return ApiError(
        404, "CASE_NOT_FOUND", "사건을 찾을 수 없습니다. 삭제됐거나 24시간이 지나 자동 삭제됐어요."
    )


def get_authorized_case(
    case_id: str,
    db: DbSession,
    x_case_token: Annotated[str | None, Header(alias="X-Case-Token")] = None,
) -> Case:
    """라우터용 의존성. 순서: 토큰 없음 401 → 사건 없음·만료 404 → 토큰 불일치 401."""
    if not x_case_token:
        raise _token_invalid()
    case = db.get(Case, case_id)
    if case is None or case.expires_at <= utc_now():
        # 만료 사건의 실제 삭제는 주기 정리(T11)가 한다
        raise _case_not_found()
    if not hmac.compare_digest(case.access_token_hash, hash_token(x_case_token)):
        raise _token_invalid()
    return case


# 라우터 인자 타입: 토큰을 확인한 사건
AuthorizedCase = Annotated[Case, Depends(get_authorized_case)]
