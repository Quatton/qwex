import { Template } from "nunjucks";

import type { ModuleTemplate, TaskTemplate, VariableTemplate } from "../ast";

import { QwlError } from "../errors";
import { nj } from "../utils/templating";

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
  /** Maps pre-rendered var values back to the deps captured during their rendering */
  readonly varCapturedDeps = new Map<string, Set<string>>();
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
  ) {}

  create(
    module: ModuleTemplate,
    task: TaskTemplate | null,
    prefix: string,
  ): Record<string, unknown> {
    const varsProxy = this.createVarsProxy(module, task, prefix);
    const tasksProxy = this.createTasksProxy(module, prefix);
    const modulesProxy = this.createModulesProxy(module, prefix);
    const usesFunction = this.createUsesFunction(module, prefix);
    const __renderContext = this.ctx;

    return new Proxy(
      {
        vars: varsProxy,
        tasks: tasksProxy,
        modules: modulesProxy,
        uses: usesFunction,
        __renderContext,
      },
      {
        get: (target, key: string | symbol) => {
          if (typeof key === "symbol") return undefined;
          if (key in target) return target[key as keyof typeof target];
          if (Object.hasOwn(module.tasks, key)) return this.createTaskRef(module, key, prefix);
          const subModule = module.modules[key];
          if (subModule) {
            const newPrefix = prefix ? `${prefix}.${key}` : key;
            return this.create(subModule, null, newPrefix);
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
      },
    );
  }

  createForTask(
    module: ModuleTemplate,
    task: TaskTemplate,
    prefix: string,
  ): Record<string, unknown> {
    return this.create(module, task, prefix);
  }

  private createVarsProxy(
    module: ModuleTemplate,
    task: TaskTemplate | null,
    prefix: string,
  ): object {
    return new Proxy(
      {},
      {
        get: (_, key: string) => {
          const taskVarTemplate = task?.vars[key];
          if (taskVarTemplate !== undefined) {
            return this.renderVariableTemplate(taskVarTemplate, {
              vars: this.createVarsProxy(module, task, prefix),
              tasks: {},
              modules: {},
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

  private createModulesProxy(module: ModuleTemplate, prefix: string): object {
    return new Proxy(
      {},
      {
        get: (_, modName: string) => {
          const subModule = module.modules[modName];
          if (!subModule) return undefined;
          const newPrefix = prefix ? `${prefix}.${modName}` : modName;
          return this.create(subModule, null, newPrefix);
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

  /**
   * Traverses a dotted path to find a module and task.
   * e.g., "tasks.myTask" or "modules.sub.tasks.subTask"
   */
  private resolveModulePath(
    startModule: ModuleTemplate,
    path: string,
    startPrefix: string,
  ): { module: ModuleTemplate; taskName: string; prefix: string } {
    const parts = path.split(".");
    let currentModule = startModule;
    let currentPrefix = startPrefix;
    let i = 0;

    // Skip leading "modules" keyword
    if (parts[i] === "modules") i++;

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
   * Creates a uses() function that can:
   * 1. Inline a task: uses("tasks.taskName") or uses("modules.sub.tasks.taskName")
   * 2. Read a file: uses("./path/to/file.sh") - delegated to global uses()
   */
  private createUsesFunction(
    module: ModuleTemplate,
    prefix: string,
  ): (path: string, overrideVars?: Record<string, unknown>) => string {
    return (path: string, overrideVars: Record<string, unknown> = {}): string => {
      if (path.startsWith("tasks.") || path.startsWith("modules.")) {
        const resolved = this.resolveModulePath(module, path, prefix);
        return this.callbacks.renderTaskInline(
          this.ctx,
          resolved.module,
          resolved.taskName,
          resolved.prefix,
          overrideVars,
        );
      }

      const globalUses = nj.getGlobal("uses");
      return globalUses(path);
    };
  }

  private renderVariableTemplate(
    template: VariableTemplate,
    ctx: Record<string, unknown>,
  ): unknown {
    if (typeof template === "string") return template;
    if (template instanceof Template) return template.render(ctx);
    if (Array.isArray(template))
      return template.map((item) => this.renderVariableTemplate(item, ctx));
    if (typeof template === "object" && template !== null) {
      const result: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(template)) {
        result[key] = this.renderVariableTemplate(value as VariableTemplate, ctx);
      }
      return result;
    }
    return template;
  }
}
