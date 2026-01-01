import { Template } from "nunjucks";

import type { ModuleTemplate, TaskTemplate, VariableTemplate } from "../ast";

import { QwlError } from "../errors";
import { hash } from "../utils/hash";
import { setCurrentModulePath } from "../utils/templating";
import { RenderContext, RenderProxyFactory, type TaskRef } from "./proxy";

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
  private rootModule!: ModuleTemplate;

  /**
   * Extract the module prefix from a uses path like "modules.steps.tasks.compose" -> "steps"
   */
  private getModulePrefix(usesPath: string): string {
    const parts = usesPath.split(".");
    const moduleParts: string[] = [];
    let i = 0;
    if (parts[i] === "modules") i++;
    while (i < parts.length && parts[i] !== "tasks") {
      moduleParts.push(parts[i]!);
      i++;
    }
    return moduleParts.join(".");
  }

  renderAllTasks(module: ModuleTemplate): RenderResult {
    this.rootModule = module;
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
      const node: TaskNode = { name, cmd, hash: `0x${hash(cmd).toString(16)}`, desc };
      if (this.ctx.mainTasks.has(name)) {
        main.push(node);
      } else {
        deps.push(node);
      }
    }

    return { main, deps, graph: this.ctx.graph };
  }

  private renderTask(module: ModuleTemplate, taskName: string, prefix: string): TaskRef {
    const canonicalName = prefix ? `${prefix}.${taskName}` : taskName;
    const bashName = canonicalName.replace(/\./g, ":");

    // If already rendered, return the cached ref
    if (this.ctx.renderedTasks.has(canonicalName)) {
      const rendered = this.ctx.renderedTasks.get(canonicalName)!;
      return {
        canonicalName,
        bashName,
        hash: `0x${hash(rendered.cmd).toString(16)}`,
      };
    }

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

      // If task has 'uses' field, resolve the referenced task
      let resolvedTask: TaskTemplate = task;
      let _resolvedModule = module;

      if (task.uses) {
        const usesPath = task.uses.split(".");
        let currentModule: ModuleTemplate = this.rootModule;

        // Navigate to the correct module/task
        // Path format: "modules.moduleName.tasks.taskName"
        let i = 0;
        if (usesPath[i] === "modules") i++; // Skip "modules" prefix

        // Navigate through module hierarchy
        while (i < usesPath.length && usesPath[i] !== "tasks") {
          const nextModule = currentModule.modules[usesPath[i]!];
          if (!nextModule) {
            throw new QwlError({
              code: "RENDERER_ERROR",
              message: `Module not found in uses path: ${task.uses}`,
            });
          }
          currentModule = nextModule;
          i++;
        }

        // Skip "tasks" keyword
        if (usesPath[i] === "tasks") i++;

        // Get the task name
        const referencedTaskName = usesPath[i]!;
        const foundTask = currentModule.tasks[referencedTaskName];
        if (!foundTask) {
          throw new QwlError({
            code: "RENDERER_ERROR",
            message: `Task not found in uses: ${task.uses}`,
          });
        }
        resolvedTask = foundTask;
        _resolvedModule = currentModule;
      }

      // Pre-render caller's vars in their original context before merging
      // This ensures templates like {{ vars.demo_dir }} get the caller's values
      const callerProxy = this.proxyFactory.createForTask(module, task, prefix);
      const preRenderedTaskVars: Record<string, VariableTemplate> = {};

      for (const [key, varTemplate] of Object.entries(task.vars)) {
        preRenderedTaskVars[key] = this.preRenderVariableTemplate(varTemplate, callerProxy);
      }

      // Merge vars: pre-rendered caller's vars override resolved task's vars
      const mergedVars = { ...resolvedTask.vars, ...preRenderedTaskVars };
      const modifiedTask: TaskTemplate = { ...resolvedTask, vars: mergedVars };

      // Use the resolved module for the proxy so task references resolve correctly
      const resolvedPrefix = task.uses ? this.getModulePrefix(task.uses) : prefix;
      const proxy = this.proxyFactory.createForTask(_resolvedModule, modifiedTask, resolvedPrefix);
      const cmd = resolvedTask.cmd.render(proxy);

      this.ctx.renderedTasks.set(canonicalName, { cmd, desc: task.desc });
      this.ctx.graph.set(canonicalName, new Set(this.ctx.currentDeps));

      return {
        canonicalName,
        bashName,
        hash: `0x${hash(cmd).toString(16)}`,
      };
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
      // If task has 'uses' field, resolve the referenced task
      let resolvedTask: TaskTemplate = task;
      let _resolvedModule = module;

      if (task.uses) {
        const usesPath = task.uses.split(".");
        let currentModule: ModuleTemplate = this.rootModule;

        // Navigate to the correct module/task
        // Path format: "modules.moduleName.tasks.taskName"
        let i = 0;
        if (usesPath[i] === "modules") i++; // Skip "modules" prefix

        // Navigate through module hierarchy
        while (i < usesPath.length && usesPath[i] !== "tasks") {
          const nextModule = currentModule.modules[usesPath[i]!];
          if (!nextModule) {
            throw new QwlError({
              code: "RENDERER_ERROR",
              message: `Module not found in uses path: ${task.uses}`,
            });
          }
          currentModule = nextModule;
          i++;
        }

        // Skip "tasks" keyword
        if (usesPath[i] === "tasks") i++;

        // Get the task name
        const referencedTaskName = usesPath[i]!;
        const foundTask = currentModule.tasks[referencedTaskName];
        if (!foundTask) {
          throw new QwlError({
            code: "RENDERER_ERROR",
            message: `Task not found in uses: ${task.uses}`,
          });
        }
        resolvedTask = foundTask;
        _resolvedModule = currentModule;
      }

      // Pre-render task vars in current context before merging
      // This ensures nested templates get the right variable scope
      const currentProxy = this.proxyFactory.createForTask(module, task, prefix);
      const preRenderedTaskVars: Record<string, VariableTemplate> = {};

      for (const [key, varTemplate] of Object.entries(task.vars)) {
        preRenderedTaskVars[key] = this.preRenderVariableTemplate(varTemplate, currentProxy);
      }

      // Merge vars: pre-rendered task vars override resolved task's vars
      const mergedVars = { ...resolvedTask.vars, ...preRenderedTaskVars };
      const modifiedTask: TaskTemplate = { ...resolvedTask, vars: mergedVars };
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

      return resolvedTask.cmd.render(proxyWithOverrides);
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

  private preRenderVariableTemplate(
    template: VariableTemplate,
    ctx: Record<string, unknown>,
  ): VariableTemplate {
    if (typeof template === "string") return template;
    if (template instanceof Template) {
      // Render the template - task refs will add to currentDeps when toString() is called
      // Use a temp set to capture deps without polluting the current task's deps
      const savedDeps = this.ctx.currentDeps;
      this.ctx.currentDeps = new Set<string>();
      const rendered = template.render(ctx) as string;
      // Store captured deps keyed by the rendered value
      // When this value is accessed inside {% context %}, replay these deps
      if (this.ctx.currentDeps.size > 0) {
        this.ctx.varCapturedDeps.set(rendered, new Set(this.ctx.currentDeps));
      }
      this.ctx.currentDeps = savedDeps;
      return rendered;
    }
    if (Array.isArray(template))
      return template.map((item) => this.preRenderVariableTemplate(item, ctx));
    if (typeof template === "object" && template !== null) {
      const result: Record<string, VariableTemplate> = {};
      for (const [key, value] of Object.entries(template)) {
        result[key] = this.preRenderVariableTemplate(value as VariableTemplate, ctx);
      }
      return result;
    }
    return template;
  }
}
