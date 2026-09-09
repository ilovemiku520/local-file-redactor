from io import BytesIO
from pathlib import Path
import hashlib,sys,tarfile,zipfile
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_models import within,extract_ollama,extract_ocr

def test_archive_traversal_rejected_before_writing(tmp_path):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as stream:
        stream.writestr('ollama.exe','safe');stream.writestr('../escape.txt','bad')
    with pytest.raises(ValueError):extract_ollama(archive,tmp_path/'dest')
    assert not (tmp_path/'dest/ollama.exe').exists()
    assert not (tmp_path/'escape.txt').exists()

def test_ocr_archive_integrity(tmp_path):
    data=b'synthetic-model-parameter';archive=tmp_path/'ocr.tar'
    with tarfile.open(archive,'w') as stream:
        info=tarfile.TarInfo('model/inference.pdiparams');info.size=len(data);stream.addfile(info,BytesIO(data))
    relative='runtime/models/ocr/demo/inference.pdiparams'
    extract_ocr(archive,{relative:hashlib.sha256(data).hexdigest()},tmp_path)
    assert (tmp_path/relative).read_bytes()==data
    with pytest.raises(ValueError,match='SHA-256'):extract_ocr(archive,{relative:'0'*64},tmp_path)

def test_asset_destination_cannot_escape(tmp_path):
    with pytest.raises(ValueError):within(tmp_path,'../outside')
    assert within(tmp_path,'runtime\\models\\test')==tmp_path/'runtime/models/test'
