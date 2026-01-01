import { describe, it, expect } from "bun:test";
import { strict as assert } from "node:assert";

import { QwlError } from "../errors";
import { parseConfig } from "./index";

const yamlText = `vars:
  variable: "value"

tasks:
  hello:
    cmd: echo "Hello, Qwex!"
    desc: "Prints a hello message"
`;

describe("parseYaml", () => {
  it("parses vars and tasks", () => {
    const out = parseConfig(yamlText);
    if (out instanceof QwlError) {
      console.error("Parsing failed with error:", out);
      throw out;
    }
    expect(out.vars).toBeDefined();
    expect(out.tasks).toBeDefined();
    assert(out.vars, "Expected vars to be defined");
    assert(out.tasks, "Expected tasks to be defined");
    expect(out.vars.variable).toBe("value");
    expect(out.tasks.hello?.cmd).toEqual(`echo "Hello, Qwex!"`);
    expect(out.tasks.hello?.desc).toBe("Prints a hello message");
  });

  it("variables are ordered correctly", () => {
    const yaml = `
vars:
  first: "1"
  second: 
    mapped: "2"
    mapped2: "3"
  third:
    - "a"
    - "b"
`;
    const out = parseConfig(yaml);
    assert(!(out instanceof QwlError), "Expected valid config");
    assert(out.vars, "Expected vars to be defined");
    const keys = Object.keys(out.vars!);
    expect(keys).toEqual(["first", "second", "third"]);
    expect(out.vars.second).toEqual({ mapped: "2", mapped2: "3" });
    expect(out.vars.third).toEqual(["a", "b"]);
  });
});
