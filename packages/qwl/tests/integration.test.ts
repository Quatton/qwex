import { describe, it, expect } from "bun:test";
import { Pipeline } from "../src/pipeline";
import path from "node:path";
import fs from "node:fs/promises";

const FIXTURES_DIR = path.join(import.meta.dir, "fixtures");

describe("Pipeline Integration", () => {
  describe("simple module", () => {
    it("generates expected bash script", async () => {
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "simple.yaml"),
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
        entryPath: path.join(FIXTURES_DIR, "simple.yaml"),
      });

      const result = await pipeline.run();

      expect(result.taskCount).toBe(3);
    });
  });

  describe("nested modules", () => {
    it("renders inline tasks correctly", async () => {
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "nested.yaml"),
      });

      const result = await pipeline.run();

      // Check that inline from submodule works
      expect(result.script).toContain('echo "[LOG] INFO: $1"');
      // Check that inline from same module works
      expect(result.script).toContain('echo "Hello"');
    });
  });

  describe("variable precedence", () => {
    it("task vars override module vars", async () => {
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "var-precedence.yaml"),
      });

      const result = await pipeline.run();

      // useModuleVar should use module-level var
      expect(result.script).toContain('echo "module-level"');
      // useTaskVar should use task-level var (override)
      expect(result.script).toContain('echo "task-level"');
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
