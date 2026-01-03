import { Template } from "nunjucks";

import type { ModuleTemplate, VariableTemplateValue } from "../ast";

import { QwlError } from "../errors";
import { resolvePath as resolvePathUtil } from "../utils/path";

/**
 * Normalizes a uses path by expanding shorthand forms to full paths.
 * Examples:
 * - "adapter.local" -> "modules.adapter.tasks.local"
 * - "sub.module" -> "modules.sub.module"
 * - "modules.sub.tasks.task" -> "modules.sub.tasks.task" (unchanged)
 */
export function normalizeUsesPath(path: string): string {
  if (path.startsWith("modules") || path.startsWith("tasks")) {
    return path;
  }

  const parts = path.split(".");
  if (parts.length === 2) {
    return `modules.${parts[0]}.tasks.${parts[1]}`;
  } else {
    return `modules.${path}`;
  }
}

/**
 * Traverses a dotted path to find a module and task.
 * e.g., "tasks.myTask" or "modules.sub.tasks.subTask"
 */
export function resolveModulePath(
  rootModule: ModuleTemplate,
  startModule: ModuleTemplate,
  path: string,
  startPrefix: string,
): { module: ModuleTemplate; taskName: string; prefix: string } {
  const parts = path.split(".");
  let currentModule = startModule;
  let currentPrefix = startPrefix;
  let i = 0;

  // If path starts with "modules", start from root
  if (parts[i] === "modules") {
    currentModule = rootModule;
    currentPrefix = "";
    i++;
  }

  // Navigate through module hierarchy until we hit "tasks" or run out of parts
  while (i < parts.length && parts[i] !== "tasks") {
    const part = parts[i]!;
    const subModule = currentModule.modules[part];
    if (!subModule) {
      throw new QwlError({
        code: "RENDERER_ERROR",
        message: `Module not found: ${part} in path ${path}`,
      });
    }
    currentModule = subModule;
    currentPrefix = currentPrefix ? `${currentPrefix}.${part}` : part;
    i++;
  }

  // Skip "tasks" keyword
  if (parts[i] === "tasks") i++;

  const taskName = parts[i];
  if (!taskName || !currentModule.tasks[taskName]) {
    throw new QwlError({
      code: "RENDERER_ERROR",
      message: `Task not found: ${taskName} in path ${path}`,
    });
  }

  return { module: currentModule, taskName, prefix: currentPrefix };
}

/**
 * Renders a variable template value with the given context.
 */
export function renderVariableTemplateValue(
  template: VariableTemplateValue,
  ctx: Record<string, unknown>,
): unknown {
  if (typeof template === "string") return template;
  if (template instanceof Template) return template.render(ctx);
  if (Array.isArray(template))
    return template.map((item) => renderVariableTemplateValue(item, ctx));
  if (typeof template === "object" && template !== null) {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(template)) {
      result[key] = renderVariableTemplateValue(value as VariableTemplateValue, ctx);
    }
    return result;
  }
  return template;
}

/**
 * Resolves a file path relative to a base directory.
 */
export function resolveFromBaseDir(baseDir: string, filePath: string): string {
  return resolvePathUtil(baseDir, filePath);
}

/**
 * Creates a function that resolves paths relative to a base directory.
 */
export function createResolvePathFunction(baseDir: string): (filePath: string) => string {
  return (filePath: string): string => resolveFromBaseDir(baseDir, filePath);
}
