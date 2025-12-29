import { describe, it, expect } from "bun:test";
import { parseConfig } from "./index";
import { ArkErrors } from "arktype";
import { strict as assert } from "node:assert";

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
    assert(!(out instanceof ArkErrors), "Expected valid config");
    expect(out.vars.variable).toBe("value");
    expect(out.tasks.hello?.cmd).toEqual(`echo "Hello, Qwex!"`);
    expect(out.tasks.hello?.desc).toBe("Prints a hello message");
  });
});
