from pathlib import Path
import sys,time
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.storage import Storage

def test_cleanup_covers_jobs_beyond_ui_limit(tmp_path):
    store=Storage(tmp_path/'private')
    older=time.time()-90000;active={'queued','detecting'}
    old_ids=[uuid4().hex for _ in range(250)]
    pending=uuid4().hex;recent=uuid4().hex
    with store.connect() as db:
        for identifier in old_ids:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',(identifier,'completed',older,older,b'test'))
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',(pending,'queued',older,older,b'test'))
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',(recent,'completed',time.time(),time.time(),b'test'))
    assert set(store.lifecycle_ids(active,time.time()-86400))==set(old_ids)
    assert store.lifecycle_ids(active)==[pending]
    for identifier in store.lifecycle_ids(active,time.time()-86400):store.delete(identifier)
    with store.connect() as db:assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==2
