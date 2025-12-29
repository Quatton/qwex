import { describe, it, expect, beforeEach, afterEach } from "bun:test";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { load, canonicalize } from "./loader";

let tmpDir: string | undefined;

describe("loader", () => {
  beforeEach(async () => {
    tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "qwex-loader-"));
  });

  afterEach(async () => {
    if (tmpDir) {
      await fs.rm(tmpDir, { recursive: true, force: true });
      tmpDir = undefined;
    }
  });

  it("load reads file content", async () => {
    const file = path.join(tmpDir!, "test.txt");
    const content = "Hello, loader!";

    await fs.writeFile(file, content, "utf8");
    const out = await load(file);
    expect(out).toBe(content);
  });

  it("canonicalize resolves symlinks and returns an absolute path", async () => {
    const target = path.join(tmpDir!, "target.txt");
    const link = path.join(tmpDir!, "link.txt");
    const content = "symlink target";

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
  });

  it("canonicalize throws for missing files", async () => {
    const missing = path.join(
      process.cwd(),
      "this-file-should-not-exist-123456.txt"
    );
    await expect(canonicalize(missing)).rejects.toThrow();
  });

  it("load throws for missing files", async () => {
    const missing = path.join(
      process.cwd(),
      "this-file-should-not-exist-abcdef.txt"
    );
    await expect(load(missing)).rejects.toThrow();
  });
});
