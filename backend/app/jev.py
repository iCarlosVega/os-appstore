import json
from typing import Annotated, Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from . import budget, db, discord, store
from .config import config

# Current documented Jev input window; review this bound and pricing when changing models.
MAX_INPUT_TOKENS = 65536
SUPPORTED_MODELS = {"jev-1.13.0", "jev-latest", "jev-preview"}
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]

class ProviderModel(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)

class Noul(ProviderModel):
    type: Literal["noul"]
    noul: Probability

class Choice(ProviderModel):
    type: Literal["choice"]
    choice: str
    confidence: Probability | None = None
    probabilities: dict[str, Probability] | None = None

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
    if not settings.jevMicrosPerMillion or settings.hostingMicros is None or settings.aiPaused or settings.budgetPaused:
        return None
    try:
        if config.typesafe_model not in SUPPORTED_MODELS:
            raise ProviderError("Review the input cost bound before enabling this TypeSafe model.")
        if not isinstance(state, (str, dict, list)) or not isinstance(questions, dict) or not 1 <= len(questions) <= 30:
            raise ProviderError("TypeSafe requires state and 1 to 30 typed questions.")
        for key, question in questions.items():
            if not isinstance(key, str) or not key or not isinstance(question, dict) or question.get("type") not in ("noul", "choice") or not isinstance(question.get("instructions"), (str, dict, list)):
                raise ProviderError("TypeSafe question is invalid.")
            criteria = question.get("criteria")
            if question["type"] == "choice" or criteria is not None:
                if not isinstance(criteria, dict) or not criteria or any(not isinstance(k, str) or not k or (v is not None and not isinstance(v, (str, dict, list))) for k, v in criteria.items()):
                    raise ProviderError("TypeSafe criteria are invalid.")
                if (question["type"] == "choice" and len(criteria) > 255) or (question["type"] == "noul" and not set(criteria) <= {"true", "false"}):
                    raise ProviderError("TypeSafe criteria are incompatible with the question type.")
        body = json.dumps({"model": config.typesafe_model, "state": state, "questions": questions}, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        if len(body) > 60000:
            raise ProviderError("TypeSafe request exceeds the 60000-byte limit.")
        # Validate against the same immutable snapshot that is sent to the provider.
        questions = json.loads(body)["questions"]
        with db.transaction():
            settings = store.get_settings()
            rate = settings.jevMicrosPerMillion
            if not rate:
                return None
            reservation, notice = budget._reserve((MAX_INPUT_TOKENS * rate + 999999) // 1000000, settings)
        if notice:
            discord.deliver(notice)
        if not reservation:
            return None
        response = httpx.post("https://api.typesafe.ai/v1/systemone", headers={"Authorization": f"Bearer {config.typesafe_key}", "Content-Type": "application/json"}, content=body, timeout=6, follow_redirects=False)
        if not response.is_success:
            raise ProviderError(f"TypeSafe returned HTTP {response.status_code}")
        parsed = DecisionResponse.model_validate(response.json())
        if set(parsed.answers) != set(questions):
            raise ProviderError("TypeSafe returned mismatched decision identities.")
        for key, question in questions.items():
            answer = parsed.answers.get(key)
            if answer is None or answer.type != question["type"] or (isinstance(answer, Choice) and answer.choice not in question["criteria"]):
                raise ProviderError("TypeSafe returned an invalid decision.")
            if isinstance(answer, Choice) and answer.probabilities is not None:
                probabilities = answer.probabilities
                if set(probabilities) != set(question["criteria"]) or abs(sum(probabilities.values()) - 1) > .000001 or probabilities[answer.choice] < max(probabilities.values()):
                    raise ProviderError("TypeSafe returned invalid choice probabilities.")
        if parsed.usage is None:
            raise ProviderError("TypeSafe usage is unavailable; retain the reservation for reconciliation.")
        if parsed.usage.input_tokens > MAX_INPUT_TOKENS:
            raise ProviderError("TypeSafe usage exceeds the reserved input bound; reconcile provider billing.")
        budget.settle(reservation, max(1, (parsed.usage.input_tokens * rate + 999999) // 1000000))
        return {key: answer.model_dump(exclude={"probabilities"}) for key, answer in parsed.answers.items()}
    except (httpx.HTTPError, TypeError, ValueError, RecursionError, ValidationError, ProviderError) as error:
        # Missing or malformed responses may still be billed. Keep their full reservation.
        if strict:
            raise ProviderError(str(error) if isinstance(error, ProviderError) else "TypeSafe response unavailable or invalid.") from None
        return None
