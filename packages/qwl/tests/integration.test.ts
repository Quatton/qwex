import { describe, expect, it } from "bun:test";
import fs from "node:fs/promises";
import path from "node:path";

import innerEmitterTemplate from "../src/emitter/inner.sh.njk" with { type: "text" };
import { Pipeline } from "../src/pipeline";

const FIXTURES_DIR = path.join(import.meta.dir, "fixtures");

function createPipeline(fixturePath: string): Pipeline {
  return new Pipeline({
    sourcePath: path.join(FIXTURES_DIR, fixturePath),
    emitterTemplateStr: innerEmitterTemplate,
  });
}

describe("Pipeline Integration", () => {
  describe("simple module", () => {
    it("generates bash script matching expected output", async () => {
      const pipeline = createPipeline("simple.yaml");

      const result = await pipeline.run();

      // Remove hash lines for comparison (hashes depend on implementation details)
      const normalizedOutput = normalizeScript(result.script);
      const expectedPath = path.join(FIXTURES_DIR, "simple.expected.sh");
      const expected = await fs.readFile(expectedPath, "utf8");
      const normalizedExpected = normalizeScript(expected);

      expect(normalizedOutput).toBe(normalizedExpected);
    });

    it("returns correct task count", async () => {
      const pipeline = createPipeline("simple.yaml");

      const result = await pipeline.run();

      expect(result.count).toBe(3);
    });
  });

  describe("nested modules", () => {
    it("matches expected output", async () => {
      const pipeline = createPipeline("nested.yaml");

      const result = await pipeline.run();
      const normalizedOutput = normalizeScript(result.script);
      const expectedPath = path.join(FIXTURES_DIR, "nested.expected.sh");
      const expected = await fs.readFile(expectedPath, "utf8");
      const normalizedExpected = normalizeScript(expected);

      expect(normalizedOutput).toBe(normalizedExpected);
    });

    it("inlines tasks from submodules and same module", async () => {
      const pipeline = createPipeline("nested.yaml");

      const result = await pipeline.run();

      // Check that inline from submodule works
      expect(result.script).toContain('echo "[LOG] INFO: $1"');
      // Check that inline from same module works
      expect(result.script).toContain('echo "Hello"');
    });
  });

  describe("variable precedence", () => {
    it("matches expected output", async () => {
      const pipeline = createPipeline("var-precedence.yaml");

      const result = await pipeline.run();
      const normalizedOutput = normalizeScript(result.script);
      const expectedPath = path.join(FIXTURES_DIR, "var-precedence.expected.sh");
      const expected = await fs.readFile(expectedPath, "utf8");
      const normalizedExpected = normalizeScript(expected);

      expect(normalizedOutput).toBe(normalizedExpected);
    });

    it("resolves task-level vars over module-level vars", async () => {
      const pipeline = createPipeline("var-precedence.yaml");

      const result = await pipeline.run();

      // useModuleVar should use module-level var
      expect(result.script).toContain('echo "module-level"');
      // useTaskVar should use task-level var (override)
      expect(result.script).toContain('echo "task-level"');
    });
  });

  describe("complex module inheritance", () => {
    it("matches expected output", async () => {
      const pipeline = createPipeline("circular/entry.yaml");

      const result = await pipeline.run();
      const normalizedOutput = normalizeScript(result.script);
      const expectedPath = path.join(FIXTURES_DIR, "circular/entry.expected.sh");
      const expected = await fs.readFile(expectedPath, "utf8");
      const normalizedExpected = normalizeScript(expected);

      expect(normalizedOutput).toBe(normalizedExpected);
    });

    it("applies variable scoping correctly through nested modules", async () => {
      const pipeline = createPipeline("circular/entry.yaml");

      const result = await pipeline.run();

      // Entry's a1 uses entry's vars (origin=from-entry)
      expect(result.script).toContain('echo "a1: origin=from-entry"');

      // B's c1 uses B's vars (origin=from-B)
      expect(result.script).toContain('echo "c1: origin=from-B"');

      // B.D's d1 uses D's vars (origin=from-D)
      expect(result.script).toContain('echo "d1: origin=from-D"');
    });

    it("generates bash-safe function names with colon separators", async () => {
      const pipeline = createPipeline("circular/entry.yaml");

      const result = await pipeline.run();

      // Function definitions use colons for module hierarchy
      expect(result.script).toContain("B:c1()");
      expect(result.script).toContain("B:D:d1()");

      // Function calls also use colons
      expect(result.script).toContain("B:c1");
      expect(result.script).toContain("B:c2");
    });

    it("defines each task function only once despite multiple references", async () => {
      const pipeline = createPipeline("circular/entry.yaml");

      const result = await pipeline.run();

      // Count occurrences of a1() function definition - should be exactly 1
      const a1Defs = result.script.match(/^a1\(\)/gm);
      expect(a1Defs).toBeDefined();
      expect(a1Defs?.length).toBe(1);
    });

    it("duplicates inlined task code without creating function dependencies", async () => {
      const pipeline = createPipeline("circular/entry.yaml");

      const result = await pipeline.run();

      // testInlineDedup inlines a1 twice - both copies should be present in the output
      expect(result.script).toContain('echo "a1: origin=from-entry"\necho "a1: origin=from-entry"');
    });
  });

  describe("uses() function", () => {
    it("matches expected output for uses-task-inline", async () => {
      const pipeline = createPipeline("uses-task-inline.yaml");

      const result = await pipeline.run();
      const normalizedOutput = normalizeScript(result.script);
      const expectedPath = path.join(FIXTURES_DIR, "uses-task-inline.expected.sh");
      const expected = await fs.readFile(expectedPath, "utf8");
      const normalizedExpected = normalizeScript(expected);

      expect(normalizedOutput).toBe(normalizedExpected);
    });

    it("matches expected output for uses-module-task-inline", async () => {
      const pipeline = createPipeline("uses-module-task-inline.yaml");

      const result = await pipeline.run();
      const normalizedOutput = normalizeScript(result.script);
      const expectedPath = path.join(FIXTURES_DIR, "uses-module-task-inline.expected.sh");
      const expected = await fs.readFile(expectedPath, "utf8");
      const normalizedExpected = normalizeScript(expected);

      expect(normalizedOutput).toBe(normalizedExpected);
    });

    it("includes external file content directly in task body", async () => {
      const pipeline = createPipeline("uses-function.yaml");

      const result = await pipeline.run();

      // Check that the included script content is present
      expect(result.script).toContain('echo "This is an included script"');
      expect(result.script).toContain('echo "Variable: $1"');
    });

    it("inlines local task code with uses('tasks.taskName')", async () => {
      const pipeline = createPipeline("uses-task-inline.yaml");

      const result = await pipeline.run();

      // Check that the task code is inlined directly
      expect(result.script).toContain('echo "Inlined: echo');
      expect(result.script).toContain("Hello from helper");
    });

    it("inlines task from submodule with uses('modules.sub.tasks.taskName')", async () => {
      const pipeline = createPipeline("uses-module-task-inline.yaml");

      const result = await pipeline.run();

      // Check that the submodule task code is inlined
      expect(result.script).toContain('echo "From submodule"');
    });
  });

  describe("{% uses %} tag", () => {
    it("resolves relative paths from each task's defining source file", async () => {
      const pipeline = createPipeline("inherit-path/entry.yaml");

      const result = await pipeline.run();

      const cwd = process.cwd();
      const entrySrc = path.join(FIXTURES_DIR, "inherit-path/entry.yaml");
      const bSrc = path.join(FIXTURES_DIR, "inherit-path/another_folder/module-b.yaml");
      const entryDir = path.join(FIXTURES_DIR, "inherit-path");
      const bDir = path.join(FIXTURES_DIR, "inherit-path/another_folder");

      // fromA is defined in entry.yaml, so ./local.sh resolves in inherit-path/
      expect(result.script).toContain('echo "FROM A: local.sh"');

      expect(result.script).toContain(`echo "A cwd=${cwd}"`);
      expect(result.script).toContain(`echo "A src=${entrySrc}"`);
      expect(result.script).toContain(`echo "A dir=${entryDir}"`);
      expect(result.script).toContain(`echo "A resolved=${path.join(entryDir, "local.sh")}"`);

      // fromB is defined in another_folder/module-b.yaml, so ./b.sh resolves in another_folder/
      expect(result.script).toContain('echo "FROM B: b.sh"');

      expect(result.script).toContain(`echo "B cwd=${cwd}"`);
      expect(result.script).toContain(`echo "B src=${bSrc}"`);
      expect(result.script).toContain(`echo "B dir=${bDir}"`);
      expect(result.script).toContain(`echo "B resolved=${path.join(bDir, "b.sh")}"`);
    });
  });

  describe("task.uses with pre-rendered vars", () => {
    it("matches expected output", async () => {
      const pipeline = createPipeline("task-uses-with-vars.yaml");

      const result = await pipeline.run();
      const normalizedOutput = normalizeScript(result.script);
      const expectedPath = path.join(FIXTURES_DIR, "task-uses-with-vars.expected.sh");
      const expected = await fs.readFile(expectedPath, "utf8");
      const normalizedExpected = normalizeScript(expected);

      expect(normalizedOutput).toBe(normalizedExpected);
    });

    it("pre-renders task vars in caller context before passing to used task", async () => {
      const pipeline = createPipeline("task-uses-with-vars.yaml");

      const result = await pipeline.run();

      // Check that vars from caller context (base_dir, file_name) are rendered in path
      expect(result.script).toContain('echo "Hello World" > "/tmp/test/output.txt"');
      // Should not contain unreplaced template syntax
      expect(result.script).not.toContain("{{ vars.base_dir }}");
      expect(result.script).not.toContain("{{ vars.file_name }}");
    });
  });
});

function normalizeScript(script: string): string {
  return script
    .split("\n")
    .filter((line) => !line.startsWith("# Hash:"))
    .join("\n")
    .trim();
}
