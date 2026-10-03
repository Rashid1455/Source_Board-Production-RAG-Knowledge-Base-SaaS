from contextlib import contextmanager
from uuid import uuid4
from app import rag


def test_empty_workspace_abstains_without_provider_call(monkeypatch):
    class DB:
        def execute(self,*a): return self
        def fetchone(self): return {'n':0}
    @contextmanager
    def database(): yield DB()
    monkeypatch.setattr(rag,'database',database)
    monkeypatch.setattr(rag.provider,'embed',lambda *a:(_ for _ in ()).throw(AssertionError('Provider must not be called')))
    assert rag.answer(uuid4(),'question')['status']=='insufficient_evidence'


def test_unentailed_claim_is_rejected_after_real_quote_validation(monkeypatch):
    source_id,document_id=uuid4(),uuid4()
    class DB:
        def execute(self,*a): return self
        def fetchone(self): return {'n':1}
        def fetchall(self): return [{'id':source_id,'document_id':document_id,'name':'policy','page':1,
                                    'text':'Employees may work remotely three days per week.','similarity':.9}]
    @contextmanager
    def database(): yield DB()
    monkeypatch.setattr(rag,'database',database)
    monkeypatch.setattr(rag.provider,'embed',lambda *a:[[1.0]*1536])
    monkeypatch.setattr(rag.provider,'generate',lambda *a:{'answerable':True,'claims':[{
        'text':'Employees can work remotely every day.',
        'evidence':[{'source_id':str(source_id),'quote':'Employees may work remotely three days per week.'}]}]})
    monkeypatch.setattr(rag.provider,'verify',lambda *a:False)
    result=rag.answer(uuid4(),'How many remote days?')
    assert result['status']=='unsupported_claims'
    assert result['sources']==[]
