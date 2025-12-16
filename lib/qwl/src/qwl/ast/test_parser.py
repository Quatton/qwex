from qwl.ast.parser import Parser

source = """
name: Test Module
vars:
  message: "This is a test module."
tasks:
  echo:
    run: |
      echo "{{ vars.message }}"
"""


def test_parser_read_yaml():
    parser = Parser()
    module = parser.parse(source)
    assert module.name == "Test Module"
    assert module.vars["message"] == "This is a test module."
    # tasks should be parsed into Task objects
    echo_task = module.tasks.get("echo")
    assert echo_task is not None
    # the run string should contain the echo command (template left intact)
    assert hasattr(echo_task, "run")
    assert echo_task.run is not None
    assert echo_task.run.strip().startswith("echo")
    # This is essentially just a smoke test to ensure no exceptions are raised
