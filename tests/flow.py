"""여러 테스트가 같이 쓰는 API 흐름(T23부터). 샘플 사건 만들기, 분석을 돌려 끝날 때까지 기다리기."""

import time
from typing import Any

API = "/api/v1"


def sample(client, scenario: str = "GOODS") -> tuple[str, dict[str, str]]:
    body = client.post(f"{API}/cases/sample", json={"scenario": scenario}).json()
    return body["caseId"], {"X-Case-Token": body["caseToken"]}


def start(client, case_id: str, auth: dict[str, str], body: dict[str, Any] | None = None):
    return client.post(f"{API}/cases/{case_id}/analysis-runs", json=body or {}, headers=auth)


def wait(client, case_id: str, auth: dict[str, str], run_id: str) -> dict[str, Any]:
    end = time.monotonic() + 60
    while time.monotonic() < end:
        run = client.get(f"{API}/cases/{case_id}/analysis-runs/{run_id}", headers=auth).json()
        if run["status"] != "RUNNING":
            return run
        time.sleep(0.02)
    raise AssertionError("분석이 끝나지 않았습니다")


def run(client, case_id: str, auth: dict[str, str], body: dict[str, Any] | None = None):
    res = start(client, case_id, auth, body)
    assert res.status_code == 202, res.text
    return wait(client, case_id, auth, res.json()["runId"])
