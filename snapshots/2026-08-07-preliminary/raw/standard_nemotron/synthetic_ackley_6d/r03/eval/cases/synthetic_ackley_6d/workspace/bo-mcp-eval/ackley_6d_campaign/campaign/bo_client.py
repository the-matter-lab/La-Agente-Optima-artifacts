"""BO-MCP REST client wrapper for campaign operations.

Cache-buster nonce: 87fe1294-416b-4ab4-8491-0d8cb2c43c23
"""

import os
import uuid
from typing import Any

import httpx
import logfire
from pydantic import BaseModel


class CampaignCreateResponse(BaseModel):
    success: bool
    campaign_id: str | None = None
    errors: list[str] = []
    warnings: list[str] = []
    idempotency_replay: bool = False
    schema_version: int = 2
    spec_id: str | None = None


class SuggestionProvenance(BaseModel):
    batch_index: int
    generation_method: str
    iteration: int
    acquisition_function: str | None = None
    acquisition_value: float | None = None
    confidence_level: str | None = None
    explanation: str | None = None
    model_type: str | None = None
    model_uncertainty: float | None = None
    model_version: int | None = None
    random_seed: int | None = None


class SuggestionResponse(BaseModel):
    campaign_id: str
    created_at: str
    parameter_values: dict[str, Any]
    provenance: SuggestionProvenance
    status: str
    suggestion_id: str


class SuggestionsGenerateResponse(BaseModel):
    success: bool
    suggestions: list[SuggestionResponse] = []
    errors: list[str] = []
    iteration: int | None = None
    idempotency_replay: bool = False
    schema_version: int = 2


class ResultSubmitResponse(BaseModel):
    success: bool
    result_ids: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    duplicates_detected: list[dict[str, Any]] | None = None
    error_code: str | None = None
    field_errors: dict[str, list[str]] | None = None
    idempotency_replay: bool = False
    schema_version: int = 2


class CampaignResponse(BaseModel):
    campaign_id: str
    name: str
    spec_id: str
    created_at: str
    status: str
    intake: dict[str, Any]
    max_observations: int | None = None


class BoMcpClient:
    """Client for BO-MCP REST API."""

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
    ):
        self.api_url = api_url or os.environ.get("BO_MCP_API_URL")
        if not self.api_url:
            raise ValueError("BO_MCP_API_URL must be set in environment or passed explicitly")

        self.api_key = api_key or os.environ.get("BO_MCP_API_KEY")
        if not self.api_key:
            raise ValueError("BO_MCP_API_KEY must be set in environment or passed explicitly")

        self.timeout = timeout
        self._client = httpx.Client(
            base_url=self.api_url.rstrip("/"),
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
            timeout=timeout,
        )

    @classmethod
    def from_env(cls) -> "BoMcpClient":
        """Create client from environment variables."""
        return cls()

    def _generate_idempotency_key(self, prefix: str) -> str:
        """Generate a unique idempotency key."""
        return f"{prefix}-{uuid.uuid4().hex[:16]}"

    def create_campaign(self, intake: dict[str, Any]) -> CampaignCreateResponse:
        """Create a new BO campaign."""
        idempotency_key = self._generate_idempotency_key("create-campaign")
        logfire.info("Creating campaign", name=intake.get("name"))

        response = self._client.post(
            "/api/v1/campaigns",
            json={"intake": intake},
            headers={"Idempotency-Key": idempotency_key},
        )
        response.raise_for_status()
        data = response.json()
        return CampaignCreateResponse(**data)

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Get campaign details."""
        response = self._client.get(f"/api/v1/campaigns/{campaign_id}")
        response.raise_for_status()
        return response.json()

    def generate_suggestions(
        self, campaign_id: str, batch_size: int | None = None
    ) -> SuggestionsGenerateResponse:
        """Generate new suggestions for a campaign."""
        idempotency_key = self._generate_idempotency_key(f"suggest-{campaign_id}")
        params = {}
        if batch_size is not None:
            params["batch_size"] = batch_size

        logfire.info("Generating suggestions", campaign_id=campaign_id, batch_size=batch_size)

        response = self._client.post(
            f"/api/v1/suggestions/{campaign_id}/generate",
            params=params,
            headers={"Idempotency-Key": idempotency_key},
        )
        response.raise_for_status()
        data = response.json()
        return SuggestionsGenerateResponse(**data)

    def submit_results(
        self,
        campaign_id: str,
        results: list[dict[str, Any]],
        force: bool = False,
    ) -> ResultSubmitResponse:
        """Submit evaluation results for a campaign."""
        idempotency_key = self._generate_idempotency_key(f"results-{campaign_id}")
        payload = {"results": results, "source": "api"}
        if force:
            payload["force"] = True

        logfire.info("Submitting results", campaign_id=campaign_id, count=len(results))

        response = self._client.post(
            f"/api/v1/results/{campaign_id}",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        response.raise_for_status()
        data = response.json()
        return ResultSubmitResponse(**data)

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()