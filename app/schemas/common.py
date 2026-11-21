from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """요청·응답 기본 모델. 파이썬에서는 snake_case, JSON에서는 camelCase(계약 1절)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
