import ast
from pathlib import Path


def test_domain_has_no_transport_persistence_or_consumer_imports():
    root = Path(__file__).resolve().parents[1] / 'finance_core'
    forbidden = {'fastapi', 'sqlite3', 'httpx', 'requests', 'openai', 'ollama', 'frag', 'sfos', 'database', 'ledger_repository', 'registry'}
    for name in ('domain.py', 'ledger.py', 'models_v2.py', 'models_personal.py', 'personal_finance.py'):
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


def test_read_and_backup_adapters_do_not_depend_on_command_repositories():
    root = Path(__file__).resolve().parents[1] / 'finance_core'
    forbidden = {'ledger_repository', 'personal_finance_repository', 'api_v2', 'api_v3', 'api_personal'}
    for name in ('personal_finance_snapshot.py', 'ledger_reports.py', 'ledger_backup.py'):
        tree = ast.parse((root / name).read_text(encoding='utf-8'))
        # A type-only annotation is not a runtime dependency or a new repository port.
        for node in tree.body:
            if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == 'TYPE_CHECKING':
                continue
            for child in ast.walk(node):
                imports = [child.module or ''] if isinstance(child, ast.ImportFrom) else [alias.name for alias in child.names] if isinstance(child, ast.Import) else []
                for module in imports:
                    assert not forbidden.intersection(module.split('.')), f'{name} imports {module}'
