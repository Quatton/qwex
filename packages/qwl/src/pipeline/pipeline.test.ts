import { describe, expect, it } from "bun:test";
import path from "node:path";

import { Pipeline } from "./pipeline";

const FIXTURES_DIR = path.join(import.meta.dir, "../../tests/fixtures");

describe("Pipeline", () => {
  describe("constructor", () => {
    it("creates pipeline instance with valid source path", () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "simple.yaml"),
      });
      expect(pipeline).toBeInstanceOf(Pipeline);
    });
  });

  describe("run", () => {
    it("generates bash script with task count", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "simple.yaml"),
      });

      const result = await pipeline.run();

      expect(result).toHaveProperty("script");
      expect(result).toHaveProperty("count");
      expect(typeof result.script).toBe("string");
      expect(typeof result.count).toBe("number");
      expect(result.count).toBeGreaterThan(0);
      expect(result.script.length).toBeGreaterThan(0);
    });

    it("resolves relative paths from cwd", async () => {
      const originalCwd = process.cwd();
      try {
        process.chdir(FIXTURES_DIR);
        const pipeline = new Pipeline({ sourcePath: "simple.yaml" });
        const result = await pipeline.run();
        expect(result.count).toBeGreaterThan(0);
        expect(result.script).toContain("echo");
      } finally {
        process.chdir(originalCwd);
      }
    });

    it("throws error for non-existent file", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "non-existent.yaml"),
      });

      await expect(pipeline.run()).rejects.toThrow(/LOADER_ERROR|ENOENT|cannot find/i);
    });

    it("throws error on circular module dependency", async () => {
      const pipeline = new Pipeline({
        sourcePath: path.join(FIXTURES_DIR, "circular-dep-a.yaml"),
      });

      await expect(pipeline.run()).rejects.toThrow(/Circular module dependency/);
    });
  });
});
