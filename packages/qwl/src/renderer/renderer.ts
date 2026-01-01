import { Template } from "nunjucks";

import type { ModuleTemplate, TaskTemplate, VariableTemplate } from "../ast";

import { QwlError } from "../errors";
import { hash } from "../utils/hash";
import { setCurrentModulePath } from "../utils/templating";
import { RenderContext, RenderProxyFactory } from "./proxy";

export interface TaskNode {
  name: string;
  cmd: string;
  hash: string;
  desc?: string;
}

export interface RenderResult {
  main: TaskNode[];
  deps: TaskNode[];
  graph: Map<string, Set<string>>;
}

export class Renderer {
  private ctx!: RenderContext;
  private proxyFactory!: RenderProxyFactory;

  renderAllTasks(module: ModuleTemplate): RenderResult {
    this.ctx = new RenderContext();
    this.proxyFactory = new RenderProxyFactory(this.ctx, {
      renderVar: (ctx, mod, name, prefix) => this.renderVar(mod, name, prefix),
      renderTask: (ctx, mod, name, prefix) => this.renderTask(mod, name, prefix),
      renderTaskInline: (ctx, mod, name, prefix, vars) =>
        this.renderTaskInline(mod, name, prefix, vars),
    });

    for (const taskName of Object.keys(module.tasks)) {
      this.ctx.mainTasks.add(taskName);
    }

    for (const taskName of Object.keys(module.tasks)) {
      this.renderTask(module, taskName, "");
    }

    const main: TaskNode[] = [];
    const deps: TaskNode[] = [];

    for (const [name, { cmd, desc }] of this.ctx.renderedTasks) {
      const node: TaskNode = { name, cmd, hash: hash(cmd).toString(), desc };
      if (this.ctx.mainTasks.has(name)) {
        main.push(node);
      } else {
        deps.push(node);
      }
    }

    return { main, deps, graph: this.ctx.graph };
  }

  private renderTask(module: ModuleTemplate, taskName: string, prefix: string): string {
    const canonicalName = prefix ? `${prefix}.${taskName}` : taskName;

    if (this.ctx.renderedTasks.has(canonicalName)) return canonicalName;

    if (this.ctx.pendingTasks.has(canonicalName)) {
      throw new QwlError({
        code: "RENDERER_ERROR",
        message: `Circular task dependency detected: ${canonicalName}`,
      });
    }

    this.ctx.pendingTasks.add(canonicalName);
    const savedDeps = this.ctx.currentDeps;
    this.ctx.currentDeps = new Set();

    try {
      const task = module.tasks[taskName];
      if (!task) {
        throw new QwlError({
          code: "RENDERER_ERROR",
          message: `Task not found: ${taskName} in module with prefix "${prefix}"`,
        });
      }

      // Set module path for uses() function
      setCurrentModulePath(module.__meta__.sourcePath ?? null);

      const proxy = this.proxyFactory.createForTask(module, task, prefix);
      const cmd = task.cmd.render(proxy);

      this.ctx.renderedTasks.set(canonicalName, { cmd, desc: task.desc });
      this.ctx.graph.set(canonicalName, new Set(this.ctx.currentDeps));

      return canonicalName;
    } finally {
      this.ctx.pendingTasks.delete(canonicalName);
      this.ctx.currentDeps = savedDeps;
      setCurrentModulePath(null);
    }
  }

  private renderTaskInline(
    module: ModuleTemplate,
    taskName: string,
    prefix: string,
    overrideVars: Record<string, unknown>,
  ): string {
    const task = module.tasks[taskName];
    if (!task) {
      throw new QwlError({
        code: "RENDERER_ERROR",
        message: `Task not found for inline: ${taskName}`,
      });
    }

    // Set module path for uses() function
    setCurrentModulePath(module.__meta__.sourcePath ?? null);

    try {
      const modifiedTask: TaskTemplate = { ...task, vars: { ...task.vars } };
      const proxy = this.proxyFactory.createForTask(module, modifiedTask, prefix);

      const proxyWithOverrides = {
        ...proxy,
        vars: new Proxy(proxy.vars as object, {
          get(target, key: string) {
            if (key in overrideVars) return overrideVars[key];
            return Reflect.get(target, key);
          },
        }),
      };

      return task.cmd.render(proxyWithOverrides);
    } finally {
      setCurrentModulePath(null);
    }
  }

  private renderVar(module: ModuleTemplate, varName: string, prefix: string): unknown {
    const cacheKey = prefix ? `${prefix}.${varName}` : varName;

    if (this.ctx.renderedVars.has(cacheKey)) {
      return this.ctx.renderedVars.get(cacheKey);
    }

    if (this.ctx.pendingVars.has(cacheKey)) {
      throw new QwlError({
        code: "RENDERER_ERROR",
        message: `Circular variable dependency detected: ${cacheKey}`,
      });
    }

    this.ctx.pendingVars.add(cacheKey);

    try {
      const template = module.vars[varName];
      if (!template) return undefined;

      const proxy = {
        vars: new Proxy({}, { get: (_, key: string) => this.renderVar(module, key, prefix) }),
        tasks: {},
        modules: {},
      };

      const value = this.renderVariableTemplate(template, proxy);
      this.ctx.renderedVars.set(cacheKey, value);
      return value;
    } finally {
      this.ctx.pendingVars.delete(cacheKey);
    }
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
