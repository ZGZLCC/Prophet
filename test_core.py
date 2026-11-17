"""Small checks for the stage-A/B/C/D data, analysis, and parser paths."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import analysis
import background_jobs
import desktop
import parsers
import storage


class _Response:
    status = "completed"

    def __init__(self, payload: dict):
        self.output_text = json.dumps(payload, ensure_ascii=False)


def _material_payload(label: str) -> dict:
    return {
        "source_summary": f"摘要：{label}",
        "observed_emotions": [
            {
                "name": "平静",
                "intensity": "medium",
                "evidence": label,
                "confidence": "medium",
            }
        ],
        "observed_behaviors": [
            {"description": "直接表达", "evidence": label, "confidence": "medium"}
        ],
        "possible_needs": [
            {"description": "被理解", "reasoning": label, "confidence": "low"}
        ],
        "triggers_and_context": [],
        "new_hypotheses": [],
        "contradictions": [],
        "missing_context": [],
    }


def _prediction_payload() -> dict:
    reaction = {
        "reaction": "先确认原因再回应",
        "emotion": "谨慎",
        "behavior": "询问细节并调整安排",
        "conditions": ["对方提前说明原因"],
        "evidence": ["画像中的直接沟通倾向"],
        "confidence": "medium",
    }
    alternative = {
        **reaction,
        "reaction": "暂时不回应",
        "emotion": "不确定",
        "behavior": "稍后再处理",
        "conditions": ["信息不足或时间紧张"],
        "confidence": "low",
    }
    return {
        "likely_reactions": [reaction, alternative],
        "alternatives": ["直接接受安排并继续沟通。"],
        "unknowns": ["尚不清楚当时的时间压力。"],
        "safe_interaction_suggestion": "说明变化原因，并给对方保留选择空间。",
    }


def _review_payload() -> dict:
    return {
        "assessment": "partially_matched",
        "summary": "实际结果与部分预测一致，但仍有情境差异。",
        "matched_points": ["仍然进行了直接沟通。"],
        "differences": ["回应时间比预期更晚。"],
        "possible_reasons": ["当时可能存在额外时间压力。"],
        "unknowns": ["无法确认延迟回应的具体原因。"],
        "profile_adjustments": ["保留直接沟通倾向，同时降低对即时回应的信心。"],
    }


def _profile_payload(entry_ids: list[int]) -> dict:
    item = {
        "claim": "会直接表达感受",
        "kind": "observation",
        "confidence": "low" if len(entry_ids) == 1 else "medium",
        "evidence_entry_ids": entry_ids,
    }
    return {
        "summary_md": "## 当前画像\n会直接表达感受。",
        "overview": "基于当前材料的暂时画像。",
        "emotion_patterns": [item],
        "triggers": [],
        "behavior_tendencies": [],
        "communication_preferences": [],
        "values_and_needs": [],
        "situational_differences": [],
        "uncertainties_and_contradictions": [],
    }


class _FakeResponses:
    def __init__(self):
        self.calls: list[dict] = []
        self.entry_ids: list[int] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        schema_name = kwargs["text"]["format"]["name"]
        if schema_name in {"material_analysis", "material_analysis_merge"}:
            return _Response(_material_payload(f"材料 {len(self.entry_ids) + 1}"))
        if schema_name == "prediction":
            return _Response(_prediction_payload())
        if schema_name == "prediction_review":
            return _Response(_review_payload())
        contract = kwargs["input"].split(
            "<evidence_contract>\n", 1
        )[1].split("\n</evidence_contract>", 1)[0]
        valid_entry_ids = json.loads(contract)["valid_entry_ids"]
        self.entry_ids = valid_entry_ids
        return _Response(_profile_payload(valid_entry_ids))


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponses()


class _InvalidClient:
    class _Responses:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            return _Response({})

    def __init__(self):
        self.responses = self._Responses()


class _UrlopenResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def _seed_related_rows(db_path: Path, person_id: int) -> None:
    connection = storage.connect(db_path)
    try:
        timestamp = "2026-01-01T00:00:00+00:00"
        entry = connection.execute(
            """
            INSERT INTO entries
                (person_id, entry_type, content, content_hash, created_at)
            VALUES (?, 'text', 'seed', 'seed-hash', ?)
            """,
            (person_id, timestamp),
        )
        entry_id = entry.lastrowid
        connection.execute(
            """
            INSERT INTO profiles
                (person_id, version, profile_json, updated_at)
            VALUES (?, 1, '{}', ?)
            """,
            (person_id, timestamp),
        )
        connection.execute(
            """
            INSERT INTO profile_revisions
                (person_id, version, profile_json, trigger_entry_id, created_at)
            VALUES (?, 1, '{}', ?, ?)
            """,
            (person_id, entry_id, timestamp),
        )
        connection.execute(
            """
            INSERT INTO predictions
                (person_id, profile_version, event_text, prediction_json, created_at)
            VALUES (?, 1, 'event', '{}', ?)
            """,
            (person_id, timestamp),
        )
        connection.commit()
    finally:
        connection.close()


def test_people_persist_and_stay_isolated() -> None:
    with TemporaryDirectory() as temporary_directory:
        db_path = Path(temporary_directory) / "sentiment.db"
        storage.init_db(db_path)
        alice_id = storage.create_person(db_path, " Alice ", "备注")
        bob_id = storage.create_person(db_path, "Bob")

        assert [person["name"] for person in storage.list_people(db_path)] == [
            "Alice",
            "Bob",
        ]
        assert storage.get_person(db_path, alice_id)["notes"] == "备注"
        assert storage.get_person(db_path, bob_id)["notes"] == ""

        storage.update_person(db_path, alice_id, "Alice 2", "新备注")
        assert storage.get_person(db_path, alice_id)["name"] == "Alice 2"
        assert storage.get_person(db_path, alice_id)["notes"] == "新备注"


def test_local_env_file_loading_preserves_environment_priority() -> None:
    names = ("SENTIMENT_TEST_FROM_FILE", "SENTIMENT_TEST_PRIORITY")
    original = {name: os.environ.get(name) for name in names}
    try:
        os.environ.pop(names[0], None)
        os.environ[names[1]] = "from-environment"
        with TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                "SENTIMENT_TEST_FROM_FILE='from-file'\n"
                "SENTIMENT_TEST_PRIORITY=from-file\n",
                encoding="utf-8",
            )
            analysis.load_local_env(env_path)
            assert os.environ[names[0]] == "from-file"
            assert os.environ[names[1]] == "from-environment"
            saved_path = Path(temporary_directory) / "saved.env"
            analysis.save_local_env(
                saved_path,
                {"LLM_API_KEY": "new-key", "LLM_MODEL": "new-model"},
                template=env_path,
            )
            saved = analysis.read_local_env(saved_path)
            assert saved["LLM_API_KEY"] == "new-key"
            assert saved["LLM_MODEL"] == "new-model"
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_background_job_runs_outside_the_page_call() -> None:
    assert background_jobs.submit(lambda: "done").result(timeout=2) == "done"


def test_desktop_uses_native_assets_without_http_service() -> None:
    launcher = (desktop.RESOURCE_ROOT / "desktop.py").read_text(encoding="utf-8")
    index = (desktop.RESOURCE_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    web_root = desktop.RESOURCE_ROOT / "web"
    script = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [web_root / "app.js", *sorted((web_root / "modules").glob("*.js"))]
    )
    styles = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [web_root / "styles.css", *sorted((web_root / "styles").glob("*.css"))]
    )
    requirements = (desktop.RESOURCE_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert 'content="light dark"' in index
    assert 'id="startup-splash"' in index
    assert 'id="setting-theme"' in index
    assert 'id="setting-timezone"' in index
    assert 'localStorage.getItem("prophet-theme")' in index + script
    assert "saveAppearanceSettings" in script
    assert "save_appearance_settings" in script
    assert 'timeZone: state.settings?.timezone || "Asia/Shanghai"' in script
    assert "animatedRoute !== state.route" in script
    assert ".page-intro.is-entering" in styles
    assert "data-route-content='profile'" in script
    assert "data-route-content='fortune'" in script
    assert "person-avatar" not in script + styles
    assert "stage-number" not in script + styles
    assert "inspect-chat" not in script
    assert "renderChatInspection" not in script
    assert "analysis-start-button" in script
    assert "analysis-code-box" in script
    assert 'data-action="generate-chat-commands"' not in script
    assert "scheduleChatAnalysisPreview" in script
    assert "if (!values.inputPath.trim() || !values.target.trim())" not in script
    assert "scheduleChatAnalysisValidation" in script
    assert "resetChatAnalysisValidation" in script
    assert 'callApi("inspect_chat", path)' in script
    assert 'addEventListener("focusout"' in script
    assert 'if (event.target.id === "chat-analysis-input") scheduleChatAnalysisValidation();' not in script
    assert "targetChecked = true" in script
    assert 'analysisState.prompt || (ready ? ""' in script
    assert 'analysisState.commands || (ready ? ""' in script
    assert "if (panel) panel.textContent = '';" in script
    assert "path-callout" not in script + styles
    assert ".analysis-code-box .button" in styles
    assert ".page-view .analysis-code-box pre" in styles
    assert "font-family: var(--font-sans)" in styles
    assert "line-height: 25.6px" in styles
    assert "chatAnalysisReady" in script
    assert "busy || !ready" in script
    assert "ready && analysisState.prompt" in script
    assert "ready && analysisState.commands" in script
    assert "!modelConfigured" in script
    assert 'status === "succeeded" ? detail : status === "failed"' in script
    assert "toggleFortuneInterpretation" in script
    assert "再次生成解读" in script
    assert "收起agent提示词" in script
    assert 'status-badge is-done">已保存' not in script
    assert script.index('class="fortune-facts"') < script.index('class="field fortune-result-export"') < script.index('class="fortune-result-actions"')
    assert "color: var(--red) !important" in styles
    assert "scrollbar-width: none" in styles and "*::-webkit-scrollbar" in styles
    assert 'data-back-to-top aria-label="回到顶部"' in index
    assert 'scrollPageToTop("smooth")' in script and ".back-to-top" in styles
    assert "requestAnimationFrame(() => scrollPageToTop())" in script
    assert ".analysis-code-box-manual" in styles
    assert "CURRENT PROFILE" not in script
    assert script.count('class="eyebrow"') == 4
    assert ".button,\n.button-primary,\n.button-secondary" in styles
    assert 'class="is-starting"' in index
    assert "startup-accent" not in index + styles
    assert "html.is-starting" in index
    assert "finishStartupSplash" in script
    assert 'new Event("prophetwindowshown")' in launcher
    assert 'addEventListener("prophetwindowshown", startStartupSplash' in script
    assert 'classList.add("is-playing")' in script
    assert 'classList.remove("is-starting")' in script
    assert "prefers-reduced-motion" in styles
    assert "hidden=True" in launcher
    assert "window.events.loaded += show_window" in launcher
    assert "pywebview.api" in script
    assert "streamlit" not in requirements.lower()
    assert "openai" not in requirements.lower()
    assert len(desktop.TRUSTED_SCRIPTS) == 3
    assert all(path.is_file() for path in desktop.TRUSTED_SCRIPTS)


def test_stdlib_llm_client_preserves_api_shapes() -> None:
    calls = []
    original = analysis.urllib.request.urlopen

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if request.full_url.endswith("/responses"):
            return _UrlopenResponse({
                "status": "completed",
                "output": [{"content": [{"type": "output_text", "text": "response text"}]}],
            })
        return _UrlopenResponse({"choices": [{"message": {"content": "chat text"}}]})

    analysis.urllib.request.urlopen = fake_urlopen
    try:
        client = analysis._HttpClient("secret", "https://example.test/v1/")
        response = client.responses.create(model="model", input="hello")
        chat = client.chat.completions.create(model="model", messages=[])
    finally:
        analysis.urllib.request.urlopen = original

    assert response.status == "completed"
    assert response.output_text == "response text"
    assert chat.choices[0].message.content == "chat text"
    assert [call[0].full_url for call in calls] == [
        "https://example.test/v1/responses",
        "https://example.test/v1/chat/completions",
    ]
    assert all(call[0].get_header("Authorization") == "Bearer secret" for call in calls)
    assert all(call[1] == analysis.DEFAULT_LLM_TIMEOUT for call in calls)



def test_delete_person_cascades_without_touching_other_people() -> None:
    with TemporaryDirectory() as temporary_directory:
        db_path = Path(temporary_directory) / "sentiment.db"
        storage.init_db(db_path)
        alice_id = storage.create_person(db_path, "Alice")
        bob_id = storage.create_person(db_path, "Bob")
        _seed_related_rows(db_path, alice_id)

        assert storage.delete_person(db_path, alice_id)
        assert storage.get_person(db_path, alice_id) is None
        assert storage.get_person(db_path, bob_id) is not None

        connection = storage.connect(db_path)
        try:
            for table in ("entries", "profiles", "profile_revisions", "predictions"):
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE person_id = ?", (alice_id,)
                ).fetchone()[0]
                assert count == 0, (table, count)
        finally:
            connection.close()


def _sample_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length 47 >>\nstream\nBT /F1 12 Tf 72 720 Td (PDF sample) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    pdf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return pdf


def _sample_docx() -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph("DOCX sample paragraph")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "姓名"
    table.rows[0].cells[1].text = "Alice"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _sample_xlsx() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    worksheet.append(["姓名", "情绪"])
    worksheet.append(["Alice", "平静"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def test_empty_names_are_rejected() -> None:
    with TemporaryDirectory() as temporary_directory:
        db_path = Path(temporary_directory) / "sentiment.db"
        storage.init_db(db_path)
        try:
            storage.create_person(db_path, "   ")
        except ValueError:
            pass
        else:
            raise AssertionError("空名称应被拒绝")


def test_text_analysis_saves_evidence_and_increments_profile() -> None:
    old_model = os.environ.get("LLM_MODEL")
    os.environ["LLM_MODEL"] = "test-model"
    try:
        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "sentiment.db"
            storage.init_db(db_path)
            person_id = storage.create_person(db_path, "Alice")
            client = _FakeClient()

            first = analysis.analyze_and_save(
                str(db_path),
                person_id,
                source_name="第一条",
                context="聊天",
                content="他说：我今天很平静。",
                client=client,
            )
            assert first["entry_id"] == 1
            assert first["profile_version"] == 1
            assert storage.get_profile(db_path, person_id)["version"] == 1
            assert storage.get_profile(db_path, person_id)["profile"]["emotion_patterns"][0][
                "evidence_entry_ids"
            ] == [1]
            assert storage.get_entry(db_path, 1)["analysis_json"] is not None
            first_material_prompt = next(
                call["input"]
                for call in client.responses.calls
                if call["text"]["format"]["name"] == "material_analysis"
            )
            first_profile_prompt = next(
                call["input"]
                for call in client.responses.calls
                if call["text"]["format"]["name"] == "person_profile"
            )
            for prompt in (first_material_prompt, first_profile_prompt):
                assert '"person_name": "Alice"' in prompt
                assert '"material_title": "第一条"' in prompt
                assert '"context": "聊天"' in prompt
                assert '"occurred_at"' not in prompt

            second = analysis.analyze_and_save(
                str(db_path),
                person_id,
                source_name="第二条",
                occurred_at="2026-01-02",
                content="他说：我仍然愿意直接沟通。",
                client=client,
            )
            profile = storage.get_profile(db_path, person_id)
            assert second["entry_id"] == 2
            assert profile["version"] == 2
            assert profile["profile"]["emotion_patterns"][0]["evidence_entry_ids"] == [1, 2]
            assert storage.get_entry(db_path, 1)["occurred_at"] is None
            assert storage.get_entry(db_path, 2)["occurred_at"] == "2026-01-02"
            second_material_prompt = [
                call["input"]
                for call in client.responses.calls
                if call["text"]["format"]["name"] == "material_analysis"
            ][1]
            second_profile_prompt = [
                call["input"]
                for call in client.responses.calls
                if call["text"]["format"]["name"] == "person_profile"
            ][1]
            assert '"material_title": "第二条"' in second_material_prompt
            assert '"occurred_at": "2026-01-02"' in second_material_prompt
            assert '"material_title": "第二条"' in second_profile_prompt
            assert '"occurred_at": "2026-01-02"' in second_profile_prompt

            assert storage.find_duplicate(
                db_path, person_id, storage.content_hash("他说：我今天很平静。")
            )["id"] == 1
            other_person_id = storage.create_person(db_path, "Bob")
            assert storage.find_duplicate(
                db_path, other_person_id, storage.content_hash("他说：我今天很平静。")
            ) is None
            assert all(call["store"] is False for call in client.responses.calls)
    finally:
        if old_model is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = old_model


def test_invalid_analysis_does_not_write_a_pending_entry_or_profile() -> None:
    old_model = os.environ.get("LLM_MODEL")
    os.environ["LLM_MODEL"] = "test-model"
    try:
        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "sentiment.db"
            storage.init_db(db_path)
            person_id = storage.create_person(db_path, "Alice")
            client = _InvalidClient()
            try:
                analysis.analyze_and_save(
                    str(db_path), person_id, content="无法解析", client=client
                )
            except analysis.AnalysisError:
                pass
            else:
                raise AssertionError("非法模型输出应失败")
            assert client.responses.calls == 2
            assert storage.get_profile(db_path, person_id) is None
            connection = storage.connect(db_path)
            try:
                assert connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0
            finally:
                connection.close()
    finally:
        if old_model is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = old_model


def test_supported_file_parsers_and_upload_protection() -> None:
    samples = {
        "note.txt": ("text/plain", "TXT sample", b"TXT sample"),
        "note.md": ("text/markdown", "# MD sample", b"# MD sample"),
        "table.csv": ("text/csv", "Alice | calm", "name,feeling\nAlice,calm".encode()),
        "data.json": ("application/json", '"name": "Alice"', b'{"name": "Alice"}'),
        "note.pdf": ("application/pdf", "PDF sample", _sample_pdf()),
        "note.docx": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "DOCX sample paragraph",
            _sample_docx(),
        ),
        "note.xlsx": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Alice",
            _sample_xlsx(),
        ),
    }
    for filename, (mime_type, expected, data) in samples.items():
        parsed = parsers.parse_file(filename, data, mime_type=mime_type)
        assert expected in parsed.text, (filename, parsed.text)
        assert parsed.name == filename

    encoded = "中文编码".encode("gb18030")
    try:
        parsers.parse_file("gb.txt", encoded, mime_type="text/plain")
    except parsers.EncodingRequiredError:
        pass
    else:
        raise AssertionError("非 UTF-8 文本应要求选择编码")
    assert parsers.parse_file(
        "gb.txt", encoded, mime_type="text/plain", encoding="gb18030"
    ).text == "中文编码"

    for filename, data in (
        ("empty.txt", b" \r\n"),
        ("bad.json", b"{bad"),
        ("bad.pdf", b"not a pdf"),
        ("bad.docx", b"not a docx"),
        ("bad.xlsx", b"not an xlsx"),
    ):
        try:
            parsers.parse_file(filename, data)
        except parsers.ParserError:
            pass
        else:
            raise AssertionError(f"损坏或空文件应被拒绝: {filename}")

    try:
        parsers.parse_file("large.txt", b"123", max_bytes=2)
    except parsers.FileTooLargeError:
        pass
    else:
        raise AssertionError("超大文件应被拒绝")


def test_long_text_is_split_with_overlap_and_merged() -> None:
    text = "\n\n".join(f"段落 {index}: " + "内容 " * 30 for index in range(6))
    chunks = analysis.split_text(text, max_chars=120, overlap_chars=20)
    assert len(chunks) > 1
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert chunks[0][-10:] in chunks[1]

    old_model = os.environ.get("LLM_MODEL")
    old_chunk_size = os.environ.get("MAX_CHUNK_CHARS")
    old_overlap = os.environ.get("CHUNK_OVERLAP_CHARS")
    os.environ["LLM_MODEL"] = "test-model"
    os.environ["MAX_CHUNK_CHARS"] = "120"
    os.environ["CHUNK_OVERLAP_CHARS"] = "20"
    try:
        client = _FakeClient()
        result = analysis.analyze_material(text, client=client)
        assert result["source_summary"]
        assert any(
            call["text"]["format"]["name"] == "material_analysis_merge"
            for call in client.responses.calls
        )
    finally:
        if old_model is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = old_model
        if old_chunk_size is None:
            os.environ.pop("MAX_CHUNK_CHARS", None)
        else:
            os.environ["MAX_CHUNK_CHARS"] = old_chunk_size
        if old_overlap is None:
            os.environ.pop("CHUNK_OVERLAP_CHARS", None)
        else:
            os.environ["CHUNK_OVERLAP_CHARS"] = old_overlap


def test_prediction_tracks_profile_version_and_review_updates_profile() -> None:
    old_model = os.environ.get("LLM_MODEL")
    os.environ["LLM_MODEL"] = "test-model"
    try:
        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "sentiment.db"
            storage.init_db(db_path)
            person_id = storage.create_person(db_path, "Alice")
            client = _FakeClient()
            analysis.analyze_and_save(
                str(db_path), person_id, content="第一条材料", client=client
            )
            analysis.analyze_and_save(
                str(db_path), person_id, content="第二条材料", client=client
            )

            prediction = analysis.predict_and_save(
                str(db_path),
                person_id,
                "假设临时改变原定安排。",
                profile_version=1,
                client=client,
            )
            assert prediction["prediction_id"] == 1
            assert prediction["profile_version"] == 1
            saved_prediction = storage.get_prediction(db_path, 1)
            assert saved_prediction["profile_version"] == 1
            assert len(saved_prediction["prediction"]["likely_reactions"]) == 2
            prediction_prompt = next(
                call["input"]
                for call in client.responses.calls
                if call["text"]["format"]["name"] == "prediction"
            )
            assert '<person_context>\n{"person_name": "Alice"}' in prediction_prompt

            review = analysis.review_and_save(
                str(db_path),
                person_id,
                1,
                "实际结果是对方先询问原因，稍后才继续沟通。",
                client=client,
            )
            assert review["prediction_id"] == 1
            assert review["profile_version"] == 3
            saved_prediction = storage.get_prediction(db_path, 1)
            assert saved_prediction["actual_outcome"]
            assert saved_prediction["review"]["assessment"] == "partially_matched"
            actual_entry = storage.get_entry(db_path, review["actual_entry_id"])
            assert actual_entry["entry_type"] == "actual_outcome"
            assert actual_entry["analysis_json"] is not None
            profile = storage.get_profile(db_path, person_id)
            assert profile["version"] == 3
            assert profile["profile"]["emotion_patterns"][0]["evidence_entry_ids"] == [
                1,
                2,
                3,
            ]
            assert [
                call["text"]["format"]["name"] for call in client.responses.calls
            ].count("prediction") == 1
            assert [
                call["text"]["format"]["name"] for call in client.responses.calls
            ].count("prediction_review") == 1
            review_prompt = next(
                call["input"]
                for call in client.responses.calls
                if call["text"]["format"]["name"] == "prediction_review"
            )
            assert '<person_context>\n{"person_name": "Alice"}' in review_prompt
    finally:
        if old_model is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = old_model


def test_delete_prediction_is_scoped_and_keeps_actual_material() -> None:
    with TemporaryDirectory() as temporary_directory:
        db_path = Path(temporary_directory) / "sentiment.db"
        storage.init_db(db_path)
        alice_id = storage.create_person(db_path, "Alice")
        bob_id = storage.create_person(db_path, "Bob")
        with storage.transaction(db_path) as connection:
            actual_entry_id = storage.insert_entry(
                connection,
                person_id=alice_id,
                entry_type="actual_outcome",
                source_name="预测 #1 实际结果",
                occurred_at=None,
                context="复盘",
                content="实际结果",
            )
            alice_prediction_id = storage.insert_prediction(
                connection,
                person_id=alice_id,
                profile_version=1,
                event_text="Alice 的事件",
                prediction=_prediction_payload(),
            )
            bob_prediction_id = storage.insert_prediction(
                connection,
                person_id=bob_id,
                profile_version=1,
                event_text="Bob 的事件",
                prediction=_prediction_payload(),
            )

        assert storage.delete_prediction(db_path, alice_id, alice_prediction_id)
        assert storage.get_prediction(db_path, alice_prediction_id) is None
        assert storage.get_entry(db_path, actual_entry_id) is not None
        assert storage.get_prediction(db_path, bob_prediction_id) is not None
        assert not storage.delete_prediction(db_path, bob_id, alice_prediction_id)
        assert not storage.delete_prediction(db_path, alice_id, alice_prediction_id)


def test_history_controls_rebuild_export_and_backup() -> None:
    old_model = os.environ.get("LLM_MODEL")
    os.environ["LLM_MODEL"] = "test-model"
    try:
        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "sentiment.db"
            storage.init_db(db_path)
            person_id = storage.create_person(db_path, "Alice", "备注")
            client = _FakeClient()
            first = analysis.analyze_and_save(
                str(db_path), person_id, content="第一条材料", client=client
            )
            second = analysis.analyze_and_save(
                str(db_path),
                person_id,
                source_name="第二条",
                occurred_at="2026-01-02",
                content="第二条材料",
                client=client,
            )

            assert storage.set_entry_active(db_path, person_id, first["entry_id"], False)
            rebuild = analysis.rebuild_profile(
                str(db_path), person_id, client=client
            )
            assert rebuild["active_entry_ids"] == [second["entry_id"]]
            assert rebuild["profile_version"] == 3
            rebuild_prompts = [
                call["input"]
                for call in client.responses.calls
                if call["text"]["format"]["name"]
                in {"material_analysis", "person_profile"}
            ][4:]
            assert all('"person_name": "Alice"' in prompt for prompt in rebuild_prompts)
            assert all('"material_title": "第二条"' in prompt for prompt in rebuild_prompts)
            assert all('"occurred_at": "2026-01-02"' in prompt for prompt in rebuild_prompts)
            profile = storage.get_profile(db_path, person_id)
            assert profile["profile"]["emotion_patterns"][0]["evidence_entry_ids"] == [
                second["entry_id"]
            ]

            restored = analysis.restore_profile(str(db_path), person_id, 1)
            assert restored["profile_version"] == 4
            assert restored["restored_from_version"] == 1
            assert storage.get_profile(db_path, person_id)["profile"] == storage.get_profile_revision(
                db_path, person_id, 1
            )["profile"]

            bundle = storage.export_person(db_path, person_id)
            assert bundle["person"]["name"] == "Alice"
            assert len(bundle["entries"]) == 2
            assert len(bundle["profile_revisions"]) == 4
            backup = storage.backup_database(db_path)
            assert backup.startswith(b"SQLite format 3")
            backup_path = Path(temporary_directory) / "backup.db"
            backup_path.write_bytes(backup)
            connection = storage.connect(backup_path)
            try:
                assert connection.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1
            finally:
                connection.close()

            replacement_path = Path(temporary_directory) / "replacement.db"
            storage.init_db(replacement_path)
            storage.create_person(replacement_path, "Bob")
            storage.restore_database(replacement_path, backup)
            assert [item["name"] for item in storage.list_people(replacement_path)] == ["Alice"]
            try:
                storage.restore_database(replacement_path, b"not a database")
            except ValueError:
                pass
            else:
                raise AssertionError("非法数据库备份应被拒绝")
            assert [item["name"] for item in storage.list_people(replacement_path)] == ["Alice"]
    finally:
        if old_model is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = old_model


def main() -> None:
    test_local_env_file_loading_preserves_environment_priority()
    test_background_job_runs_outside_the_page_call()
    test_desktop_uses_native_assets_without_http_service()
    test_stdlib_llm_client_preserves_api_shapes()
    test_people_persist_and_stay_isolated()
    test_delete_person_cascades_without_touching_other_people()
    test_empty_names_are_rejected()
    test_text_analysis_saves_evidence_and_increments_profile()
    test_invalid_analysis_does_not_write_a_pending_entry_or_profile()
    test_supported_file_parsers_and_upload_protection()
    test_long_text_is_split_with_overlap_and_merged()
    test_prediction_tracks_profile_version_and_review_updates_profile()
    test_delete_prediction_is_scoped_and_keeps_actual_material()
    test_history_controls_rebuild_export_and_backup()
    print("stage-A/B/C/D/E core checks passed")


if __name__ == "__main__":
    main()
