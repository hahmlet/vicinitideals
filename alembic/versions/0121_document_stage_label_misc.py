"""Document naming scheme: add stage + name_label, backfill, auto-file into Misc.

Revision ID: 0121
Revises: 0120

- `name_label`: user-entered name component (the scheme is
  project · task · label · stage · upload-date). Backfilled to the upload stem.
- `stage`: draft/final, drives the "Draft"/"Final" scheme segment. Defaults draft.
- Every document must live in a task. Existing task-less documents are filed
  into a per-project "Misc." task (created on demand).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("name_label", sa.String(length=512), nullable=False, server_default=""),
    )
    op.add_column(
        "documents",
        sa.Column("stage", sa.String(length=20), nullable=False, server_default="draft"),
    )

    conn = op.get_bind()

    # Backfill name_label = filename without its extension (the upload stem).
    conn.execute(
        sa.text(
            r"UPDATE documents SET name_label = "
            r"regexp_replace(filename, '\.[^.\\/]*$', '') WHERE name_label = ''"
        )
    )

    # File every task-less document into a per-project "Misc." task.
    #
    # Online only. The UPDATE above renders as static SQL and stays outside the
    # guard; this part reads rows to decide how many Misc. tasks to create and
    # what to call them, and offline mode has nothing to read -- execute()
    # returns None and .fetchall() raises. Same guard as 0043 and 0119. A
    # rendered script omits this step, so a hand-applied upgrade leaves
    # task-less documents where they were; the deploy path runs online.
    if op.get_context().as_sql:
        return

    projects = conn.execute(
        sa.text(
            "SELECT DISTINCT org_id, project_id FROM documents WHERE task_id IS NULL"
        )
    ).fetchall()
    for org_id, project_id in projects:
        misc_id = conn.execute(
            sa.text(
                "SELECT id FROM document_tasks "
                "WHERE org_id = :org AND project_id = :proj AND lower(title) = 'misc.' "
                "LIMIT 1"
            ),
            {"org": org_id, "proj": project_id},
        ).scalar()
        if misc_id is None:
            misc_id = conn.execute(
                sa.text(
                    "INSERT INTO document_tasks (id, org_id, project_id, title, status) "
                    "VALUES (gen_random_uuid(), :org, :proj, 'Misc.', 'pending') "
                    "RETURNING id"
                ),
                {"org": org_id, "proj": project_id},
            ).scalar()
        conn.execute(
            sa.text(
                "UPDATE documents SET task_id = :task "
                "WHERE org_id = :org AND project_id = :proj AND task_id IS NULL"
            ),
            {"task": misc_id, "org": org_id, "proj": project_id},
        )


def downgrade() -> None:
    op.drop_column("documents", "stage")
    op.drop_column("documents", "name_label")
