import fs from "node:fs/promises";
import path from "node:path";

export async function canonicalize(filePath: string): Promise<string> {
  return await fs.realpath(path.resolve(filePath));
}

export async function load(filePath: string): Promise<string> {
  return await fs.readFile(filePath, "utf8");
}

export class Loader {
  cache: Map<string, string> = new Map();

  async load(filePath: string): Promise<string> {
    const realPath = await canonicalize(filePath);
    let cached = this.cache.get(realPath);
    if (!cached) {
      cached = await load(realPath);
      this.cache.set(realPath, cached);
    }
    return cached;
  }
}
