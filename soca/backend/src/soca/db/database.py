"""Database class for Cosmos DB operations."""

from typing import Any, Optional

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from soca.config import settings
from soca.models import (
    CriteriaSet,
    Evaluation,
    Submission,
)


class Database:
    """Cosmos DB database wrapper."""

    def __init__(self) -> None:
        """Initialize database connection."""
        self._client: Optional[CosmosClient] = None
        self._database: Any = None
        self._submissions_container: Any = None
        self._criteria_container: Any = None
        self._evaluations_container: Any = None
        # In-memory storage for local development
        self._use_memory = not settings.cosmos_uri
        self._memory_submissions: dict[str, dict[str, Any]] = {}
        self._memory_criteria: dict[str, dict[str, Any]] = {}
        self._memory_evaluations: dict[str, dict[str, Any]] = {}

    def _init_cosmos(self) -> None:
        """Initialize Cosmos DB client and containers."""
        if self._client is not None:
            return

        self._client = CosmosClient(settings.cosmos_uri, settings.cosmos_key)
        self._database = self._client.create_database_if_not_exists(settings.cosmos_database)
        self._submissions_container = self._database.create_container_if_not_exists(
            id="submissions",
            partition_key=PartitionKey(path="/id"),
        )
        self._criteria_container = self._database.create_container_if_not_exists(
            id="criteria",
            partition_key=PartitionKey(path="/id"),
        )
        self._evaluations_container = self._database.create_container_if_not_exists(
            id="evaluations",
            partition_key=PartitionKey(path="/id"),
        )

    # Submissions
    async def list_submissions(self) -> list[Submission]:
        """List all submissions."""
        if self._use_memory:
            return [
                Submission(**s)
                for s in sorted(
                    self._memory_submissions.values(),
                    key=lambda x: x["uploadedAt"],
                    reverse=True,
                )
            ]
        self._init_cosmos()
        items = list(self._submissions_container.read_all_items())
        return [Submission(**item) for item in items]

    async def create_submission(self, submission: Submission) -> Submission:
        """Create a new submission."""
        data = submission.model_dump(by_alias=True)
        if self._use_memory:
            self._memory_submissions[submission.id] = data
        else:
            self._init_cosmos()
            self._submissions_container.create_item(data)
        return submission

    async def get_submission(self, submission_id: str) -> Optional[Submission]:
        """Get a submission by ID."""
        if self._use_memory:
            data = self._memory_submissions.get(submission_id)
            return Submission(**data) if data else None
        self._init_cosmos()
        try:
            item = self._submissions_container.read_item(submission_id, partition_key=submission_id)
            return Submission(**item)
        except CosmosResourceNotFoundError:
            return None

    async def delete_submission(self, submission_id: str) -> bool:
        """Delete a submission."""
        if self._use_memory:
            if submission_id in self._memory_submissions:
                del self._memory_submissions[submission_id]
                return True
            return False
        self._init_cosmos()
        try:
            self._submissions_container.delete_item(submission_id, partition_key=submission_id)
            return True
        except CosmosResourceNotFoundError:
            return False

    async def update_submission(self, submission: Submission) -> Submission:
        """Update a submission."""
        data = submission.model_dump(by_alias=True)
        if self._use_memory:
            self._memory_submissions[submission.id] = data
        else:
            self._init_cosmos()
            self._submissions_container.upsert_item(data)
        return submission

    # Criteria Sets
    async def list_criteria_sets(self) -> list[CriteriaSet]:
        """List all criteria sets."""
        if self._use_memory:
            return [
                CriteriaSet(**c)
                for c in sorted(
                    self._memory_criteria.values(),
                    key=lambda x: x["createdAt"],
                    reverse=True,
                )
            ]
        self._init_cosmos()
        items = list(self._criteria_container.read_all_items())
        return [CriteriaSet(**item) for item in items]

    async def create_criteria_set(self, criteria_set: CriteriaSet) -> CriteriaSet:
        """Create a new criteria set."""
        data = criteria_set.model_dump(by_alias=True)
        if self._use_memory:
            self._memory_criteria[criteria_set.id] = data
        else:
            self._init_cosmos()
            self._criteria_container.create_item(data)
        return criteria_set

    async def get_criteria_set(self, criteria_set_id: str) -> Optional[CriteriaSet]:
        """Get a criteria set by ID."""
        if self._use_memory:
            data = self._memory_criteria.get(criteria_set_id)
            return CriteriaSet(**data) if data else None
        self._init_cosmos()
        try:
            item = self._criteria_container.read_item(
                criteria_set_id, partition_key=criteria_set_id
            )
            return CriteriaSet(**item)
        except CosmosResourceNotFoundError:
            return None

    async def update_criteria_set(self, criteria_set: CriteriaSet) -> CriteriaSet:
        """Update a criteria set."""
        data = criteria_set.model_dump(by_alias=True)
        if self._use_memory:
            self._memory_criteria[criteria_set.id] = data
        else:
            self._init_cosmos()
            self._criteria_container.upsert_item(data)
        return criteria_set

    async def delete_criteria_set(self, criteria_set_id: str) -> bool:
        """Delete a criteria set."""
        if self._use_memory:
            if criteria_set_id in self._memory_criteria:
                del self._memory_criteria[criteria_set_id]
                return True
            return False
        self._init_cosmos()
        try:
            self._criteria_container.delete_item(criteria_set_id, partition_key=criteria_set_id)
            return True
        except CosmosResourceNotFoundError:
            return False

    # Evaluations
    async def list_evaluations(self) -> list[Evaluation]:
        """List all evaluations."""
        if self._use_memory:
            return [
                Evaluation(**e)
                for e in sorted(
                    self._memory_evaluations.values(),
                    key=lambda x: x["createdAt"],
                    reverse=True,
                )
            ]
        self._init_cosmos()
        items = list(self._evaluations_container.read_all_items())
        return [Evaluation(**item) for item in items]

    async def create_evaluation(self, evaluation: Evaluation) -> Evaluation:
        """Create a new evaluation."""
        data = evaluation.model_dump(by_alias=True)
        if self._use_memory:
            self._memory_evaluations[evaluation.id] = data
        else:
            self._init_cosmos()
            self._evaluations_container.create_item(data)
        return evaluation

    async def get_evaluation(self, evaluation_id: str) -> Optional[Evaluation]:
        """Get an evaluation by ID."""
        if self._use_memory:
            data = self._memory_evaluations.get(evaluation_id)
            return Evaluation(**data) if data else None
        self._init_cosmos()
        try:
            item = self._evaluations_container.read_item(evaluation_id, partition_key=evaluation_id)
            return Evaluation(**item)
        except CosmosResourceNotFoundError:
            return None

    async def update_evaluation(self, evaluation: Evaluation) -> Evaluation:
        """Update an evaluation."""
        data = evaluation.model_dump(by_alias=True)
        if self._use_memory:
            self._memory_evaluations[evaluation.id] = data
        else:
            self._init_cosmos()
            self._evaluations_container.upsert_item(data)
        return evaluation

    async def delete_evaluation(self, evaluation_id: str) -> bool:
        """Delete an evaluation."""
        if self._use_memory:
            if evaluation_id in self._memory_evaluations:
                del self._memory_evaluations[evaluation_id]
                return True
            return False
        self._init_cosmos()
        try:
            self._evaluations_container.delete_item(evaluation_id, partition_key=evaluation_id)
            return True
        except CosmosResourceNotFoundError:
            return False
