import fs from "node:fs/promises";
import path from "node:path";
import { QwlError } from "../errors";

// Import builtins as text
import stdUtils from "../../builtins/std/utils.yaml" with { type: "text" };
import stdLog from "../../builtins/std/log.yaml" with { type: "text" };
import stdTest from "../../builtins/std/test.yaml" with { type: "text" };
import stdSteps from "../../builtins/std/steps.yaml" with { type: "text" };

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
    throw QwlError.from(e);
  }
}

export async function load(filePath: string): Promise<string> {
  try {
    return await fs.readFile(filePath, "utf8");
  } catch (e) {
    throw QwlError.from(e);
  }
}

async function probeYamlPath(basePath: string): Promise<string | QwlError> {
  for (const ext of YAML_EXTENSIONS) {
    const candidate = basePath + ext;
    try {
      await fs.access(candidate);
      return await canonicalize(candidate);
    } catch {}
  }
  for (const ext of YAML_EXTENSIONS) {
    const candidate = path.join(basePath, `index${ext}`);
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

export async function resolveModulePath(
  specifier: string,
  parentPath?: string
): Promise<string> {
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
