from qwl.ast.parser import parse_yaml_text


SAMPLE = """vars:
  variable: "value"

tasks:
  hello:
    cmd:
      - echo "Hello, Qwex!"
    desc: "Prints a hello message"
"""


def test_parse_vars_and_tasks():
    cfg = parse_yaml_text(SAMPLE)

    assert cfg is not None

    assert cfg.vars["variable"] == "value"

    assert "hello" in cfg.tasks
    t = cfg.tasks["hello"]
    assert t.cmd == ['echo "Hello, Qwex!"']
    assert t.desc == "Prints a hello message"
