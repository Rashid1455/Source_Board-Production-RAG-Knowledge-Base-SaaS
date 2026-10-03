import copy
import pytest
from app.extraction import extract, chunk_pages
from app.rag import validate_answer
from app import provider

SOURCES=[{'id':'source-1','text':'Employees may work remotely three days per week. Manager approval is required.',
          'document_id':'document-1','name':'Policy.pdf','page':2}]
VALID={'answerable':True,'claims':[{'text':'Employees can work remotely three days per week.',
      'evidence':[{'source_id':'source-1','quote':'Employees may work remotely three days per week.'}]}]}


def test_verified_quotes_preserve_real_citations():
    result=validate_answer(VALID,SOURCES)
    assert result['status']=='answered'
    assert result['sources'][0]['page']==2
    assert result['claims'][0]['evidence'][0]['quote'] in SOURCES[0]['text']


@pytest.mark.parametrize('kind',['invented_source','invented_quote','no_citation','empty_answer','bad_schema','refusal'])
def test_fails_closed(kind):
    raw=copy.deepcopy(VALID)
    if kind=='invented_source': raw['claims'][0]['evidence'][0]['source_id']='another-tenant-source'
    if kind=='invented_quote': raw['claims'][0]['evidence'][0]['quote']='Work remotely every day without permission.'
    if kind=='no_citation': raw['claims'][0]['evidence']=[]
    if kind=='empty_answer': raw['claims']=[]
    if kind=='bad_schema': raw={'answerable':'yes'}
    if kind=='refusal': raw['answerable']=False
    result=validate_answer(raw,SOURCES)
    assert result['status']!='answered'
    assert not result['sources'] and not result['claims']


def test_page_aware_chunks_are_bounded_and_overlap():
    chunks=chunk_pages(['a'*2800,'Second page contains the policy.'])
    assert [c['page'] for c in chunks]==[1,1,1,2]
    assert max(len(c['text']) for c in chunks)<=1500
    assert chunks[0]['text'][-300:]==chunks[1]['text'][:300]
    assert chunks[-1]['text']=='Second page contains the policy.'


@pytest.mark.parametrize(('name','content'),[('x.exe',b'test'),('x.txt',b''),('x.md',b'\xff'),('x.pdf',b'not a pdf')])
def test_invalid_files_are_rejected(name,content):
    with pytest.raises(ValueError): extract(name,content)


def test_embeddings_validate_order_dimensions_and_finite_values(monkeypatch):
    monkeypatch.setattr(provider,'request',lambda *a:{'data':[{'index':1,'embedding':[2.0]*1536},{'index':0,'embedding':[1.0]*1536}]})
    assert provider.embed(['a','b'])[0][0]==1
    for vector in ([1.0]*3,[float('nan')]*1536,[0]*1536):
        monkeypatch.setattr(provider,'request',lambda *a,v=vector:{'data':[{'index':0,'embedding':v}]})
        with pytest.raises(provider.ProviderError): provider.embed(['a'])


def test_provider_truncation_and_refusal_do_not_return_an_answer(monkeypatch):
    monkeypatch.setattr(provider,'request',lambda *a:{'choices':[{'finish_reason':'length','message':{'content':'{}'}}]})
    with pytest.raises(provider.ProviderError): provider.generate('question',[])
    assert provider.verify('question',[]) is False


def test_missing_api_key_fails_explicitly(monkeypatch):
    from app.config import Settings
    monkeypatch.setattr(provider,'settings',lambda:Settings(model_api_key=''))
    with pytest.raises(provider.ProviderError,match='not configured'): provider.embed(['hello'])


def test_gemini_omitted_zero_index_retains_batch_validation(monkeypatch):
    from app.config import Settings
    monkeypatch.setattr(provider,'settings',lambda:Settings(model_base_url='https://generativelanguage.googleapis.com/v1beta/openai'))
    monkeypatch.setattr(provider,'request',lambda *a:{'data':[{'index':1,'embedding':[2.0]*1536},{'embedding':[1.0]*1536}]})
    assert [v[0] for v in provider.embed(['a','b'])]==[1.0,2.0]
    monkeypatch.setattr(provider,'request',lambda *a:{'data':[{'embedding':[1.0]*1536},{'embedding':[2.0]*1536}]})
    with pytest.raises(provider.ProviderError): provider.embed(['a','b'])
