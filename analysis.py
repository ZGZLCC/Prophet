"""Backward-compatible imports for the person-profile package."""

from person_profile.analysis import (  # noqa: F401
    AnalysisError,
    ConfigurationError,
    DEFAULT_CHUNK_CHARS,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_RETRIES,
    DEFAULT_LLM_TIMEOUT,
    DEFAULT_MAX_ANALYSIS_CHARS,
    ENTRY_ANALYSIS_SCHEMA,
    LLM_SETTING_NAMES,
    MATERIAL_ANALYSIS_SCHEMA,
    MATERIAL_SYSTEM_PROMPT,
    MERGE_SYSTEM_PROMPT,
    PREDICTION_SCHEMA,
    PREDICTION_SYSTEM_PROMPT,
    PROFILE_SCHEMA,
    PROFILE_SECTIONS,
    PROFILE_SYSTEM_PROMPT,
    REVIEW_SCHEMA,
    REVIEW_SYSTEM_PROMPT,
    SUPPORTED_LLM_PROVIDER,
    SUPPORTED_LLM_PROVIDERS,
    analyze_and_save,
    analyze_material,
    build_client,
    empty_profile,
    llm_status,
    load_local_env,
    predict_and_save,
    predict_event,
    read_local_env,
    rebuild_profile,
    request_structured,
    restore_profile,
    review_and_save,
    review_prediction,
    save_local_env,
    split_text,
    update_profile,
)
from person_profile.analysis import (  # noqa: F401
    _HttpClient,
    _HttpEndpoint,
    _InvalidModelOutput,
    _response_json,
)

# Existing callers patch this module during the HTTP self-test.
import urllib  # noqa: E402,F401

