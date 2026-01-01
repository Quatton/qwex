import fs from "node:fs/promises";
import path from "node:path";

import stdLog from "../../builtins/std/log.yaml" with { type: "text" };
import stdSteps from "../../builtins/std/steps.yaml" with { type: "text" };
import stdTest from "../../builtins/std/test.yaml" with { type: "text" };
// Import builtins as text
import stdUtils from "../../builtins/std/utils.yaml" with { type: "text" };
import { QwlError } from "../errors";

const BUILTINS: Record<string, string> = {
  "std/utils": stdUtils,
  "std/log": stdLog,
  "std/test": stdTest,
  "std/steps": stdSteps,
};

const YAML_EXTENSIONS = [".yaml", ".yml"];

export function isBuiltin(specifier: string): boolean {
  return specifier in BUILTINS;
}

export function getBuiltinText(specifier: string): string | undefined {
  return BUILTINS[specifier];
}

export async function canonicalize(filePath: string): Promise<string> {
  try {
    return await fs.realpath(path.resolve(filePath));
  } catch (e) {
    throw new QwlError({
      code: "LOADER_ERROR",
      message: `Failed to canonicalize path '${filePath}': ${(e as Error).message}.`,
    });
  }
}

export async function load(filePath: string): Promise<string> {
  try {
    return await fs.readFile(filePath, "utf8");
  } catch (e) {
    throw new QwlError({
      code: "LOADER_ERROR",
      message: `Failed to load file '${filePath}': ${(e as Error).message}`,
    });
  }
}

async function probeYamlPath(basePath: string): Promise<string | QwlError> {
  const candidates = [
    ...YAML_EXTENSIONS.map((ext) => basePath + ext),
    ...YAML_EXTENSIONS.map((ext) => path.join(basePath, `index${ext}`)),
  ];

  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return await canonicalize(candidate);
    } catch {}
  }

  return new QwlError({
    code: "LOADER_ERROR",
    message: `No YAML file found at ${basePath}`,
  });
}

export async function resolveModulePath(specifier: string, parentPath?: string): Promise<string> {
  if (!specifier) {
    throw new QwlError({
      code: "LOADER_ERROR",
      message: "Module specifier is required",
    });
  }

  if (isBuiltin(specifier)) {
    return specifier;
  }

  const hasExtension = YAML_EXTENSIONS.some((ext) => specifier.endsWith(ext));

  let basePath: string;
  if (path.isAbsolute(specifier)) {
    basePath = specifier;
  } else if (parentPath && !isBuiltin(parentPath)) {
    basePath = path.resolve(path.dirname(parentPath), specifier);
  } else {
    basePath = path.resolve(process.cwd(), specifier);
  }

  if (hasExtension) {
    return await canonicalize(basePath);
  }

  const found = await probeYamlPath(basePath);
  if (found instanceof QwlError) {
    throw new QwlError({
      code: "LOADER_ERROR",
      message: `Module not found: ${specifier} (searched from ${parentPath ?? "cwd"})`,
    });
  }
  return found;
}

export class Loader {
  private cache = new Map<string, string>();

  async load(specifier: string, parentPath?: string): Promise<string> {
    const resolvedPath = await resolveModulePath(specifier, parentPath);

    let text = this.cache.get(resolvedPath);
    if (text !== undefined) {
      return text;
    }

    if (isBuiltin(resolvedPath)) {
      text = getBuiltinText(resolvedPath)!;
    } else {
      text = await load(resolvedPath);
    }

    this.cache.set(resolvedPath, text);
    return text;
  }
}
