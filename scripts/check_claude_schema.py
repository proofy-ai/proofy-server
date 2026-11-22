"""실제 Claude API가 대조 요청의 도구·출력 스키마를 받아들이는지 확인한다(이슈 #71).

가짜 SDK 테스트로는 API의 스키마 복잡도 한도(400 "compiled grammar is too large")를 잡을 수 없다.
`compare.TOOLS`·`OUTPUT_SCHEMA`·`SYSTEM_PROMPT`를 바꾼 뒤, 그리고 배포 전에 한 번 돌린다.
짧은 응답 한 번이라 비용은 1센트 안팎이다. 키는 `.env`나 환경변수 `ANTHROPIC_API_KEY`에서 읽는다.

사용: uv run python -m scripts.check_claude_schema
"""

import sys
import time

from app.agent.compare import OUTPUT_SCHEMA, SYSTEM_PROMPT, TOOLS
from app.agent.llm import ClaudeClient, Deadline, user_text
from app.agent.masking import mask_text
from app.agent.steps import AgentError, AgentRefused
from app.config import Settings

# 답을 끝까지 받을 필요는 없다. 요청이 받아들여지는지만 본다
CHECK_MAX_TOKENS = 16


def main() -> int:
    settings = Settings()
    try:
        client = ClaudeClient(
            settings.anthropic_api_key,
            settings.anthropic_model,
            settings.anthropic_effort,
            Deadline(time.monotonic() + 60),
        )
        message = mask_text("스키마 확인용 요청입니다. 짧게 답하세요.")
        client.turn(
            SYSTEM_PROMPT,
            TOOLS,
            OUTPUT_SCHEMA,
            [{"role": "user", "content": [user_text(message)]}],
            max_tokens=CHECK_MAX_TOKENS,
        )
    except AgentRefused:
        # 출력 한도(16토큰)에서 끊긴 것도 여기로 온다. 요청 자체는 받아들여졌다
        pass
    except AgentError as exc:
        print(f"실패: {exc.message} (자세한 원인은 위 로그의 'Claude 요청 실패')")
        return 1
    print(f"통과: 모델 {settings.anthropic_model}이 대조 요청 스키마를 받아들였습니다.")
    return 0


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())
