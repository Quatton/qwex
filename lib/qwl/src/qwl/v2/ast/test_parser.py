from qwl.ast.parser import Parser

source = """
name: Test Module
vars:
  message: "This is a test module."
tasks:
  echo:
    run: |
      echo "{{ vars.message }}"
  multistep:
    uses: std:steps
    vars:
      - name: Step 1
        run: echo "This is step 1"
      - name: Step 2
        run: echo "This is step 2"
"""


def test_parser_read_yaml():
    parser = Parser()
    module = parser.parse(source)
    assert module.name == "Test Module"
    assert module.vars["message"] == "This is a test module."

    echo_task = module.tasks.get("echo")
    assert echo_task is not None

    assert hasattr(echo_task, "run")
    assert echo_task.run is not None
    assert echo_task.run.strip().startswith("echo")
