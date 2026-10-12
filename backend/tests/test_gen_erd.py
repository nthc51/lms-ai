from scripts.gen_erd import render


def test_erd_lists_core_tables_and_relationships():
    md = render()
    assert "erDiagram" in md
    for table in (
        "users",
        "courses",
        "sections",
        "lessons",
        "chunks",
        "jobs",
        "admin_actions",
        "email_outbox",
        "ai_calls",
        "study_artifacts",
        "notes",
    ):
        assert f"    {table} {{" in md
    assert 'courses ||--o{ sections : "course_id"' in md
    assert "uuid id PK" in md
