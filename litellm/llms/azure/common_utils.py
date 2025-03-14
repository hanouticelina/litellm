from typing import Callable, Optional, Union

import httpx
from openai import AsyncAzureOpenAI, AzureOpenAI

import litellm
from litellm._logging import verbose_logger
from litellm.llms.base_llm.chat.transformation import BaseLLMException
from litellm.secret_managers.main import get_secret_str


class AzureOpenAIError(BaseLLMException):
    def __init__(
        self,
        status_code,
        message,
        request: Optional[httpx.Request] = None,
        response: Optional[httpx.Response] = None,
        headers: Optional[Union[httpx.Headers, dict]] = None,
        body: Optional[dict] = None,
    ):
        super().__init__(
            status_code=status_code,
            message=message,
            request=request,
            response=response,
            headers=headers,
            body=body,
        )


def get_azure_openai_client(
    api_key: Optional[str],
    api_base: Optional[str],
    timeout: Union[float, httpx.Timeout],
    max_retries: Optional[int],
    api_version: Optional[str] = None,
    organization: Optional[str] = None,
    client: Optional[Union[AzureOpenAI, AsyncAzureOpenAI]] = None,
    _is_async: bool = False,
) -> Optional[Union[AzureOpenAI, AsyncAzureOpenAI]]:
    received_args = locals()
    openai_client: Optional[Union[AzureOpenAI, AsyncAzureOpenAI]] = None
    if client is None:
        data = {}
        for k, v in received_args.items():
            if k == "self" or k == "client" or k == "_is_async":
                pass
            elif k == "api_base" and v is not None:
                data["azure_endpoint"] = v
            elif v is not None:
                data[k] = v
        if "api_version" not in data:
            data["api_version"] = litellm.AZURE_DEFAULT_API_VERSION
        if _is_async is True:
            openai_client = AsyncAzureOpenAI(**data)
        else:
            openai_client = AzureOpenAI(**data)  # type: ignore
    else:
        openai_client = client

    return openai_client


def process_azure_headers(headers: Union[httpx.Headers, dict]) -> dict:
    openai_headers = {}
    if "x-ratelimit-limit-requests" in headers:
        openai_headers["x-ratelimit-limit-requests"] = headers[
            "x-ratelimit-limit-requests"
        ]
    if "x-ratelimit-remaining-requests" in headers:
        openai_headers["x-ratelimit-remaining-requests"] = headers[
            "x-ratelimit-remaining-requests"
        ]
    if "x-ratelimit-limit-tokens" in headers:
        openai_headers["x-ratelimit-limit-tokens"] = headers["x-ratelimit-limit-tokens"]
    if "x-ratelimit-remaining-tokens" in headers:
        openai_headers["x-ratelimit-remaining-tokens"] = headers[
            "x-ratelimit-remaining-tokens"
        ]
    llm_response_headers = {
        "{}-{}".format("llm_provider", k): v for k, v in headers.items()
    }

    return {**llm_response_headers, **openai_headers}


def get_azure_ad_token_from_entrata_id(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    scope: str = "https://cognitiveservices.azure.com/.default",
) -> Callable[[], str]:
    """
    Get Azure AD token provider from `client_id`, `client_secret`, and `tenant_id`

    Args:
        tenant_id: str
        client_id: str
        client_secret: str
        scope: str

    Returns:
        callable that returns a bearer token.
    """
    from azure.identity import ClientSecretCredential, get_bearer_token_provider

    verbose_logger.debug("Getting Azure AD Token from Entrata ID")

    if tenant_id.startswith("os.environ/"):
        _tenant_id = get_secret_str(tenant_id)
    else:
        _tenant_id = tenant_id

    if client_id.startswith("os.environ/"):
        _client_id = get_secret_str(client_id)
    else:
        _client_id = client_id

    if client_secret.startswith("os.environ/"):
        _client_secret = get_secret_str(client_secret)
    else:
        _client_secret = client_secret

    verbose_logger.debug(
        "tenant_id %s, client_id %s, client_secret %s",
        _tenant_id,
        _client_id,
        _client_secret,
    )
    if _tenant_id is None or _client_id is None or _client_secret is None:
        raise ValueError("tenant_id, client_id, and client_secret must be provided")
    credential = ClientSecretCredential(_tenant_id, _client_id, _client_secret)

    verbose_logger.debug("credential %s", credential)

    token_provider = get_bearer_token_provider(credential, scope)

    verbose_logger.debug("token_provider %s", token_provider)

    return token_provider


def get_azure_ad_token_from_username_password(
    client_id: str,
    azure_username: str,
    azure_password: str,
    scope: str = "https://cognitiveservices.azure.com/.default",
) -> Callable[[], str]:
    """
    Get Azure AD token provider from `client_id`, `azure_username`, and `azure_password`

    Args:
        client_id: str
        azure_username: str
        azure_password: str
        scope: str

    Returns:
        callable that returns a bearer token.
    """
    from azure.identity import UsernamePasswordCredential, get_bearer_token_provider

    verbose_logger.debug(
        "client_id %s, azure_username %s, azure_password %s",
        client_id,
        azure_username,
        azure_password,
    )
    credential = UsernamePasswordCredential(
        client_id=client_id,
        username=azure_username,
        password=azure_password,
    )

    verbose_logger.debug("credential %s", credential)

    token_provider = get_bearer_token_provider(credential, scope)

    verbose_logger.debug("token_provider %s", token_provider)

    return token_provider
