"""T18 배포 설정(계약 테스트 아님)."""

import pytest

from app.db import normalize_database_url


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgresql://u:p@ep-x.ap-southeast-1.aws.neon.tech/db?sslmode=require",
            "postgresql+psycopg://u:p@ep-x.ap-southeast-1.aws.neon.tech/db?sslmode=require",
        ),
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("sqlite:///./proofy.sqlite3", "sqlite:///./proofy.sqlite3"),
    ],
)
def test_normalize_database_url(given, expected):
    assert normalize_database_url(given) == expected
