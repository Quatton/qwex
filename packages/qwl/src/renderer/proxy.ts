import { Template } from "nunjucks";

import type { ModuleTemplate, TaskTemplate, VariableTemplate } from "../ast";

import { nj } from "../utils/templating";

export interface RenderedTask {
  cmd: string;
  desc?: string;
}

export class RenderContext {
  readonly renderedTasks = new Map<string, RenderedTask>();
  readonly renderedVars = new Map<string, unknown>();
  readonly pendingTasks = new Set<string>();
  readonly pendingVars = new Set<string>();
  readonly graph = new Map<string, Set<string>>();
  readonly mainTasks = new Set<string>();
  currentDeps = new Set<string>();
}

export interface ProxyCallbacks {
  renderVar: (
    ctx: RenderContext,
    module: ModuleTemplate,
    varName: string,
    prefix: string,
  ) => unknown;
  renderTask: (
    ctx: RenderContext,
    module: ModuleTemplate,
    taskName: string,
    prefix: string,
  ) => string;
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

    // Create uses() function for this context
    const usesFunction = this.createUsesFunction(module, prefix);

    return new Proxy(
      {
        vars: varsProxy,
        tasks: tasksProxy,
        modules: modulesProxy,
        uses: usesFunction,
      },
      {
        get: (target, key: string) => {
          if (key in target) return target[key as keyof typeof target];
          if (key in module.tasks) return this.createTaskRef(module, key, prefix);
          const subModule = module.modules[key];
          if (subModule) {
            const newPrefix = prefix ? `${prefix}.${key}` : key;
            return this.createAliasProxy(subModule, newPrefix);
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
        get: (_, key: string) => {
          if (!(key in module.tasks)) return undefined;
          return this.createTaskRef(module, key, prefix);
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
        const depName = this.callbacks.renderTask(this.ctx, module, taskName, prefix);
        this.ctx.currentDeps.add(depName);
        return depName.replace(/\./g, ":");
      },
      inline: (overrideVars: Record<string, unknown> = {}) => {
        return this.callbacks.renderTaskInline(this.ctx, module, taskName, prefix, overrideVars);
      },
    };
  }

  private createAliasProxy(module: ModuleTemplate, prefix: string): Record<string, unknown> {
    return new Proxy(
      {},
      {
        get: (_, key: string) => {
          if (key in module.tasks) return this.createTaskRef(module, key, prefix);
          const subModule = module.modules[key];
          if (subModule) {
            const newPrefix = prefix ? `${prefix}.${key}` : key;
            return this.createAliasProxy(subModule, newPrefix);
          }
          return undefined;
        },
      },
    );
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
      // Check if it's a task path
      if (path.startsWith("tasks.") || path.startsWith("modules.")) {
        return this.resolveTaskPath(module, path, prefix, overrideVars);
      }

      const globalUses = nj.getGlobal("uses");
      return globalUses(path);
    };
  }

  /**
   * Resolves a dotted task path and inlines the task
   * e.g., "tasks.myTask" or "modules.sub.tasks.subTask"
   */
  private resolveTaskPath(
    module: ModuleTemplate,
    path: string,
    prefix: string,
    overrideVars: Record<string, unknown>,
  ): string {
    const parts = path.split(".");
    let currentModule = module;
    let currentPrefix = prefix;
    let i = 0;

    // Navigate through modules
    while (i < parts.length - 2) {
      const part = parts[i];
      if (!part) {
        i++;
        continue;
      }
      if (part === "modules") {
        i++;
        continue;
      }
      const subModule = currentModule.modules[part];
      if (!subModule) {
        throw new Error(`uses(): Module not found: ${part} in path ${path}`);
      }
      currentModule = subModule;
      currentPrefix = currentPrefix ? `${currentPrefix}.${part}` : part;
      i++;
    }

    // Extract task part
    if (parts[i] === "tasks") {
      i++;
    }
    const taskName = parts[i];

    if (!taskName || !currentModule.tasks[taskName]) {
      throw new Error(`uses(): Task not found: ${taskName} in path ${path}`);
    }

    return this.callbacks.renderTaskInline(
      this.ctx,
      currentModule,
      taskName,
      currentPrefix,
      overrideVars,
    );
  }

  private renderVariableTemplate(
    template: VariableTemplate,
    ctx: Record<string, unknown>,
  ): unknown {
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
