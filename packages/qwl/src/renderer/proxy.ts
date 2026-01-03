import fs from "node:fs";

import type { ModuleTemplate, TaskTemplate } from "../ast";

import { QwlError } from "../errors";
import { getDirFromSourcePath, resolvePath } from "../utils/path";
import { normalizeUsesPath, renderVariableTemplateValue, resolveModulePath } from "./normalize";

export interface RenderedTask {
  cmd: string;
  desc?: string;
}

/** Result of rendering a task reference */
export interface TaskRef {
  canonicalName: string; // e.g., "log.tasks.info"
  bashName: string; // e.g., "log:tasks:info"
  hash: string;
}

export class RenderContext {
  readonly renderedTasks = new Map<string, RenderedTask>();
  readonly renderedVars = new Map<string, unknown>();
  readonly pendingTasks = new Set<string>();
  readonly pendingVars = new Set<string>();
  readonly graph = new Map<string, Set<string>>();
  readonly mainTasks = new Set<string>();
  currentDeps = new Set<string>();
  /** Maps content hash -> first task name with that hash (for deduplication) */
  readonly hashToName = new Map<bigint, string>();
  /** Maps canonical task name -> deduplicated bash name */
  readonly nameToDedup = new Map<string, string>();
  /** Maps module prefix -> parent proxy for super keyword support */
  readonly prefixToParentProxy = new Map<string, Record<string, unknown>>();
}

export interface ProxyCallbacks {
  renderVar: (
    ctx: RenderContext,
    module: ModuleTemplate,
    varName: string,
    prefix: string,
  ) => unknown;
  /** Renders a task and returns its reference info */
  renderTask: (
    ctx: RenderContext,
    module: ModuleTemplate,
    taskName: string,
    prefix: string,
  ) => TaskRef;
  renderTaskInline: (
    ctx: RenderContext,
    module: ModuleTemplate,
    taskName: string,
    prefix: string,
    overrideVars: Record<string, unknown>,
  ) => string;
}

export class RenderProxyFactory {
  constructor(
    private ctx: RenderContext,
    private callbacks: ProxyCallbacks,
    private rootModule: ModuleTemplate,
  ) {}

  create(
    module: ModuleTemplate,
    task: TaskTemplate | null,
    prefix: string,
    parentProxy?: Record<string, unknown>,
  ): Record<string, unknown> {
    const { __src__, __dir__ } = this.getSourceInfo(module, task);
    const varsProxy = this.createVarsProxy(module, task, prefix);
    const tasksProxy = this.createTasksProxy(module, prefix);
    const usesFunction = this.createUsesFunction(module, prefix, __dir__);
    const resolvePathFunction = (filePath: string, dir = __dir__) => resolvePath(dir, filePath);
    const __cwd__ = process.cwd();

    // Look up parent proxy from context if not provided
    const resolvedParentProxy = parentProxy ?? this.ctx.prefixToParentProxy.get(prefix);

    // Create the current proxy first (without modules/super to avoid circular reference)
    const currentProxy: Record<string, unknown> = {
      vars: varsProxy,
      tasks: tasksProxy,
      modules: {}, // placeholder, will be replaced
      uses: usesFunction,
      resolvePath: resolvePathFunction,
      __cwd__,
      __src__,
      __dir__,
    };

    // Add super reference to parent module's proxy
    if (resolvedParentProxy) {
      currentProxy.super = resolvedParentProxy;
    }

    // Now create the full proxy with proper module access
    const fullProxy = new Proxy(currentProxy, {
      get: (target, key: string | symbol) => {
        if (typeof key === "symbol") return undefined;
        if (key === "modules") {
          // Lazy create modules proxy with fullProxy as parent
          return this.createModulesProxy(module, prefix, fullProxy);
        }
        if (key in target) return target[key as keyof typeof target];
        if (Object.hasOwn(module.tasks, key)) return this.createTaskRef(module, key, prefix);
        const subModule = module.modules[key];
        if (subModule) {
          const newPrefix = prefix ? `${prefix}.${key}` : key;
          // Register parent proxy for the submodule prefix
          this.ctx.prefixToParentProxy.set(newPrefix, fullProxy);
          // Pass fullProxy as parentProxy for sub-modules
          return this.create(subModule, null, newPrefix, fullProxy);
        }
        return undefined;
      },
      has: (target, key: string) => {
        if (key in target) return true;
        if (Object.hasOwn(module.tasks, key)) return true;
        if (Object.hasOwn(module.modules, key)) return true;
        return false;
      },
      ownKeys: (target) => {
        return [
          ...Object.keys(target),
          ...Object.keys(module.tasks),
          ...Object.keys(module.modules),
        ];
      },
      getOwnPropertyDescriptor: (target, key: string) => {
        if (key in target || key in module.tasks || key in module.modules) {
          return { enumerable: true, configurable: true };
        }
        return undefined;
      },
    });

    return fullProxy;
  }

  createForTask(
    module: ModuleTemplate,
    task: TaskTemplate,
    prefix: string,
    parentProxy?: Record<string, unknown>,
  ): Record<string, unknown> {
    return this.create(module, task, prefix, parentProxy);
  }

  private createVarsProxy(
    module: ModuleTemplate,
    task: TaskTemplate | null,
    prefix: string,
  ): object {
    const { __src__, __dir__ } = this.getSourceInfo(module, task);
    const __cwd__ = process.cwd();

    return new Proxy(
      {},
      {
        get: (_, key: string) => {
          const taskVarTemplate = task?.vars[key];
          if (taskVarTemplate !== undefined) {
            const varSrc = taskVarTemplate.__meta__.sourcePath ?? __src__;
            const varDir = getDirFromSourcePath(varSrc);
            return renderVariableTemplateValue(taskVarTemplate.value, {
              vars: this.createVarsProxy(module, task, prefix),
              tasks: {},
              modules: {},
              __cwd__,
              __src__: varSrc,
              __dir__: varDir,
              resolvePath: (filePath: string, dir = varDir) => resolvePath(dir, filePath),
            });
          }
          const moduleVarTemplate = module.vars[key];
          if (!moduleVarTemplate) return undefined;
          return this.callbacks.renderVar(this.ctx, module, key, prefix);
        },
      },
    );
  }

  private createTasksProxy(module: ModuleTemplate, prefix: string): object {
    return new Proxy(
      {},
      {
        get: (_, key: string | symbol) => {
          if (typeof key === "symbol") return undefined;
          if (!Object.hasOwn(module.tasks, key)) return undefined;
          return this.createTaskRef(module, key, prefix);
        },
        has: (_, key: string) => {
          return Object.hasOwn(module.tasks, key);
        },
        ownKeys: () => {
          return Object.keys(module.tasks);
        },
        getOwnPropertyDescriptor: (_, key: string) => {
          if (key in module.tasks) {
            return { enumerable: true, configurable: true };
          }
          return undefined;
        },
      },
    );
  }

  private createModulesProxy(
    module: ModuleTemplate,
    prefix: string,
    parentProxy?: Record<string, unknown>,
  ): object {
    return new Proxy(
      {},
      {
        get: (_, modName: string) => {
          const subModule = module.modules[modName];
          if (!subModule) return undefined;
          const newPrefix = prefix ? `${prefix}.${modName}` : modName;
          // Register parent proxy for the submodule prefix
          if (parentProxy) {
            this.ctx.prefixToParentProxy.set(newPrefix, parentProxy);
          }
          return this.create(subModule, null, newPrefix, parentProxy);
        },
      },
    );
  }

  private createTaskRef(module: ModuleTemplate, taskName: string, prefix: string) {
    return {
      toString: () => {
        // Render the task and get its reference info
        const ref = this.callbacks.renderTask(this.ctx, module, taskName, prefix);
        // Add to deps - this happens at access time, not pre-render time
        this.ctx.currentDeps.add(ref.canonicalName);
        return ref.bashName;
      },
      inline: (overrideVars: Record<string, unknown> = {}) => {
        return this.callbacks.renderTaskInline(this.ctx, module, taskName, prefix, overrideVars);
      },
    };
  }

  private getSourceInfo(
    module: ModuleTemplate,
    task: TaskTemplate | null,
  ): { __src__: string | null; __dir__: string } {
    const src = task?.__meta__?.sourcePath ?? module.__meta__.sourcePath;
    return { __src__: src ?? null, __dir__: getDirFromSourcePath(src) };
  }

  private createUsesFunction(
    module: ModuleTemplate,
    prefix: string,
    baseDir: string,
  ): (path: string, overrideVars?: Record<string, unknown>) => string {
    return (path: string, overrideVars: Record<string, unknown> = {}): string => {
      if (path.startsWith("tasks.") || path.startsWith("modules.")) {
        const normalizedPath = normalizeUsesPath(path);
        const resolved = resolveModulePath(this.rootModule, module, normalizedPath, prefix);
        return this.callbacks.renderTaskInline(
          this.ctx,
          resolved.module,
          resolved.taskName,
          resolved.prefix,
          overrideVars,
        );
      }

      const resolvedPath = resolvePath(baseDir, path);
      try {
        return fs.readFileSync(resolvedPath, "utf8");
      } catch (e) {
        throw new QwlError({
          code: "RENDERER_ERROR",
          message: `uses(): Failed to read file '${path}' resolved to '${resolvedPath}': ${(e as Error).message}`,
        });
      }
    };
  }
}
