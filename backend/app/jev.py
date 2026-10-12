import math
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from . import budget, store
from .config import config

class ProviderModel(BaseModel):
    model_config = ConfigDict(strict=True)

class Noul(ProviderModel):
    type: Literal["noul"]
    noul: float = Field(ge=0, le=1)

class Choice(ProviderModel):
    type: Literal["choice"]
    choice: str
    confidence: float | None = Field(default=None, ge=0, le=1)

class Usage(ProviderModel):
    input_tokens: int = Field(ge=0)

class DecisionResponse(ProviderModel):
    answers: dict[str, Noul | Choice]
    usage: Usage | None = None

class ProviderError(RuntimeError):
    pass

def decide(state, questions: dict, strict=False):
    if not config.typesafe_key:
        return None
    settings = store.get_settings()
    if not settings.jevMicrosPerMillion or settings.aiPaused or settings.budgetPaused:
        return None
    body = {"model": config.typesafe_model, "state": state, "questions": questions}
    if len(store.encode(body).encode()) > 60000 or len(questions) > 30:
        return None
    reservation = budget.reserve(max(1, math.ceil(65536 * settings.jevMicrosPerMillion / 1000000)))
    if not reservation:
        return None
    try:
        response = httpx.post("https://api.typesafe.ai/v1/systemone", headers={"Authorization": f"Bearer {config.typesafe_key}"}, json=body, timeout=6, follow_redirects=False)
        if not response.is_success:
            raise ProviderError(f"TypeSafe returned HTTP {response.status_code}")
        parsed = DecisionResponse.model_validate(response.json())
        for key, question in questions.items():
            answer = parsed.answers.get(key)
            if answer is None or answer.type != question["type"] or (isinstance(answer, Choice) and answer.choice not in question["criteria"]):
                raise ProviderError("TypeSafe returned an invalid decision.")
        if parsed.usage:
            budget.settle(reservation, max(1, math.ceil(parsed.usage.input_tokens * settings.jevMicrosPerMillion / 1000000)))
        return {key: answer.model_dump() for key, answer in parsed.answers.items()}
    except (httpx.HTTPError, ValueError, ValidationError, ProviderError) as error:
        # Missing or malformed responses may still be billed. Keep their full reservation.
        if strict:
            raise ProviderError(str(error) if isinstance(error, ProviderError) else "TypeSafe response unavailable or invalid.") from None
        return None
