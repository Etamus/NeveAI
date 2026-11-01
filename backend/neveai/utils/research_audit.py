"""Ground a web-document review in actual draft spans and retrieved passages."""


def _normalize(text):
    return " ".join(str(text or "").split()).casefold()


def research_review_issues(review, draft, sources):
    if not isinstance(review, dict) or not isinstance(review.get("claim_checks"), list):
        raise ValueError("A revisao precisa identificar as afirmacoes verificadas.")
    if type(review.get("objective_failure")) is not bool:
        raise ValueError("A revisao precisa de um resultado objetivo valido.")
    passages = []
    for source in sources:
        documents = source.get("document") or []
        metadata = source.get("metadata") or []
        if isinstance(documents, str):
            documents = [documents]
        if isinstance(metadata, dict):
            metadata = [metadata]
        for index, document in enumerate(documents):
            meta = metadata[index] if index < len(metadata) and isinstance(metadata[index], dict) else {}
            urls = {str(meta.get(key) or "") for key in ("source", "link", "fetched_url")}
            passages.extend((url, _normalize(document)) for url in urls)
    normalized_draft = _normalize(draft)
    issues = []
    for check in review["claim_checks"]:
        if not isinstance(check, dict):
            raise ValueError("A verificacao de afirmacao precisa ser um objeto.")
        verdict = check.get("verdict")
        if verdict not in {"supported", "opinion", "unsupported", "contradicted"}:
            raise ValueError("A verificacao precisa de uma classificacao valida.")
        if verdict in {"supported", "opinion"}:
            continue
        claim = str(check.get("claim") or "").strip()
        normalized_claim = _normalize(claim)
        if not normalized_claim or normalized_claim not in normalized_draft:
            continue
        if verdict == "unsupported":
            if any(normalized_claim in passage for _, passage in passages):
                continue
            issues.append("Afirmação sem suporte nas fontes: " + claim)
        else:
            evidence = _normalize(check.get("evidence"))
            url = str(check.get("source") or "")
            if url and evidence and any(source_url == url and evidence in passage for source_url, passage in passages):
                issues.append("Afirmação em conflito com a fonte " + url + ": " + claim)
    if review.get("objective_failure"):
        issues.append(str(review.get("objective_issue") or "O documento nao atende ao pedido original.").strip())
    # A bare negative verdict cannot veto an answer without an actionable defect.
    return issues
