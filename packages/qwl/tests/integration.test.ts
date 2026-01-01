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

      expect(result.count).toBe(3);
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

  describe("complex inheritance", () => {
    it("renders nested module tasks with correct prefixes", async () => {
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "circular/entry.yaml"),
      });

      const result = await pipeline.run();

      // Entry's a1 uses entry's vars (origin=from-entry)
      expect(result.script).toContain('echo "a1: origin=from-entry"');

      // B's c1 uses B's vars (origin=from-B)
      expect(result.script).toContain('echo "c1: origin=from-B"');

      // B.D's d1 uses D's vars (origin=from-D)
      expect(result.script).toContain('echo "d1: origin=from-D"');
    });

    it("uses bash-safe function names (double underscores)", async () => {
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "circular/entry.yaml"),
      });

      const result = await pipeline.run();

      // Function definitions use double underscores
      expect(result.script).toContain("B__c1()");
      expect(result.script).toContain("B__D__d1()");

      // Function calls also use double underscores
      expect(result.script).toContain("B__c1");
      expect(result.script).toContain("B__c2");
    });

    it("deduplicates tasks referenced multiple times", async () => {
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "circular/entry.yaml"),
      });

      const result = await pipeline.run();

      // Count occurrences of a1() function definition
      const a1Defs = result.script.match(/^a1\(\)/gm);
      expect(a1Defs?.length).toBe(1);
    });

    it("inlines tasks without creating dependencies", async () => {
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "circular/entry.yaml"),
      });

      const result = await pipeline.run();

      // testInlineDedup inlines a1 twice, check both are present
      expect(result.script).toContain(
        'echo "a1: origin=from-entry"\necho "a1: origin=from-entry"'
      );
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
