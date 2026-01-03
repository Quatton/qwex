import { Template } from "nunjucks";

import type { ModuleTemplate, TaskTemplate, VariableTemplate, VariableTemplateValue } from "../ast";

import { TASK_FN_PREFIX } from "../constants";
import { QwlError } from "../errors";
import { hash } from "../utils/hash";
import { getCwd, getDirFromSourcePath, resolvePath as resolvePathUtil } from "../utils/path";
import { RenderContext, RenderProxyFactory, type TaskRef } from "./proxy";
import { normalizeUsesPath, resolveModulePath, renderVariableTemplateValue } from "./normalize";

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

  private toBashName(name: string): string {
    return `${TASK_FN_PREFIX}${name.replace(/\./g, ":")}`;
  }

  renderAllTasks(module: ModuleTemplate): RenderResult {
    this.rootModule = module;
    this.ctx = new RenderContext();
    this.proxyFactory = new RenderProxyFactory(this.ctx, {
      renderVar: (ctx, mod, name, prefix) => this.renderVar(mod, name, prefix),
      renderTask: (ctx, mod, name, prefix) => this.renderTask(mod, name, prefix),
      renderTaskInline: (ctx, mod, name, prefix, vars) =>
        this.renderTaskInline(mod, name, prefix, vars),
    }, module);

    for (const taskName of Object.keys(module.tasks)) {
      this.ctx.mainTasks.add(taskName);
    }

    for (const taskName of Object.keys(module.tasks)) {
      this.renderTask(module, taskName, "");
    }

    const main: TaskNode[] = [];
    const deps: TaskNode[] = [];
    const emittedHashes = new Set<bigint>();

    for (const [name, renderedTask] of this.ctx.renderedTasks.entries()) {
      const { cmd, desc } = renderedTask;
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

  private renderTask(module: ModuleTemplate, name: string, prefix: string): TaskRef {
    const fullName = prefix ? `${prefix}.${name}` : name;

    if (this.ctx.renderedTasks.has(fullName)) {
      const dedupName = this.ctx.nameToDedup.get(fullName) ?? fullName;
      const { cmd } = this.ctx.renderedTasks.get(fullName)!;
      const cmdHash = hash(cmd);
      return { canonicalName: fullName, bashName: this.toBashName(dedupName), hash: `0x${cmdHash.toString(16)}` };
    }

    if (this.ctx.pendingTasks.has(fullName)) {
      throw new QwlError({
        code: "RENDERER_ERROR",
        message: `Circular task dependency detected: ${fullName}`,
      });
    }

    this.ctx.pendingTasks.add(fullName);

    try {
      let task = module.tasks[name];
      if (!task) {
        throw new QwlError({
          code: "RENDERER_ERROR",
          message: `Task not found: ${name}`,
        });
      }

      let desc = task.desc;
      let resolvedTask = task;
      let _resolvedModule = module;
      let varLayers: Array<{ vars: Record<string, VariableTemplate>, module: ModuleTemplate, prefix: string }> = [
        { vars: task.vars, module, prefix }
      ];

      if (task.uses) {
        let usesPath = task.uses;
        const normalizedUsesPath = normalizeUsesPath(usesPath);
        const resolved = resolveModulePath(this.rootModule, module, normalizedUsesPath, prefix);
        resolvedTask = resolved.module.tasks[resolved.taskName]!;
        _resolvedModule = resolved.module;
        varLayers.push({
          vars: resolvedTask.vars,
          module: _resolvedModule,
          prefix: resolved.prefix,
        });
      }

      // Recursively resolve uses if the resolved task also has uses
      let currentResolvedPrefix = task.uses
        ? this.getModulePrefix(task.uses.startsWith("modules") ? task.uses : `modules.${task.uses}`)
        : prefix;

      while (resolvedTask.uses) {
        let usesPath = resolvedTask.uses;
        const normalizedUsesPath = normalizeUsesPath(usesPath);
        const resolved = resolveModulePath(
          this.rootModule,
          _resolvedModule,
          normalizedUsesPath,
          currentResolvedPrefix,
        );
        resolvedTask = resolved.module.tasks[resolved.taskName]!;
        _resolvedModule = resolved.module;
        currentResolvedPrefix = resolved.prefix;
        varLayers.push({
          vars: resolvedTask.vars,
          module: _resolvedModule,
          prefix: currentResolvedPrefix,
        });
      }

      // Merge vars by resolving templates in order
      const resolvedVarLayers: Array<Record<string, VariableTemplate>> = [];
      let currentVars: Record<string, VariableTemplate> = {};
      for (const layer of varLayers) {
        // Create proxy with current resolved vars
        const tempTask: TaskTemplate = { ...resolvedTask, vars: currentVars };
        const tempProxy = this.proxyFactory.createForTask(layer.module, tempTask, layer.prefix);
        const resolvedLayer: Record<string, VariableTemplate> = {};
        for (const [key, varTemplate] of Object.entries(layer.vars)) {
          resolvedLayer[key] = this.preRenderVariableTemplate(varTemplate, tempProxy);
        }
        resolvedVarLayers.push(resolvedLayer);
        // Add to currentVars for next layer
        Object.assign(currentVars, resolvedLayer);
      }

      // Now merge all resolved layers, with later layers overriding
      const mergedVars: Record<string, VariableTemplate> = {};
      for (let i = resolvedVarLayers.length - 1; i >= 0; i--) {
        const layer = resolvedVarLayers[i];
        Object.assign(mergedVars, layer);
      }
      const modifiedTask: TaskTemplate = { ...resolvedTask, vars: mergedVars };

      // Use the resolved module for the proxy so task references resolve correctly
      const resolvedPrefix = currentResolvedPrefix;
      const proxy = this.proxyFactory.createForTask(_resolvedModule, modifiedTask, resolvedPrefix);
      const cmd = resolvedTask.cmd.render(proxy);
      const cmdHash = hash(cmd);

      // Deduplication: check if we've seen this exact content before
      let dedupName: string;
      if (this.ctx.hashToName.has(cmdHash)) {
        // Reuse existing task name for this content
        dedupName = this.ctx.hashToName.get(cmdHash)!;
      } else {
        dedupName = fullName;
        this.ctx.hashToName.set(cmdHash, fullName);
      }
      this.ctx.nameToDedup.set(fullName, dedupName);
      this.ctx.renderedTasks.set(fullName, { cmd, desc });

      // Track dependencies
      if (!this.ctx.graph.has(fullName)) {
        this.ctx.graph.set(fullName, new Set());
      }
      for (const dep of this.ctx.currentDeps) {
        this.ctx.graph.get(fullName)!.add(dep);
      }

      return { canonicalName: fullName, bashName: this.toBashName(dedupName), hash: `0x${cmdHash.toString(16)}` };
    } finally {
      this.ctx.pendingTasks.delete(fullName);
    }
  }

  private renderTaskInline(
    module: ModuleTemplate,
    name: string,
    prefix: string,
    overrideVars: Record<string, unknown>,
  ): string {
    let task = module.tasks[name];
    if (!task) {
      throw new QwlError({
        code: "RENDERER_ERROR",
        message: `Task not found: ${name}`,
      });
    }

    let resolvedTask = task;
    let _resolvedModule = module;
    let varLayers: Array<{ vars: Record<string, VariableTemplate>, module: ModuleTemplate, prefix: string }> = [
      { vars: task.vars, module, prefix }
    ];

    if (task.uses) {
      let usesPath = task.uses;
      const normalizedUsesPath = normalizeUsesPath(usesPath);
      const resolved = resolveModulePath(this.rootModule, module, normalizedUsesPath, prefix);
      resolvedTask = resolved.module.tasks[resolved.taskName]!;
      _resolvedModule = resolved.module;
      varLayers.push({
        vars: resolvedTask.vars,
        module: _resolvedModule,
        prefix: resolved.prefix,
      });
    }

    // Recursively resolve uses if the resolved task also has uses
    let currentResolvedPrefix = task.uses
      ? this.getModulePrefix(task.uses.startsWith("modules") ? task.uses : `modules.${task.uses}`)
      : prefix;

    while (resolvedTask.uses) {
      let usesPath = resolvedTask.uses;
      const normalizedUsesPath = normalizeUsesPath(usesPath);
      const resolved = resolveModulePath(
        this.rootModule,
        _resolvedModule,
        normalizedUsesPath,
        currentResolvedPrefix,
      );
      resolvedTask = resolved.module.tasks[resolved.taskName]!;
      _resolvedModule = resolved.module;
      currentResolvedPrefix = resolved.prefix;
      varLayers.push({
        vars: resolvedTask.vars,
        module: _resolvedModule,
        prefix: currentResolvedPrefix,
      });
    }

    // Merge vars by resolving templates in order
    const resolvedVarLayers: Array<Record<string, VariableTemplate>> = [];
    let currentVars: Record<string, VariableTemplate> = {};
    for (const layer of varLayers) {
      // Create proxy with current resolved vars
      const tempTask: TaskTemplate = { ...resolvedTask, vars: currentVars };
      const tempProxy = this.proxyFactory.createForTask(layer.module, tempTask, layer.prefix);

      const resolvedLayer: Record<string, VariableTemplate> = {};
      for (const [key, varTemplate] of Object.entries(layer.vars)) {
        resolvedLayer[key] = this.preRenderVariableTemplate(varTemplate, tempProxy);
      }
      resolvedVarLayers.push(resolvedLayer);
      // Add to currentVars for next layer
      Object.assign(currentVars, resolvedLayer);
    }

    // Now merge all resolved layers, with later layers overriding
    const mergedVars: Record<string, VariableTemplate> = {};
    for (let i = resolvedVarLayers.length - 1; i >= 0; i--) {
      const layer = resolvedVarLayers[i];
      Object.assign(mergedVars, layer);
    }
    const modifiedTask: TaskTemplate = { ...resolvedTask, vars: mergedVars };
    const resolvedPrefix = currentResolvedPrefix;
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

      const value = renderVariableTemplateValue(varTemplate.value, proxy);
      this.ctx.renderedVars.set(cacheKey, value);
      return value;
    } finally {
      this.ctx.pendingVars.delete(cacheKey);
    }
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
