"""Exercise production routing without importing the application or its database."""
import ast
import asyncio
import html
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Optional
import unicodedata
from unittest.mock import AsyncMock, Mock
from urllib.parse import unquote, urlsplit, urlunsplit

import pytest


def router():
    path = Path(__file__).parent / "neveai/utils/middleware.py"
    names = {"normalize_web_search_intent_text", "web_search_intent_decision",
             "should_run_web_search_for_message", "resolve_web_search_decision", "document_research_query"}
    nodes = [node for node in ast.parse(path.read_text(encoding="utf-8")).body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
             or isinstance(node, ast.Assign) and any(
                 isinstance(target, ast.Name) and target.id.startswith("WEB_SEARCH_")
                 for target in node.targets)]
    scope = dict(re=re, html=html, json=json, unicodedata=unicodedata, unquote=unquote,
                 Any=Any, Optional=Optional, asyncio=asyncio, log=Mock(),
                 TASKS=SimpleNamespace(QUERY_GENERATION="query_generation"),
                 generate_chat_completion=AsyncMock(), _load_model_json=json.loads,
                 _get_json_response_content=lambda response: response)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope


@pytest.mark.parametrize("text, expected", [
    ("Dolar hoje", True), ("Clima agora", True), ("Bitcoin hoje", True),
    ("Preciso de precos atualizados de placas de video", True),
    ("Qual o tempo em Sao Paulo?", True), ("Cotacao", True),
    ("Pesquise a capital da Franca", True), ("Compare os modelos com fontes", True),
    ("Leia https://example.org/artigo", True), ("Inclua referencias", True),
    ('Leia "https://example.org/artigo"', True),
    ('"https://example.org/artigo"', True),
    ("Analise meu investimento hoje", True),
    ("Latest Python release", True), ("Weather tomorrow", True),
    ("Como melhorar este poema?", False), ("Crie uma historia sobre o clima", False),
    ("Escreva um poema sobre as noticias de hoje", False),
    ('Traduza: "Pesquise o dolar hoje"', False),
    ('Corrija este texto: "o preco subiu hoje"', False),
    ("Explique este codigo:\n```python\nsearch('weather today')\n```", False),
    ("Sem pesquisar, explique a inflacao", False),
    ("Nao use a internet para responder quem e o presidente", False),
    ("Do not browse; explain current events from this document", False),
    ("Don't search for the latest news", False),
    ("Bom dia!", False), ("Obrigado", False), ("", False), (None, False),
    ("Qual a capital da Franca?", None), ("O que e fotossintese?", None),
    ("Explique recursao", None), ("Sugira uma placa de video", True),
    ("Qual a melhor temporada de GOT?", True),
    ("Quais os melhores livros de ficcao cientifica?", True),
    ("Which is the best season of Breaking Bad?", True),
    ("Qual o melhor notebook para trabalhar?", True),
    ("Recomende filmes de ficcao cientifica", True),
    ("Quais os piores aeroportos para conexoes?", True),
    ("Sem pesquisar, recomende filmes de ficcao cientifica", False),
    ("Sem pesquisar, qual a melhor temporada de GOT?", False),
    ("Crie uma historia sobre a melhor temporada de GOT", False),
    ("Analise este texto e diga qual o melhor titulo", False),
    ("Reescreva meu texto e pesquise fontes para verificar os fatos", True),
    ("Explique recursao\n\nPesquise fontes para conferir", True),
    ("Qual a cidade mais divertida da franca?", True),
    ("Tem alguma mais divertida?", True),
    ("Quais os lugares menos movimentados para viajar?", True),
    ("Which camera has the most reliable autofocus?", True),
    ("What is the least crowded airport?", True),
    ("Is there something more comfortable?", True),
    ("Qual restaurante tem mais opcoes vegetarianas?", True),
    ("Crie uma historia sobre a cidade mais divertida", False),
    ("Analise este texto: qual o trecho mais longo?", False),
    ('Traduza: "Which camera has the most reliable autofocus?"', False),
    ("Sem pesquisar, qual a cidade mais divertida?", False),
    ("Qual o trecho mais longo deste texto?", False),
    ("Which function is the most complex in this code?", False),
    ("Qual a frase menos clara neste documento?", False),
    ("Pesquise quais as informacoes mais atuais neste documento", True),
])
def test_local_decision(text, expected):
    assert router()["web_search_intent_decision"](text) is expected


def test_comparative_followup_keeps_previous_user_subject_not_assistant_drift():
    scope = router()
    path = Path(__file__).parent / "neveai/utils/middleware.py"
    names = {"is_contextual_search_follow_up", "is_web_model_discovery_follow_up", "build_primary_web_search_query"}
    nodes = [node for node in ast.parse(path.read_text(encoding="utf-8")).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in nodes:
        node.body = [statement for statement in node.body if not (
            isinstance(statement, ast.ImportFrom) and statement.module == "neveai.retrieval.web.research")]
    research = path.parents[1] / "retrieval/web/research.py"
    nodes.extend(node for node in ast.parse(research.read_text(encoding="utf-8")).body
                 if isinstance(node, ast.FunctionDef) and node.name == "extract_request_urls")
    scope.update(sanitize_generated_search_query=lambda value: value,
                 get_content_from_message=lambda message: message["content"], urlsplit=urlsplit, urlunsplit=urlunsplit)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    messages = [{"role": "user", "content": "Qual a cidade mais divertida da franca?"},
                {"role": "assistant", "content": "A resposta incorreta mudou para nomes de cidades engraçados."},
                {"role": "user", "content": "Tem alguma mais divertida?"}]
    assert scope["is_contextual_search_follow_up"](messages[-1]["content"])
    query = scope["build_primary_web_search_query"](messages[-1]["content"], messages)
    assert "cidade mais divertida da franca" in query
    assert "nomes de cidades" not in query


@pytest.mark.parametrize("text, expected", [
    ("Crie um PDF curto: qual a melhor temporada de GOT? Inclua fontes", "qual a melhor temporada de GOT"),
    ("Faca um relatorio sobre baterias", "baterias"),
    ("Create a report about current processors. Include sources.", "current processors"),
    ("Crie um PDF sobre como criar arquivos PDF", "como criar arquivos PDF"),
    ("Qual o melhor criador de PDF?", "Qual o melhor criador de PDF?"),
    ("Leia https://example.com/arquivo.pdf", "Leia https://example.com/arquivo.pdf"),
    ("Crie um PDF", "Crie um PDF"),
])
def test_research_subject_excludes_deliverable_wrapper(text, expected):
    assert router()["document_research_query"](text) == expected


def test_ambiguous_requests_use_typed_model_decision():
    async def run():
        for decision in (True, False):
            scope = router()
            completion = scope["generate_chat_completion"]
            completion.return_value = json.dumps({"needs_search": decision})
            assert await scope["resolve_web_search_decision"](
                SimpleNamespace(app=object()), {"model": "selected-model"}, None,
                "Explique recursao", "Explique recursao") is decision
            payload = completion.call_args.kwargs["form_data"]
            assert payload["model"] == "selected-model"
            assert payload["no_think"] is True
            assert payload["stream"] is False
            assert payload["response_format"]["json_schema"]["strict"] is True
    asyncio.run(run())


@pytest.mark.parametrize("response", ['{"needs_search":"false"}', '{}', 'invalid'])
def test_invalid_classifier_output_falls_back(response):
    async def run():
        scope = router()
        scope["generate_chat_completion"].return_value = response
        assert await scope["resolve_web_search_decision"](
            SimpleNamespace(app=object()), {"model": "selected"}, None,
            "Qual a capital da Franca?", "Qual a capital da Franca?") is True
    asyncio.run(run())


def test_errors_and_cancellation():
    async def run():
        scope = router()
        scope["generate_chat_completion"].side_effect = TimeoutError()
        assert await scope["resolve_web_search_decision"](
            SimpleNamespace(app=object()), {"model": "selected"}, None,
            "Qual a capital da Franca?", "Qual a capital da Franca?") is True
        scope["generate_chat_completion"].side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await scope["resolve_web_search_decision"](
                SimpleNamespace(app=object()), {"model": "selected"}, None,
                "Qual a capital da Franca?", "Qual a capital da Franca?")
    asyncio.run(run())


def test_clear_decisions_and_deep_research_do_not_call_classifier():
    async def run():
        scope = router()
        request = SimpleNamespace(app=object())
        for question, deep, expected in [
            ("Dolar hoje", False, True), ("Como melhorar este poema?", False, False),
            ("Nao pesquise na web", False, False), ("Explique recursao", True, True),
            ("Bom dia", True, False),
        ]:
            assert await scope["resolve_web_search_decision"](
                request, {"model": "selected"}, None, question, question, deep) is expected
        scope["generate_chat_completion"].assert_not_awaited()
    asyncio.run(run())


def test_resolved_followup_respects_current_instruction():
    async def run():
        scope = router()
        assert await scope["resolve_web_search_decision"](
            SimpleNamespace(app=object()), {"model": "selected"}, None,
            "Sem pesquisar, resuma sua resposta", "precos atuais de GPU") is False
        assert await scope["resolve_web_search_decision"](
            SimpleNamespace(app=object()), {"model": "selected"}, None,
            "E hoje?", "Cotacao do dolar hoje") is True
    asyncio.run(run())


def test_handler_preserves_files_sources_and_status_contract():
    async def run():
        scope = router()
        path = Path(__file__).parent / "neveai/utils/middleware.py"
        handler = next(node for node in ast.parse(path.read_text(encoding="utf-8")).body
                       if isinstance(node, ast.AsyncFunctionDef) and node.name == "chat_web_search_handler")
        # Load the real URL helper without importing application config/DB state.
        handler.body = [node for node in handler.body if not (
            isinstance(node, ast.ImportFrom) and node.module == "neveai.retrieval.web.research")]
        research = path.parents[1] / "retrieval/web/research.py"
        helper = next(node for node in ast.parse(research.read_text(encoding="utf-8")).body
                      if isinstance(node, ast.FunctionDef) and node.name == "extract_request_urls")
        scope.update(urlsplit=urlsplit, urlunsplit=urlunsplit)
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(research), "exec"), scope)
        scope.update(Request=Any, get_last_user_message=lambda messages: messages[-1]["content"],
                     build_primary_web_search_query=lambda question, *args: question,
                     is_web_model_discovery_follow_up=lambda value: False,
                     is_contextual_search_follow_up=lambda value: False,
                     filter_web_search_queries=lambda queries, *args, **kwargs: queries,
                     sanitize_generated_search_queries=lambda queries, *args: queries,
                     ENABLE_QUERIES_CACHE=False, SearchForm=SimpleNamespace,
                     add_or_update_system_message=lambda text, messages: [
                         {"role": "system", "content": text}, *messages],
                     plan_chat_web_queries=AsyncMock(return_value=["Dolar hoje"]),
                     process_web_search=AsyncMock(return_value={
                         "status": True, "docs": [{"content": "Evidence", "metadata": {}}],
                         "filenames": ["https://example.org/evidence"], "items": [],
                         "pages_read_count": 1, "site_count": 1,
                     }))
        exec(compile(ast.Module(body=[handler], type_ignores=[]), str(path), "exec"), scope)
        events = AsyncMock()
        request = SimpleNamespace(state=SimpleNamespace(), app=object())
        upload = {"type": "file", "id": "existing-upload"}
        form = {"model": "selected", "messages": [{"role": "user", "content": "Dolar hoje"}],
                "files": [upload]}
        result = await scope["chat_web_search_handler"](
            request, form, {"__event_emitter__": events, "__features__": {}}, None)
        assert result["files"][0] == upload
        assert result["files"][1]["type"] == "web_search"
        assert result["files"][1]["urls"] == ["https://example.org/evidence"]
        assert events.await_args_list[0].args[0]["data"]["done"] is False
        assert events.await_args_list[-1].args[0]["data"]["done"] is True
        events.reset_mock()
        scope["process_web_search"].reset_mock()
        form = {"model": "selected", "messages": [{"role": "user", "content": "Como melhorar este poema?"}],
                "files": [upload]}
        result = await scope["chat_web_search_handler"](
            request, form, {"__event_emitter__": events, "__features__": {}}, None)
        assert result is form
        events.assert_not_awaited()
        scope["process_web_search"].assert_not_awaited()
        for question, expected_query in [
            ("O que esse link fala? https://www.reddit.com/r/ECE/comments/1rphq0l/free_stuff/?js_challenge=1&jsc_token=secret", "https://www.reddit.com/r/ECE/comments/1rphq0l/free_stuff/"),
            ("Resuma https://example.org/article?id=2&utm_source=mail&token=secret", "https://example.org/article?id=2"),
        ]:
            form = {"model": "selected", "messages": [{"role": "user", "content": question}], "files": [upload]}
            scope["process_web_search"].return_value = {"status": False, "unread_urls": [expected_query]}
            result = await scope["chat_web_search_handler"](
                request, form, {"__event_emitter__": events, "__features__": {}}, None)
            search = scope["process_web_search"].call_args.args[1]
            assert search.queries == [expected_query]
            assert result["files"] == [upload]
            assert any("could not be read" in message["content"] for message in result["messages"])
    asyncio.run(run())
