import { Template } from "nunjucks";

import type { ModuleTemplate, TaskTemplate, VariableTemplate, VariableTemplateValue } from "../ast";

import { TASK_FN_PREFIX } from "../constants";
import { QwlError } from "../errors";
import { hash } from "../utils/hash";
import { getCwd, getDirFromSourcePath, resolvePath as resolvePathUtil } from "../utils/path";
import { RenderContext, RenderProxyFactory, type TaskRef } from "./proxy";

export interface TaskNode {
  key: string;
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
    const emittedHashes = new Set<bigint>();

    for (const [name, { cmd, desc }] of this.ctx.renderedTasks) {
      const cmdHash = hash(cmd);
      const dedupName = this.ctx.nameToDedup.get(name) ?? name;

      // Only emit the function if this is the canonical (first) name for this hash
      if (dedupName === name && !emittedHashes.has(cmdHash)) {
        emittedHashes.add(cmdHash);
        const node: TaskNode = {
          key: name,
          name: this.toBashName(dedupName),
          cmd,
          hash: `0x${cmdHash.toString(16)}`,
          desc,
        };
        if (this.ctx.mainTasks.has(name)) {
          main.push(node);
        } else {
          deps.push(node);
        }
      }
    }

    return { main, deps, graph: this.ctx.graph };
  }

  private renderTask(module: ModuleTemplate, taskName: string, prefix: string): TaskRef {
    const canonicalName = prefix ? `${prefix}.${taskName}` : taskName;

    // If already rendered, return the cached ref with deduplicated name
    if (this.ctx.renderedTasks.has(canonicalName)) {
      const rendered = this.ctx.renderedTasks.get(canonicalName)!;
      const dedupName = this.ctx.nameToDedup.get(canonicalName) ?? canonicalName;
      return {
        canonicalName,
        bashName: this.toBashName(dedupName),
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

      // If task has 'uses' field, resolve the referenced task
      let resolvedTask: TaskTemplate = task;
      let _resolvedModule = module;

      if (task.uses) {
        const usesPath = task.uses.split(".");

        let currentModule: ModuleTemplate = module;

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
      const cmdHash = hash(cmd);

      // Deduplication: check if we've seen this exact content before
      let dedupName: string;
      if (this.ctx.hashToName.has(cmdHash)) {
        // Reuse existing task name for this content
        dedupName = this.ctx.hashToName.get(cmdHash)!;
      } else {
        // First time seeing this content, register it
        dedupName = canonicalName;
        this.ctx.hashToName.set(cmdHash, canonicalName);
      }
      this.ctx.nameToDedup.set(canonicalName, dedupName);

      this.ctx.renderedTasks.set(canonicalName, { cmd, desc: task.desc });
      this.ctx.graph.set(canonicalName, new Set(this.ctx.currentDeps));

      return {
        canonicalName,
        bashName: this.toBashName(dedupName),
        hash: `0x${cmdHash.toString(16)}`,
      };
    } finally {
      this.ctx.pendingTasks.delete(canonicalName);
      this.ctx.currentDeps = savedDeps;
    }
  }

  private toBashName(name: string): string {
    const normalized = name.replace(/\./g, ":");
    return `${TASK_FN_PREFIX}${normalized}`;
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

    try {
      // If task has 'uses' field, resolve the referenced task
      let resolvedTask: TaskTemplate = task;
      let _resolvedModule = module;

      if (task.uses) {
        const usesPath = task.uses.split(".");
        let currentModule: ModuleTemplate = module;

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
      const resolvedPrefix = task.uses ? this.getModulePrefix(task.uses) : prefix;
      const proxy = this.proxyFactory.createForTask(_resolvedModule, modifiedTask, resolvedPrefix);

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
      const varTemplate = module.vars[varName];
      if (!varTemplate) return undefined;

      const __src__ = varTemplate.__meta__.sourcePath ?? module.__meta__.sourcePath;
      const __srcdir__ = getDirFromSourcePath(__src__);
      const __cwd__ = getCwd();
      const __dir__ = __srcdir__;
      const resolvePath = (filePath: string) => resolvePathUtil(__srcdir__, filePath);

      const proxy = {
        vars: new Proxy({}, { get: (_, key: string) => this.renderVar(module, key, prefix) }),
        tasks: {},
        modules: {},
        __cwd__,
        __src__,
        __srcdir__,
        __dir__,
        resolvePath,
      };

      const value = this.renderVariableTemplateValue(varTemplate.value, proxy);
      this.ctx.renderedVars.set(cacheKey, value);
      return value;
    } finally {
      this.ctx.pendingVars.delete(cacheKey);
    }
  }

  private renderVariableTemplateValue(
    template: VariableTemplateValue,
    ctx: Record<string, unknown>,
  ): unknown {
    if (typeof template === "string") return template;
    if (template instanceof Template) {
      return template.render(ctx);
    }
    if (Array.isArray(template))
      return template.map((item) => this.renderVariableTemplateValue(item, ctx));
    if (typeof template === "object" && template !== null) {
      const result: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(template)) {
        result[key] = this.renderVariableTemplateValue(value as VariableTemplateValue, ctx);
      }
      return result;
    }
    return template;
  }

  private preRenderVariableTemplate(
    template: VariableTemplate,
    ctx: Record<string, unknown>,
  ): VariableTemplate {
    return {
      value: this.preRenderVariableTemplateValue(template.value, ctx),
      __meta__: template.__meta__,
    };
  }

  private preRenderVariableTemplateValue(
    template: VariableTemplateValue,
    ctx: Record<string, unknown>,
  ): VariableTemplateValue {
    if (typeof template === "string") return template;
    if (template instanceof Template) {
      const savedDeps = this.ctx.currentDeps;
      this.ctx.currentDeps = new Set<string>();
      const rendered = template.render(ctx) as string;
      this.ctx.currentDeps = savedDeps;
      return rendered;
    }
    if (Array.isArray(template))
      return template.map((item) => this.preRenderVariableTemplateValue(item, ctx));
    if (typeof template === "object" && template !== null) {
      const result: Record<string, VariableTemplateValue> = {};
      for (const [key, value] of Object.entries(template)) {
        result[key] = this.preRenderVariableTemplateValue(value as VariableTemplateValue, ctx);
      }
      return result;
    }
    return template;
  }
}
