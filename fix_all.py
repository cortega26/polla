import re, glob

for path in glob.glob("tests/*.py"):
    with open(path, 'r') as f:
        text = f.read()
    text = text.replace('("res", ', '("resultadoslotochile", ')
    text = text.replace('("open", ', '("openloto", ')
    with open(path, 'w') as f:
        f.write(text)

