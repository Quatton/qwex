import { describe, it, expect } from "bun:test";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { load, canonicalize } from "./loader";

describe("loader", () => {
  it("load reads file content", async () => {
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), "qwex-loader-"));
    const file = path.join(dir, "test.txt");
    const content = "Hello, loader!";

    try {
      await fs.writeFile(file, content, "utf8");
      const out = await load(file);
      expect(out).toBe(content);
    } finally {
      await fs.rm(dir, { recursive: true, force: true });
    }
  });

  it("canonicalize resolves symlinks and returns an absolute path", async () => {
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), "qwex-loader-"));
    const target = path.join(dir, "target.txt");
    const link = path.join(dir, "link.txt");
    const content = "symlink target";

    try {
      await fs.writeFile(target, content, "utf8");
      await fs.symlink(target, link);

      // use a relative path to the link to exercise resolution
      const relLink = path.relative(process.cwd(), link);
      const real = await canonicalize(relLink);

      const expected = await fs.realpath(target);
      expect(real).toBe(expected);

      // ensure load works via the symlink (i.e., canonicalization used internally)
      const loaded = await load(relLink);
      expect(loaded).toBe(content);
    } finally {
      await fs.rm(dir, { recursive: true, force: true });
    }
  });

  it("canonicalize throws for missing files", async () => {
    const missing = path.join(process.cwd(), "this-file-should-not-exist-123456.txt");
    await expect(canonicalize(missing)).rejects.toThrow();
  });

  it("load throws for missing files", async () => {
    const missing = path.join(process.cwd(), "this-file-should-not-exist-abcdef.txt");
    await expect(load(missing)).rejects.toThrow();
  });
});
