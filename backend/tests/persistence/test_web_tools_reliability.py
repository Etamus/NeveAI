import asyncio
import io
import json
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch


def test_untargeted_formatting_change_is_detected_inside_edited_part(monkeypatch):
    from docx import Document
    from neveai.utils import document_edits as edits
    doc = Document()
    doc.add_paragraph("Requested")
    doc.add_paragraph("Untouched").runs[0].bold = True
    stream = io.BytesIO()
    doc.save(stream)
    snapshot = inspect_document(stream.getvalue(), "docx")
    original = edits._replace_runs
    def damage(nodes, old, new):
        original(nodes, old, new)
        for bold in nodes[0].getroottree().findall(".//{" + edits.W + "}b"):
            bold.getparent().remove(bold)
    monkeypatch.setattr(edits, "_replace_runs", damage)
    with pytest.raises(DocumentEditError, match="nao selecionado"):
        apply_document_edits(snapshot, [{"id": snapshot.elements[0]["id"], "old_text":"Requested", "new_text":"Replaced"}])

import pytest

spec = importlib.util.spec_from_file_location('web_under_test', Path(__file__).parents[2] / 'neveai/retrieval/web/research.py')
web = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'neveai.utils.url': NS(validate_url=lambda url: True)}):
    spec.loader.exec_module(web)
from neveai.utils.document_edit_planner import propose_document_edits, resolve_exact_edit_targets
from neveai.utils.document_edits import inspect_document, apply_document_edits, DocumentEditError


@pytest.mark.parametrize('question,expected', [
    ('noticias de hoje', 'day'), ('news last week', 'week'),
    ('relatorios do ultimo mes', 'month'), ('dados dos ultimos 12 meses', 'year'),
    ('versao mais recente', ''), ('historia em 2020', ''), ('compare duas linguagens', ''),
    ('Compare 2020 com hoje', ''), ('Desde janeiro ate hoje', ''),
])
def test_explicit_recency(question, expected):
    assert web.requested_time_range(question) == expected


def test_pdf_text_and_page_provenance():
    from fpdf import FPDF
    pdf = FPDF()
    for value in ('First source page', 'Second source page'):
        pdf.add_page(); pdf.set_font('Helvetica', size=12); pdf.cell(0, 10, value)
    result = web.extract_pdf(bytes(pdf.output()), 'https://example.org/source.pdf')
    assert '[Page 1]' in result['content'] and '[Page 2]' in result['content']
    assert 'Second source page' in result['content']
    assert result['metadata']['pages'] == 2
    assert result['metadata']['partial_document'] is False
    with pytest.raises(Exception):
        web.extract_pdf(b'not pdf', 'https://example.org/broken.pdf')


@pytest.mark.parametrize('deep', [False, True])
@pytest.mark.parametrize('short_pdf', [False, True])
def test_failed_pages_replaced_before_snippets(monkeypatch, deep, short_pdf):
    web._searches.clear()
    async def read(session, url, *args):
        if url.endswith('/0') or url.endswith('/1'):
            return None
        return {'content': 'Short PDF' if short_pdf else 'Reliable source content. ' * 10,
                'metadata': {'source': url, 'title': url, 'format': 'pdf' if short_pdf else 'html'}}
    reader = AsyncMock(side_effect=read)
    monkeypatch.setattr(web, 'read_page', reader)
    request = NS(state=NS(deep_search_enabled=deep), app=NS(state=NS(config=NS(
        ENABLE_WEB_LOADER_SSL_VERIFICATION=True, WEB_SEARCH_TRUST_ENV=False,
        WEB_SEARCH_ENGINE='test', WEB_SEARCH_RESULT_COUNT=8, WEB_SEARCH_DOMAIN_FILTER_LIST=[],
        DDGS_BACKEND='auto', SEARXNG_QUERY_URL='', BYPASS_WEB_SEARCH_WEB_LOADER=False,
    ))))
    form = NS(max_loaded_urls=4, urls=[], question='', queries=['test'], engine=None,
              result_count=8, search_after_urls=False)
    search = AsyncMock(return_value=[{'link': f'https://site{i}.org/{i}', 'title': 'Source',
                                     'snippet': 'Snippet only'} for i in range(8)])
    result = asyncio.run(web.research(request, form, None, search))
    assert result['pages_read_count'] == 4
    assert result['snippet_count'] == 0
    assert reader.await_count == 6


def test_private_url_never_fetched(monkeypatch):
    monkeypatch.setattr(web, 'validate_url', lambda url: False)
    class Session:
        def get(self, *args, **kwargs):
            raise AssertionError('Private URL fetched')
    assert asyncio.run(web.read_page(Session(), 'http://127.0.0.1/secret')) is None


@pytest.mark.parametrize('fmt', ['txt', 'docx', 'pptx', 'pdf'])
def test_substring_edit_preserves_surrounding_content(fmt):
    text = 'Before: Marina lives in Santos. After stays unchanged.'
    if fmt == 'txt':
        data = text.encode()
    elif fmt == 'docx':
        from docx import Document
        doc = Document(); doc.add_paragraph(text); stream = io.BytesIO(); doc.save(stream); data = stream.getvalue()
    elif fmt == 'pptx':
        from pptx import Presentation
        doc = Presentation(); slide = doc.slides.add_slide(doc.slide_layouts[1]); slide.shapes.title.text = text
        stream = io.BytesIO(); doc.save(stream); data = stream.getvalue()
    else:
        from fpdf import FPDF
        doc = FPDF(); doc.add_page(); doc.set_font('Helvetica', size=12); doc.cell(0, 10, text); data = bytes(doc.output())
    snapshot = inspect_document(data, fmt)
    element = next(e for e in snapshot.elements if 'Santos' in e['text'])
    complete = AsyncMock(return_value={'edits': [{'id': element['id'], 'old_text': 'Santos',
        'new_text': 'Recife', 'value_type': 'text'}]})
    changes = asyncio.run(propose_document_edits(snapshot, 'Atualize a cidade de residencia', complete))
    output = apply_document_edits(snapshot, changes)
    # The edit API returns bytes and an audit object.
    edited = inspect_document(output[0] if isinstance(output, tuple) else output, fmt)
    assert any('Marina lives in Recife. After stays unchanged.' in e['text'] for e in edited.elements)
    assert complete.await_count == 1


def test_target_recovery_is_exact_and_unambiguous():
    allowed = {'a': {'id': 'a', 'text': 'Original'}, 'b': {'id': 'b', 'text': 'Other'}}
    proposal = [{'id': 'invented', 'old_text': 'Original', 'new_text': 'Changed', 'value_type': 'text'}]
    assert resolve_exact_edit_targets(proposal, allowed)[0]['id'] == 'a'
    assert proposal[0]['id'] == 'invented'
    assert resolve_exact_edit_targets(proposal, allowed, [*allowed.values(), {'id': 'other-batch', 'text': 'Original'}])[0]['id'] == 'invented'
    allowed['c'] = {'id': 'c', 'text': 'Original'}
    assert resolve_exact_edit_targets(proposal, allowed)[0]['id'] == 'invented'


def test_no_guessing_cells_styles_or_repeated_substrings():
    for target, edit in [
        ({'id': 'a', 'text': '10', 'cell': 'A1'}, {'old_text': '1', 'new_text': '2'}),
        ({'id': 'a', 'text': 'Name Name'}, {'old_text': 'Name', 'new_text': 'Other'}),
        ({'id': 'a', 'text': 'Name Last'}, {'old_text': 'Name', 'new_text': 'Other', 'style': {'bold': True}}),
    ]:
        edit.update(id='a', value_type='text')
        assert resolve_exact_edit_targets([edit], {'a': target}) == [edit]


def test_invalid_proposal_still_repaired_and_validated():
    snapshot = inspect_document(b'Original', 'txt')
    complete = AsyncMock(side_effect=[{'edits': [{'id': 'wrong', 'old_text': 'Missing', 'new_text': 'Changed', 'value_type': 'text'}]},
                                     {'edits': [{'id': 'line1', 'old_text': 'Original', 'new_text': 'Changed', 'value_type': 'text'}]}])
    changes = asyncio.run(propose_document_edits(snapshot, 'Atualize o conteudo', complete))
    assert changes[0]['new_text'] == 'Changed'
    assert complete.await_count == 2


@pytest.mark.parametrize('confidences,expected_calls,success', [([0.9], 1, True), ([0.4, 0.8], 2, True), ([0, 0.8], 2, True), ([0.3, 0.4], 2, False)])
def test_ocr_recovery_is_bounded(monkeypatch, tmp_path, confidences, expected_calls, success):
    from neveai.utils import pdf_document_text as module
    import pypdf
    import pypdfium2
    from PIL import Image
    path = tmp_path / 'scan.pdf'; path.write_bytes(b'fixture')
    monkeypatch.setattr(pypdf, 'PdfReader', lambda path: NS(is_encrypted=False, pages=[NS(images=[1], extract_text=lambda **kwargs: '')]))
    scales, closed = [], []
    class Page:
        def get_size(self): return (1000, 1000)
        def render(self, scale):
            scales.append(scale)
            return NS(to_pil=lambda: Image.new('RGB', (10, 10)), close=lambda: closed.append(True))
        def close(self): pass
    class Document:
        def __init__(self, *args): pass
        def __getitem__(self, index): return Page()
        def close(self): pass
    monkeypatch.setattr(pypdfium2, 'PdfDocument', Document)
    values = iter(confidences)
    def engine(array):
        confidence = next(values)
        return ([[None, 'Recovered text', confidence]] if confidence else None), None
    with patch.dict(sys.modules, {'rapidocr_onnxruntime': NS(RapidOCR=lambda **kwargs: engine)}):
        module._read_pdf.cache_clear()
        if success:
            result = module.read_pdf_document(str(path))
            assert result['pages'][0]['text'] == 'Recovered text'
            assert result['pages'][0]['ocr_confidence'] >= 0.6
        else:
            with pytest.raises(ValueError, match='confianca'):
                module.read_pdf_document(str(path))
        assert len(scales) == len(closed) == expected_calls
        assert scales == [2, 3][:expected_calls]
        module._read_pdf.cache_clear()


def test_native_neve_session_roundtrip():
    from fastapi import FastAPI, Request
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.testclient import TestClient
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key='isolated-test-key', session_cookie='neve-session')
    @app.get('/')
    def endpoint(request: Request):
        request.session['visits'] = request.session.get('visits', 0) + 1
        return {'visits': request.session['visits']}
    with TestClient(app) as client:
        assert client.get('/').json()['visits'] == 1
        assert 'neve-session' in client.cookies
        assert client.get('/').json()['visits'] == 2
        client.cookies.clear()
        assert client.get('/', headers={'cookie': 'unrelated-session=invalid'}).json()['visits'] == 1
