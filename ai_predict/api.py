from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from ai_predict.models import MoviePrediction
from ai_predict.services import prediction_service, taste_profiles
from ai_predict.services import prompt as prompt_service
from vault.models import Movie

api = NinjaAPI(title="AI Predict API", version="1.0", urls_namespace="ai-predict-api")


class TasteProfileOut(Schema):
    id: int
    name: str
    content: str
    updated_at: str


class TasteProfileIn(Schema):
    name: str = ""
    content: str = ""


class TasteProfileUpdateIn(Schema):
    name: str | None = None
    content: str | None = None


class PredictionOut(Schema):
    id: int
    movie_id: int
    movie_title: str
    taste_profile_id: int | None = None
    taste_profile_name: str | None = None
    status: str
    status_display: str
    score: int | None = None
    verdict: str | None = None
    verdict_display: str | None = None
    confidence: float | None = None
    result_text: str = ""
    error: str = ""
    model_name: str = ""
    duration_ms: int | None = None
    created_at: str


class PredictIn(Schema):
    movie_id: int
    taste_profile_id: int | None = None


class PredictionEnvelope(Schema):
    prediction: PredictionOut | None = None


class PromptOut(Schema):
    content: str
    default_content: str
    is_default: bool
    updated_at: str | None = None


class PromptIn(Schema):
    content: str = ""


class OkOut(Schema):
    ok: bool


def _require_api_user(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise HttpError(401, "Authentication required")
    return user


def _serialize_taste(profile) -> TasteProfileOut:
    return TasteProfileOut(
        id=profile.id,
        name=profile.name,
        content=profile.content or "",
        updated_at=profile.updated_at.isoformat(),
    )


def _serialize_prediction(prediction: MoviePrediction) -> PredictionOut:
    return PredictionOut(
        id=prediction.id,
        movie_id=prediction.movie_id,
        movie_title=prediction.movie.title,
        taste_profile_id=prediction.taste_profile_id,
        taste_profile_name=prediction.taste_profile.name if prediction.taste_profile else None,
        status=prediction.status,
        status_display=prediction.get_status_display(),
        score=prediction.score,
        verdict=prediction.verdict or None,
        verdict_display=prediction.get_verdict_display() if prediction.verdict else None,
        confidence=prediction.confidence,
        result_text=prediction.result_text or "",
        error=prediction.error or "",
        model_name=prediction.model_name or "",
        duration_ms=prediction.duration_ms,
        created_at=prediction.created_at.isoformat(),
    )


# ------------------------------------ #
#            TASTE PROFILES            #
# ------------------------------------ #


@api.get("/tastes", response=list[TasteProfileOut])
def list_tastes(request):
    _require_api_user(request)
    return [_serialize_taste(profile) for profile in taste_profiles.list_taste_profiles()]


@api.post("/tastes", response=TasteProfileOut)
def create_taste(request, payload: TasteProfileIn):
    _require_api_user(request)
    try:
        profile = taste_profiles.create_taste_profile(name=payload.name, content=payload.content)
    except taste_profiles.TasteProfileError as exc:
        raise HttpError(400, str(exc))
    return _serialize_taste(profile)


@api.patch("/tastes/{taste_id}", response=TasteProfileOut)
def update_taste(request, taste_id: int, payload: TasteProfileUpdateIn):
    _require_api_user(request)
    profile = taste_profiles.get_taste_profile(taste_id)
    if profile is None:
        raise HttpError(404, "Профиль вкусов не найден.")
    if payload.name is None and payload.content is None:
        raise HttpError(400, "Нечего обновлять: передайте name и/или content.")
    try:
        updated = taste_profiles.update_taste_profile(
            profile,
            name=payload.name,
            content=payload.content,
        )
    except taste_profiles.TasteProfileError as exc:
        raise HttpError(400, str(exc))
    return _serialize_taste(updated)


@api.delete("/tastes/{taste_id}", response=OkOut)
def delete_taste(request, taste_id: int):
    _require_api_user(request)
    profile = taste_profiles.get_taste_profile(taste_id)
    if profile is None:
        raise HttpError(404, "Профиль вкусов не найден.")
    taste_profiles.delete_taste_profile(profile)
    return OkOut(ok=True)


# ------------------------------------ #
#          SYSTEM PROMPT               #
# ------------------------------------ #


@api.get("/prompt", response=PromptOut)
def get_prompt(request):
    _require_api_user(request)
    return PromptOut(**prompt_service.get_prompt_state())


@api.put("/prompt", response=PromptOut)
def save_prompt(request, payload: PromptIn):
    _require_api_user(request)
    try:
        state = prompt_service.save_prompt_template(payload.content)
    except prompt_service.PromptError as exc:
        raise HttpError(400, str(exc))
    return PromptOut(**state)


@api.post("/prompt/reset", response=PromptOut)
def reset_prompt(request):
    _require_api_user(request)
    return PromptOut(**prompt_service.reset_prompt_template())


# ------------------------------------ #
#             PREDICTIONS              #
# ------------------------------------ #


@api.post("/predict", response=PredictionOut)
def run_prediction(request, payload: PredictIn):
    _require_api_user(request)
    movie = Movie.objects.filter(pk=payload.movie_id).first()
    if movie is None:
        raise HttpError(404, "Фильм не найден.")

    if payload.taste_profile_id is None:
        raise HttpError(400, "Выберите профиль вкусов — без него предсказание невозможно.")
    taste_profile = taste_profiles.get_taste_profile(payload.taste_profile_id)
    if taste_profile is None:
        raise HttpError(404, "Профиль вкусов не найден.")

    prediction = prediction_service.predict_movie(movie, taste_profile)
    return _serialize_prediction(prediction)


@api.get("/predictions/last", response=PredictionEnvelope)
def get_last_prediction(request, movie_id: int, taste_profile_id: int | None = None):
    _require_api_user(request)
    prediction = prediction_service.last_prediction(movie_id, taste_profile_id)
    return PredictionEnvelope(prediction=_serialize_prediction(prediction) if prediction else None)
