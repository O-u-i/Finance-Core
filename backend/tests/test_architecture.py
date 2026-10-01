import ast
from pathlib import Path


def test_domain_has_no_transport_persistence_or_consumer_imports():
    root = Path(__file__).resolve().parents[1] / 'finance_core'
    forbidden = {'fastapi', 'sqlite3', 'httpx', 'requests', 'openai', 'ollama', 'frag', 'sfos', 'database', 'ledger_repository', 'registry'}
    for name in ('domain.py', 'ledger.py', 'models_v2.py'):
        tree = ast.parse((root / name).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            imports = [node.module or ''] if isinstance(node, ast.ImportFrom) else [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            for module in imports:
                assert not forbidden.intersection(module.split('.')), f'{name} imports {module}'


def test_runtime_does_not_import_optional_consumers_or_models():
    root = Path(__file__).resolve().parents[1] / 'finance_core'
    for file in root.glob('*.py'):
        tree = ast.parse(file.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            imports = [node.module or ''] if isinstance(node, ast.ImportFrom) else [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            for module in imports:
                assert not {'frag', 'sfos', 'openai', 'ollama'}.intersection(module.lower().split('.'))
