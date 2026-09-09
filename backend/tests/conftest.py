from pathlib import Path
import pytest

def pytest_addoption(parser):
    parser.addoption('--run-integration', action='store_true', default=False, help='Run tests requiring downloaded model assets.')

def pytest_collection_modifyitems(config, items):
    for item in items:
        if 'integration' in item.keywords and not config.getoption('--run-integration'):
            item.add_marker(pytest.mark.skip(reason='Use --run-integration after preparing local model/OCR assets.'))
        if 'font' in item.keywords and not Path('C:/Windows/Fonts/msyh.ttc').is_file():
            item.add_marker(pytest.mark.skip(reason='Microsoft YaHei is required for Chinese preview rendering.'))
