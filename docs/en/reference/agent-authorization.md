# Agent authorization

Browser sessions keep the existing membership and project-role checks. Agent
sessions additionally carry server-maintained `current_scope_kind` and
`current_project_id`, plus operation scopes. A parent's project membership does
not grant its delegated token access to another project.

Project checks apply to path, query, body, and name-based project resolution.
A project-scoped agent's project list is restricted to its current project.
Home-scope agents retain home navigation; changing an agent's active project is
the responsibility of the authenticated orchestrator, not a request payload.

| Operation | Required agent scope |
|---|---|
| Project configuration, styles, generic uploads, canvas and asset changes | `projects:write` |
| Explicit task submission, generation, verification, task preflight, and cancellation | `tasks:submit` |
| Chat notifications and stored UI events | `projects:write`, with a matching chat scope |
| CE gateway configuration changes | `projects:write`, plus the existing CE-only guard |

Existing endpoints with a more specific requirement retain it. For example,
synchronous episode rewrite remains a project-content write. Method names alone
do not grant permissions: each HTTP mutation declares an exact dependency.
The generic unsafe-method check is only a backstop, not an equivalence between
`projects:write` and `tasks:submit`. Browser logout remains a recovery operation
that can clear the caller's cookie even if its session is no longer valid.

Clients issued only `tasks:submit` must no longer use configuration/upload
endpoints. Have a suitably authorized caller prepare those inputs, or provision
the necessary scope through the existing credential-issuance workflow. Do not
automatically broaden existing tokens. Requests outside the delegated project
or missing an operation scope receive HTTP 403; endpoint paths and payloads
are unchanged.

CE remains a trusted, no-login single-user service. These token checks do not
turn it into a multi-user authentication service: keep the network boundary
described in the [self-hosting guide](../guides/self-hosting.md).
