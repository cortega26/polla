import re

path = "tests/test_pipeline.py"
with open(path) as f:
    text = f.read()

text = re.sub(
    r'monkeypatch\.setattr\(\s*pipeline_mod\.pozos_module,\s*"get_pozo_resultadosloto",\s*(.*?)\s*\)\n\s*monkeypatch\.setattr\(\s*pipeline_mod\.pozos_module,\s*"get_pozo_openloto",\s*(.*?)\s*\)',
    r'monkeypatch.setattr(pipeline_mod, "POZO_SOURCES", (("res", \1), ("open", \2)))',
    text,
)

text = re.sub(
    r'monkeypatch\.setattr\(\s*pipeline_mod\.pozos_module,\s*"get_pozo_openloto",\s*(.*?)\s*\)',
    r'monkeypatch.setattr(pipeline_mod, "POZO_SOURCES", (("open", \1),))',
    text,
)

with open(path, "w") as f:
    f.write(text)
