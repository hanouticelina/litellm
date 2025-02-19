import logging
import os
from typing import TYPE_CHECKING, Any, List, Optional, Union

import httpx

from litellm.types.llms.openai import AllMessageValues

if TYPE_CHECKING:
    from litellm.litellm_core_utils.litellm_logging import Logging as LiteLLMLoggingObj

    LoggingClass = LiteLLMLoggingObj
else:
    LoggingClass = Any

from litellm.llms.base_llm.chat.transformation import BaseLLMException

from ...openai.chat.gpt_transformation import OpenAIGPTConfig
from ..common_utils import HuggingFaceError, _fetch_inference_provider_mapping

if TYPE_CHECKING:
    from litellm.litellm_core_utils.litellm_logging import Logging as _LiteLLMLoggingObj

    LiteLLMLoggingObj = _LiteLLMLoggingObj
else:
    LiteLLMLoggingObj = Any

logger = logging.getLogger(__name__)

BASE_URL = "https://router.huggingface.co"


class HuggingFaceChatConfig(OpenAIGPTConfig):
    """
    Reference: https://huggingface.co/docs/huggingface_hub/guides/inference
    """

    def validate_environment(
        self,
        headers: dict,
        model: str,
        messages: List[AllMessageValues],
        optional_params: dict,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> dict:
        default_headers = {
            "content-type": "application/json",
        }
        if api_key is not None:
            default_headers["Authorization"] = f"Bearer {api_key}"

        headers = {**headers, **default_headers}

        return headers

    def get_error_class(
        self, error_message: str, status_code: int, headers: Union[dict, httpx.Headers]
    ) -> BaseLLMException:
        return HuggingFaceError(
            status_code=status_code, message=error_message, headers=headers
        )

    def get_base_url(self, model: str, base_url: Optional[str]) -> Optional[str]:
        """
        Get the API base for the Huggingface API.

        Do not add the chat/embedding/rerank extension here. Let the handler do this.
        """
        if model.startswith(("http://", "https://")):
            base_url = model
        elif base_url is None:
            base_url = os.getenv("HF_API_BASE") or os.getenv("HUGGINGFACE_API_BASE", "")
        return base_url

    def get_complete_url(
        self,
        api_base: str,
        model: str,
        optional_params: dict,
        stream: Optional[bool] = None,
    ) -> str:
        """
        Get the complete URL for the API call.
        For provider-specific routing through huggingface
        """
        # 1. Check if api_base is provided
        if api_base is not None:
            complete_url = api_base
        elif os.getenv("HF_API_BASE") or os.getenv("HUGGINGFACE_API_BASE"):
            complete_url = os.getenv("HF_API_BASE") or os.getenv(
                "HUGGINGFACE_API_BASE", ""
            )
        elif model.startswith(("http://", "https://")):
            complete_url = model
        # 4. Default construction with provider
        else:
            # Parse provider and model
            parts = model.split("/", 1)
            provider = parts[0] if len(parts) > 1 else "hf-inference"
            if provider == "novita":
                route = "chat/completions"
            else:
                route = "v1/chat/completions"
            complete_url = f"{BASE_URL}/{provider}/{route}"

        # Ensure URL doesn't end with a slash
        complete_url = complete_url.rstrip("/")
        return complete_url

    def transform_request(
        self,
        model: str,
        messages: List[AllMessageValues],
        optional_params: dict,
        litellm_params: dict,
        headers: dict,
    ) -> dict:
        if "max_retries" in optional_params:
            logger.warning("`max_retries` is not supported. It will be ignored.")
            optional_params.pop("max_retries", None)
        parts = model.split("/", 1)
        provider = parts[0] if len(parts) > 1 else "hf-inference"
        model = parts[1] if len(parts) > 1 else model
        provider_mapping = _fetch_inference_provider_mapping(model)
        if provider not in provider_mapping:
            raise HuggingFaceError(
                message=f"Model {model} is not supported for provider {provider}",
                status_code=404,
                headers={},
            )
        provider_mapping = provider_mapping[provider]
        if provider_mapping["status"] == "staging":
            logger.warning(
                f"Model {model} is in staging mode for provider {self.provider}. Meant for test purposes only."
            )
        mapped_model = provider_mapping["providerId"]
        messages = self._transform_messages(messages=messages, model=mapped_model)
        return {"model": mapped_model, "messages": messages, **optional_params}
