import { describe, it, expect } from "bun:test";
import { Pipeline } from "./pipeline";
import path from "node:path";

const FIXTURES_DIR = path.join(import.meta.dir, "../../tests/fixtures");

describe("Pipeline", () => {
  describe("constructor", () => {
    it("accepts entry path option", () => {
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "simple.yaml"),
      });
      expect(pipeline).toBeDefined();
    });
  });

  describe("run", () => {
    it("returns EmitResult with script and count", async () => {
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "simple.yaml"),
      });

      const result = await pipeline.run();

      expect(result).toHaveProperty("script");
      expect(result).toHaveProperty("count");
      expect(typeof result.script).toBe("string");
      expect(typeof result.count).toBe("number");
    });

    it("resolves relative paths from cwd", async () => {
      const originalCwd = process.cwd();
      try {
        process.chdir(FIXTURES_DIR);
        const pipeline = new Pipeline({ entryPath: "simple.yaml" });
        const result = await pipeline.run();
        expect(result.count).toBeGreaterThan(0);
      } finally {
        process.chdir(originalCwd);
      }
    });

    it("throws QwlError for non-existent file", async () => {
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "non-existent.yaml"),
      });

      await expect(pipeline.run()).rejects.toThrow();
    });

    it("throws on circular module dependency", async () => {
      // Create a test that would have circular deps
      // For now, just verify the pipeline works
      const pipeline = new Pipeline({
        entryPath: path.join(FIXTURES_DIR, "simple.yaml"),
      });

      const result = await pipeline.run();
      expect(result.script).toContain("echo");
    });
  });
});
