from uuid import UUID

from memory_application.ports import WorkItem
from memory_application.workflows import FormationWorkflow
from memory_domain import RequestContext


class FormationJobHandler:
    def __init__(self, workflow: FormationWorkflow) -> None:
        self.workflow = workflow

    async def __call__(self, item: WorkItem) -> None:
        if item.kind != "formation" or item.operation_id is None:
            raise ValueError("unsupported work item")
        payload = item.payload
        context = RequestContext(
            UUID(payload["tenant_id"]), UUID(payload["project_id"]), UUID(payload["principal_id"])
        )
        await self.workflow.run(context, item.operation_id, UUID(payload["episode_id"]))
