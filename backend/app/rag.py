import json
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from . import provider
from .config import settings
from .db import database


class Evidence(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    source_id: str
    quote: str = Field(min_length=12,max_length=1500)


class Claim(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    text: str = Field(min_length=1,max_length=2000)
    evidence: list[Evidence] = Field(min_length=1,max_length=6)


class Generated(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    answerable: bool
    claims: list[Claim] = Field(max_length=10)


def abstain(reason='insufficient_evidence'):
    return {'status':reason,'answer':'Insufficient evidence. Your sources do not support a reliable answer. Try a more specific question or add relevant documents.','claims':[],'sources':[]}


def validate_answer(raw: dict, sources: list[dict]) -> dict:
    try: parsed=Generated.model_validate(raw)
    except ValidationError: return abstain('invalid_evidence')
    if not parsed.answerable or not parsed.claims: return abstain()
    indexed={s['id']:s for s in sources}
    cited=[]
    for claim in parsed.claims:
        for item in claim.evidence:
            source=indexed.get(item.source_id)
            if not source or item.quote not in source['text']: return abstain('invalid_evidence')
            if item.source_id not in cited: cited.append(item.source_id)
    return {'status':'answered','answer':'\n\n'.join(c.text for c in parsed.claims),
            'claims':[c.model_dump() for c in parsed.claims], 'sources':[indexed[i] for i in cited]}


def answer(workspace_id, question):
    with database() as db:
        count=db.execute("SELECT count(*) AS n FROM documents WHERE workspace_id=%s AND status='ready' AND embedding_model=%s",
                         (workspace_id,settings().embedding_model)).fetchone()['n']
    if not count: return abstain()
    vector=provider.embed([question])[0]
    with database() as db:
        rows=db.execute('''SELECT c.id,c.document_id,c.text,c.page,d.name,
                    1-(c.embedding <=> %s::vector) AS similarity
                    FROM chunks c JOIN documents d ON d.id=c.document_id
                    WHERE c.workspace_id=%s AND d.workspace_id=%s AND d.status='ready' AND d.embedding_model=%s
                    ORDER BY c.embedding <=> %s::vector LIMIT 6''',
                    (json.dumps(vector),workspace_id,workspace_id,settings().embedding_model,json.dumps(vector))).fetchall()
    sources=[{**r,'id':str(r['id']),'document_id':str(r['document_id'])} for r in rows if r['similarity']>=settings().min_similarity]
    if not sources: return abstain()
    raw=provider.generate(question,[{'source_id':s['id'],'text':s['text']} for s in sources])
    result=validate_answer(raw,sources)
    if result['status']=='answered' and not provider.verify(question,result['claims']):
        return abstain('unsupported_claims')
    return result
