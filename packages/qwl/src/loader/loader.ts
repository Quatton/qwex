import fs from "node:fs/promises";
import path from "node:path";

export async function canonicalize(filePath: string): Promise<string> {
  const abs = path.resolve(filePath);
  return await fs.realpath(abs);
}

export async function load(filePath: string): Promise<string> {
  const real = await canonicalize(filePath);

  const content = await fs.readFile(real, "utf8");
  return content;
}
