"""Ground semantic objections in the draft, not its future file container."""


def _normalized(value):
    return " ".join(str(value or "").split()).casefold()


def document_review_issues(review, draft, sources):
    if not isinstance(review, dict):
        raise ValueError("A revisao do documento precisa ser um objeto.")
    for field in ("approved", "objective_failure"):
        if type(review.get(field)) is not bool:
            raise ValueError("A revisao do documento precisa de resultados validos.")
    if not isinstance(review.get("missing_facts"), list) or not isinstance(review.get("invented_facts"), list):
        raise ValueError("A revisao do documento precisa identificar os problemas encontrados.")
    scope = review.get("objective_failure_scope")
    if scope not in {"none", "content", "container"}:
        raise ValueError("A revisao precisa distinguir conteudo e renderizacao.")
    if not isinstance(review.get("objective_issue"), str):
        raise ValueError("A revisao precisa descrever o problema objetivo.")
    normalized_draft = _normalized(draft)
    issues = []
    for missing in review["missing_facts"]:
        if not isinstance(missing, dict):
            raise ValueError("O trecho ausente precisa identificar sua fonte.")
        excerpt = str(missing.get("exact_text") or "").strip()
        normalized_excerpt = _normalized(excerpt)
        if not normalized_excerpt or normalized_excerpt in normalized_draft:
            continue
        source = next((item for item in sources if normalized_excerpt in _normalized(item.get("content"))), None)
        if source is not None:
            issues.append(f'Conteudo ausente de "{source.get("name") or "fonte"}": "{excerpt}"')
    for invented in review["invented_facts"]:
        if not isinstance(invented, str):
            raise ValueError("A afirmacao contestada precisa ser um trecho do rascunho.")
        if invented.strip() and _normalized(invented) in normalized_draft:
            issues.append("Conteudo inventado: " + invented.strip())
    if review["objective_failure"] and scope == "content":
        issue = review["objective_issue"].strip()
        if not issue:
            raise ValueError("A falha de conteudo precisa de uma descricao para ser corrigida.")
        issues.append(issue)
    # The renderer validates the actual container later; a negative boolean is not evidence.
    return list(dict.fromkeys(issues))
