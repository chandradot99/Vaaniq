"""
PostSessionActionNode — trigger side effects after the session ends.

Enqueues a Celery task for each configured action. The actual work
(CRM lead creation, WhatsApp summary, etc.) runs asynchronously so
it never blocks the voice/chat session.

Config:
    actions  (list[str])  action names to trigger, e.g.:
                          ["create_crm_lead", "send_whatsapp_summary"]

The Celery task runner lives in naaviq-server. This node only enqueues
the task by name — it does not import Celery directly, keeping this
package free of server dependencies.

The task dispatcher is injected via org_keys["_task_dispatcher"] at
build time by naaviq-server. If not present, actions are logged and skipped.
"""
import structlog

from naaviq.core.state import SessionState
from naaviq.graph.nodes.base import BaseNode

log = structlog.get_logger()


class PostSessionActionNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        actions: list[str] = self.config.get("actions", [])
        dispatcher = self.org_keys.get("_task_dispatcher")

        already_done: set[str] = set(state.get("post_actions_completed") or [])
        newly_completed: list[str] = []

        for action in actions:
            if action in already_done:
                continue
            if dispatcher is not None:
                dispatcher(action, state)
            else:
                log.info("post_session_action_skipped", action=action,
                         reason="no task dispatcher injected")
            newly_completed.append(action)

        return {"post_actions_completed": newly_completed}   # reducer appends
