import { describe, expect, it } from "bun:test";
import fs from "node:fs/promises";
import path from "node:path";

import { Pipeline } from "../src/pipeline";

const FIXTURES_DIR = path.join(import.meta.dir, "fixtures");

describe("Pipeline Integration", () => {
  describe("simple module", () => {
    it("generates bash script matching expected output", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "simple.yaml"),
      });

      const result = await pipeline.run();

      // Remove hash lines for comparison (hashes depend on implementation details)
      const normalizedOutput = normalizeScript(result.script);
      const expectedPath = path.join(FIXTURES_DIR, "simple.expected.sh");
      const expected = await fs.readFile(expectedPath, "utf8");
      const normalizedExpected = normalizeScript(expected);

      expect(normalizedOutput).toBe(normalizedExpected);
    });

    it("returns correct task count", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "simple.yaml"),
      });

      const result = await pipeline.run();

      expect(result.count).toBe(3);
    });
  });

  describe("nested modules", () => {
    it("inlines tasks from submodules and same module", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "nested.yaml"),
      });

      const result = await pipeline.run();

      // Check that inline from submodule works
      expect(result.script).toContain('echo "[LOG] INFO: $1"');
      // Check that inline from same module works
      expect(result.script).toContain('echo "Hello"');
    });
  });

  describe("variable precedence", () => {
    it("resolves task-level vars over module-level vars", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "var-precedence.yaml"),
      });

      const result = await pipeline.run();

      // useModuleVar should use module-level var
      expect(result.script).toContain('echo "module-level"');
      // useTaskVar should use task-level var (override)
      expect(result.script).toContain('echo "task-level"');
    });
  });

  describe("complex module inheritance", () => {
    it("applies variable scoping correctly through nested modules", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "circular/entry.yaml"),
      });

      const result = await pipeline.run();

      // Entry's a1 uses entry's vars (origin=from-entry)
      expect(result.script).toContain('echo "a1: origin=from-entry"');

      // B's c1 uses B's vars (origin=from-B)
      expect(result.script).toContain('echo "c1: origin=from-B"');

      // B.D's d1 uses D's vars (origin=from-D)
      expect(result.script).toContain('echo "d1: origin=from-D"');
    });

    it("generates bash-safe function names with colon separators", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "circular/entry.yaml"),
      });

      const result = await pipeline.run();

      // Function definitions use colons for module hierarchy
      expect(result.script).toContain("B:c1()");
      expect(result.script).toContain("B:D:d1()");

      // Function calls also use colons
      expect(result.script).toContain("B:c1");
      expect(result.script).toContain("B:c2");
    });

    it("defines each task function only once despite multiple references", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "circular/entry.yaml"),
      });

      const result = await pipeline.run();

      // Count occurrences of a1() function definition - should be exactly 1
      const a1Defs = result.script.match(/^a1\(\)/gm);
      expect(a1Defs).toBeDefined();
      expect(a1Defs?.length).toBe(1);
    });

    it("duplicates inlined task code without creating function dependencies", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "circular/entry.yaml"),
      });

      const result = await pipeline.run();

      // testInlineDedup inlines a1 twice - both copies should be present in the output
      expect(result.script).toContain('echo "a1: origin=from-entry"\necho "a1: origin=from-entry"');
    });
  });

  describe("uses() function", () => {
    it("includes external file content directly in task body", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "uses-function.yaml"),
      });

      const result = await pipeline.run();

      // Check that the included script content is present
      expect(result.script).toContain('echo "This is an included script"');
      expect(result.script).toContain('echo "Variable: $1"');
    });

    it("inlines local task code with uses('tasks.taskName')", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "uses-task-inline.yaml"),
      });

      const result = await pipeline.run();

      // Check that the task code is inlined directly
      expect(result.script).toContain('echo "Inlined: echo');
      expect(result.script).toContain("Hello from helper");
    });

    it("inlines task from submodule with uses('modules.sub.tasks.taskName')", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "uses-module-task-inline.yaml"),
      });

      const result = await pipeline.run();

      // Check that the submodule task code is inlined
      expect(result.script).toContain('echo "From submodule"');
    });
  });

  describe("eof tag", () => {
    it("generates heredoc syntax with unique hash-based delimiter", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "eof-tag.yaml"),
      });

      const result = await pipeline.run();

      // Check that heredoc syntax is present with unique delimiter
      expect(result.script).toMatch(/'EOF_[A-F0-9]+'/); // Opening delimiter with quotes
      expect(result.script).toContain("Hello World!");
      expect(result.script).toContain("This is a heredoc.");
      expect(result.script).toMatch(/^EOF_[A-F0-9]+$/m); // Closing delimiter without quotes
    });
  });

  describe("context tag", () => {
    it("generates declare -f for tasks referenced in context blocks", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "context-tag.yaml"),
      });

      const result = await pipeline.run();

      // Check that eval "$(declare -f)" is output for referenced tasks
      expect(result.script).toContain('eval "$(declare -f helper)"');
      // And the task call is still present
      expect(result.script).toContain("helper");
    });

    it("escapes dollar signs when escape=true option is used", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "context-escape.yaml"),
      });

      const result = await pipeline.run();

      // Check that eval "$(declare -f)" is still output
      expect(result.script).toContain('eval "$(declare -f helper)"');
      // Check that $ is escaped to \$ in the body content
      expect(result.script).toContain("\\$VALUE");
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
