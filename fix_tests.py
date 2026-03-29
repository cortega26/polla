import glob
import re

for path in glob.glob("tests/*.py"):
    with open(path) as f:
        content = f.read()

    # 1. Replace monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_resultadosloto", X)
    content = re.sub(
        r'monkeypatch\.setattr\(\s*pipeline_mod\.pozos_module,\s*"get_pozo_resultadosloto",\s*(.*?)\s*\)',
        r'pipeline_mod.POZO_SOURCES = (("res", \1),) + pipeline_mod.POZO_SOURCES',
        content,
    )

    # Also patch openloto:
    content = re.sub(
        r'monkeypatch\.setattr\(\s*pipeline_mod\.pozos_module,\s*"get_pozo_openloto",\s*(.*?)\s*\)',
        r'pipeline_mod.POZO_SOURCES = pipeline_mod.POZO_SOURCES + (("open", \1),)',
        content,
    )

    # 2. Main tests
    content = re.sub(
        r'monkeypatch\.setattr\(main_mod,\s*"get_pozo_resultadosloto",\s*(.*?)\s*\)',
        r"# Deprecated: \1",
        content,
    )

    # 3. phase4 tests
    content = re.sub(
        r'monkeypatch\.setattr\("polla_app\.__main__\.get_pozo_resultadosloto",\s*(.*?)\s*\)',
        r"# Deprecated: \1",
        content,
    )

    with open(path, "w") as f:
        f.write(content)
