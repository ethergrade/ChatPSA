"""Deny-by-default projections for data returned to MCP clients."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from html import unescape
import re

SAFE_TICKET_FIELDS = (
    "id",
    "summary",
    "status_id",
    "status_name",
    "tickettype_id",
    "tickettype_name",
    "client_id",
    "client_name",
    "site_id",
    "site_name",
    "user_id",
    "user_name",
    "team_id",
    "team",
    "agent_id",
    "workflow_id",
    "workflow_name",
    "workflow_step",
    "workflow_seq",
    "priority_id",
    "sla_id",
    "sla_name",
    "dateoccurred",
    "last_update_date",
)

SAFE_AGENT_FIELDS = ("id", "name")

SAFE_STATUS_FIELDS = (
    "id",
    "guid",
    "name",
    "shortname",
    "type",
    "colour",
    "sequence",
    "showonquickchange",
    "includeinloadbalance",
    "dontsendslareminders",
    "slaaction",
    "slaignorerelease",
    "statuschangeto",
    "statuschangetofreq",
    "statusemailid",
    "statusemailfreqdays",
    "statusnochangehours",
    "useworkinghours",
)

SAFE_TICKETTYPE_FIELDS = (
    "id",
    "guid",
    "name",
    "sequence",
    "visible",
    "agentscanselect",
    "enduserscanselect",
    "enduserscanlog",
    "anonymouscanselect",
    "anonymouscanlog",
    "cancreate",
    "group_id",
    "group_name",
    "use",
    "itilrequesttype",
    "workflow_id",
    "initial_status",
    "reopenedstatus",
    "statusaftertechupdate",
    "statusafteruserupdate",
    "statusaftersupplierupdate",
    "statusafterapproverupdate",
    "parentstatusafterallchildclosed",
    "default_team",
    "default_agent",
    "default_priority",
    "default_sla",
    "default_sendack",
    "default_sendemail",
    "dontsendslareminders",
    "dontusependingclosure",
    "apply_workflow_on_type_change",
    "allowtickettypetobechild",
    "allowall_child_tickettypes",
    "allow_all_clients",
    "allowattachments",
    "includeinmobiledbsync",
    "appointmentdefaultbody",
    "project_type",
    "is_sprint",
    "access_control_level",
)

SAFE_CATEGORY_FIELDS = (
    "id",
    "guid",
    "category_name",
    "value",
    "type_id",
    "sla_id",
    "priority_id",
    "chargerate",
    "category_group_id",
    "itilrequesttype",
    "allow_ai_suggestion",
    "level1",
    "level2",
    "level3",
)

SAFE_WORKFLOW_FIELDS = (
    "id",
    "guid",
    "name",
    "note",
    "active",
    "notinuse",
    "access_control_level",
)

SAFE_WORKFLOW_STEP_FIELDS = (
    "fdid",
    "guid",
    "step_id",
    "flow_id",
    "name",
    "isstart",
    "isend",
    "islaststep",
    "stage_number",
    "steptype",
    "duration",
)

SAFE_WORKFLOW_ACTION_FIELDS = (
    "id",
    "flow_id",
    "action_id",
    "action_name",
    "action_outcome",
    "action_type",
    "seq",
    "auto_seq",
    "start_step",
    "end_step",
    "restricted",
    "use_work_hours",
)

SAFE_WORKFLOW_STAGE_FIELDS = (
    "id",
    "flow_id",
    "name",
    "sequence",
    "type",
    "edit_outcome",
)

SAFE_WORKFLOW_ALWAYS_ACTION_FIELDS = ("id", "buttonname", "labellong")

SAFE_OUTCOME_FIELDS = (
    "id",
    "guid",
    "outcome",
    "buttonname",
    "labellong",
    "sequence",
    "hidden",
    "actionvisibility",
    "systemid",
    "colour",
    "actiongroup",
    "createchildticketortemplate",
    "child_ticket_type_id",
    "requesttype",
    "child_template_id",
    "dontshowscreen",
    "hidetickettypeselection",
    "add_note_to_parent",
    "newsummaryfromsource",
    "newdetailsfromsource",
    "setdetailsfromnewticket",
    "showevenifnochild",
    "newstatus",
    "defaultteam",
    "defaultagent",
    "defaultpriority",
    "workflow_id",
    "workflow_step_id",
    "access_control_level",
)

SAFE_TICKETRULE_FIELDS = (
    "id",
    "guid",
    "name",
    "active",
    "precedence",
    "stopmatching",
    "use",
    "group_id",
    "flowdetail_id",
    "dontshownotification",
    "new_workflow_id",
    "new_workflow_name",
    "new_status_id",
    "new_teamid",
    "new_team",
    "new_agent_id",
    "new_agent_name",
    "new_priority_id",
    "new_sla_id",
    "new_template_id",
    "new_template_name",
    "outcome_id",
    "outcome_name",
    "script_id",
    "script_name",
    "set_colour",
    "set_ticket_ai_indexing",
    "batch_size",
    "batch_sleep",
    "access_control_level",
)

SAFE_TICKETRULE_CRITERIA_FIELDS = (
    "id",
    "rule_id",
    "fieldname",
    "tablename",
    "type",
    "use",
    "value_int",
    "value_string",
    "value_type",
    "value_type_id",
    "partialmatch",
    "matchseparatedvalues",
    "match_after_start",
    "match_after_target",
    "flow_id",
    "flow_seq",
    "flow_type",
)

SAFE_TICKETRULE_OUTCOME_FIELDS = (
    "id",
    "rule_id",
    "fieldname",
    "value_string",
    "value_type",
    "value_type_id",
    "is_dummy",
)

SAFE_KB_ARTICLE_FIELDS = (
    "id",
    "name",
    "description",
    "description_html",
    "description_markdown",
    "resolution",
    "resolution_html",
    "resolution_markdown",
    "date_created",
    "date_edited",
    "next_review_date",
    "inactive",
    "is_draft",
    "type",
    "link",
    "kb_tags",
    "tag_string",
    "primary_faq_list",
    "primary_faq_list_name",
    "showforall",
    "showforallroles",
    "access_control_level",
)

SAFE_KB_TAG_FIELDS = ("id", "text", "type")
SAFE_RELEASE_FIELDS = (
    "id",
    "name",
    "name_expanded",
    "releasetype_id",
    "releasetype_name",
    "builddate",
    "targetdate",
    "releasedate",
    "note",
    "public_note",
    "sequence",
    "major_version_number",
    "minor_version_number",
    "patch_version_number",
)
SAFE_RELEASE_TYPE_FIELDS = ("id", "name", "releasenoteset")
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def project_fields(source: Mapping[str, Any], allowlist: tuple[str, ...]) -> dict[str, Any]:
    """Return only explicitly permitted scalar values from a source object."""

    projected: dict[str, Any] = {}
    for key in allowlist:
        if key not in source:
            continue
        value = source[key]
        if value is None or isinstance(value, (str, int, float, bool)):
            projected[key] = value
    return projected


def safe_ticket_projection(ticket: Mapping[str, Any]) -> dict[str, Any]:
    projected = project_fields(ticket, SAFE_TICKET_FIELDS)
    assets = ticket.get("assets")
    if isinstance(assets, list):
        projected["assets_count"] = len(assets)
    return projected


def safe_agent_projection(agent: Mapping[str, Any]) -> dict[str, Any]:
    return project_fields(agent, SAFE_AGENT_FIELDS)


def safe_status_projection(status: Mapping[str, Any]) -> dict[str, Any]:
    return project_fields(status, SAFE_STATUS_FIELDS)


def safe_tickettype_projection(tickettype: Mapping[str, Any]) -> dict[str, Any]:
    return project_fields(tickettype, SAFE_TICKETTYPE_FIELDS)


def safe_category_projection(category: Mapping[str, Any]) -> dict[str, Any]:
    return project_fields(category, SAFE_CATEGORY_FIELDS)


def safe_workflow_projection(workflow: Mapping[str, Any]) -> dict[str, Any]:
    projected = project_fields(workflow, SAFE_WORKFLOW_FIELDS)

    steps = workflow.get("steps")
    if isinstance(steps, list):
        safe_steps: list[dict[str, Any]] = []
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            safe_step = project_fields(step, SAFE_WORKFLOW_STEP_FIELDS)
            actions = step.get("actions")
            if isinstance(actions, list):
                safe_step["actions"] = [
                    project_fields(action, SAFE_WORKFLOW_ACTION_FIELDS)
                    for action in actions
                    if isinstance(action, Mapping)
                ]
            safe_steps.append(safe_step)
        projected["steps"] = safe_steps

    stages = workflow.get("stages")
    if isinstance(stages, list):
        projected["stages"] = [
            project_fields(stage, SAFE_WORKFLOW_STAGE_FIELDS)
            for stage in stages
            if isinstance(stage, Mapping)
        ]

    always_actions = workflow.get("always_allow_actions")
    if isinstance(always_actions, list):
        projected["always_allow_actions"] = [
            project_fields(action, SAFE_WORKFLOW_ALWAYS_ACTION_FIELDS)
            for action in always_actions
            if isinstance(action, Mapping)
        ]
    return projected


def safe_outcome_projection(outcome: Mapping[str, Any]) -> dict[str, Any]:
    return project_fields(outcome, SAFE_OUTCOME_FIELDS)


def safe_ticketrule_projection(rule: Mapping[str, Any]) -> dict[str, Any]:
    projected = project_fields(rule, SAFE_TICKETRULE_FIELDS)
    criteria = rule.get("criteria")
    if isinstance(criteria, list):
        projected["criteria"] = [
            project_fields(item, SAFE_TICKETRULE_CRITERIA_FIELDS)
            for item in criteria
            if isinstance(item, Mapping)
        ]
    outcomes = rule.get("outcomes")
    if isinstance(outcomes, list):
        projected["outcomes"] = [
            project_fields(item, SAFE_TICKETRULE_OUTCOME_FIELDS)
            for item in outcomes
            if isinstance(item, Mapping)
        ]
    return projected


def _clean_kb_text(value: Any, *, limit: int = 6_000) -> str | None:
    if not isinstance(value, str):
        return None
    plain = unescape(_HTML_TAG_PATTERN.sub(" ", value))
    compact = " ".join(plain.split())
    if not compact:
        return None
    return compact[:limit]


def safe_kb_tag_projection(tag: Mapping[str, Any]) -> dict[str, Any]:
    return project_fields(tag, SAFE_KB_TAG_FIELDS)


def safe_kb_article_projection(article: Mapping[str, Any]) -> dict[str, Any]:
    projected = project_fields(article, SAFE_KB_ARTICLE_FIELDS)
    for field in (
        "description",
        "description_html",
        "description_markdown",
        "resolution",
        "resolution_html",
        "resolution_markdown",
    ):
        if field in projected:
            cleaned = _clean_kb_text(projected[field])
            if cleaned:
                projected[field] = cleaned
            else:
                projected.pop(field, None)
    tags = article.get("tags")
    if isinstance(tags, list):
        projected["tags"] = [
            safe_kb_tag_projection(tag) for tag in tags if isinstance(tag, Mapping)
        ]
    return projected


def safe_release_projection(release: Mapping[str, Any]) -> dict[str, Any]:
    return project_fields(release, SAFE_RELEASE_FIELDS)


def safe_release_type_projection(release_type: Mapping[str, Any]) -> dict[str, Any]:
    return project_fields(release_type, SAFE_RELEASE_TYPE_FIELDS)
