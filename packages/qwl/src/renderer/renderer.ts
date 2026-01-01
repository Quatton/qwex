import { Template } from "nunjucks";
import type { ModuleTemplate, TaskTemplate, VariableTemplate } from "../ast";
import { QwlError } from "../errors";
import { hash } from "../utils/hash";
import {
  createRenderContext,
  createTaskRenderProxy,
  type RenderContext,
  type ProxyCallbacks,
} from "./proxy";

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
  renderAllTasks(module: ModuleTemplate): RenderResult {
    const ctx = createRenderContext();

    for (const taskName of Object.keys(module.tasks)) {
      ctx.mainTasks.add(taskName);
    }

    for (const taskName of Object.keys(module.tasks)) {
      this.renderTask(ctx, module, taskName, "");
    }

    const main: TaskNode[] = [];
    const deps: TaskNode[] = [];

    for (const [name, { cmd, desc }] of ctx.renderedTasks) {
      const node: TaskNode = { name, cmd, hash: hash(cmd).toString(), desc };
      if (ctx.mainTasks.has(name)) {
        main.push(node);
      } else {
        deps.push(node);
      }
    }

    return { main, deps, graph: ctx.graph };
  }

  private renderTask(
    ctx: RenderContext,
    module: ModuleTemplate,
    taskName: string,
    prefix: string
  ): string {
    const canonicalName = prefix ? `${prefix}.${taskName}` : taskName;

    if (ctx.renderedTasks.has(canonicalName)) {
      return canonicalName;
    }

    if (ctx.pendingTasks.has(canonicalName)) {
      throw new QwlError({
        code: "RENDERER_ERROR",
        message: `Circular task dependency detected: ${canonicalName}`,
      });
    }

    ctx.pendingTasks.add(canonicalName);
    const savedDeps = ctx.currentDeps;
    ctx.currentDeps = new Set();

    try {
      const task = module.tasks[taskName];
      if (!task) {
        throw new QwlError({
          code: "RENDERER_ERROR",
          message: `Task not found: ${taskName} in module with prefix "${prefix}"`,
        });
      }

      const proxy = createTaskRenderProxy(ctx, module, task, prefix, this.createCallbacks());
      const cmd = task.cmd.render(proxy);

      ctx.renderedTasks.set(canonicalName, { cmd, desc: task.desc });
      ctx.graph.set(canonicalName, new Set(ctx.currentDeps));

      return canonicalName;
    } finally {
      ctx.pendingTasks.delete(canonicalName);
      ctx.currentDeps = savedDeps;
    }
  }

  // Inline render: does NOT register as separate task node
  private renderTaskInline(
    ctx: RenderContext,
    module: ModuleTemplate,
    taskName: string,
    prefix: string,
    overrideVars: Record<string, unknown>
  ): string {
    const task = module.tasks[taskName];
    if (!task) {
      throw new QwlError({
        code: "RENDERER_ERROR",
        message: `Task not found for inline: ${taskName}`,
      });
    }

    const modifiedTask: TaskTemplate = { ...task, vars: { ...task.vars } };
    const proxy = createTaskRenderProxy(ctx, module, modifiedTask, prefix, this.createCallbacks());

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
  }

  private renderVar(
    ctx: RenderContext,
    module: ModuleTemplate,
    varName: string,
    prefix: string
  ): unknown {
    const cacheKey = prefix ? `${prefix}.${varName}` : varName;

    if (ctx.renderedVars.has(cacheKey)) {
      return ctx.renderedVars.get(cacheKey);
    }

    if (ctx.pendingVars.has(cacheKey)) {
      throw new QwlError({
        code: "RENDERER_ERROR",
        message: `Circular variable dependency detected: ${cacheKey}`,
      });
    }

    ctx.pendingVars.add(cacheKey);

    try {
      const template = module.vars[varName];
      if (!template) return undefined;

      const proxy = {
        vars: new Proxy({}, { get: (_, key: string) => this.renderVar(ctx, module, key, prefix) }),
        tasks: {},
        modules: {},
      };

      const value = this.renderVariableTemplate(template, proxy);
      ctx.renderedVars.set(cacheKey, value);
      return value;
    } finally {
      ctx.pendingVars.delete(cacheKey);
    }
  }

  private renderVariableTemplate(template: VariableTemplate, ctx: Record<string, unknown>): unknown {
    if (template instanceof Template) {
      return template.render(ctx);
    }

    if (Array.isArray(template)) {
      return template.map((item) => this.renderVariableTemplate(item, ctx));
    }

    if (typeof template === "object" && template !== null) {
      const result: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(template)) {
        result[key] = this.renderVariableTemplate(value as VariableTemplate, ctx);
      }
      return result;
    }

    return template;
  }

  private createCallbacks(): ProxyCallbacks {
    return {
      renderVar: (ctx, module, varName, prefix) =>
        this.renderVar(ctx, module, varName, prefix),
      renderTask: (ctx, module, taskName, prefix) =>
        this.renderTask(ctx, module, taskName, prefix),
      renderTaskInline: (ctx, module, taskName, prefix, overrideVars) =>
        this.renderTaskInline(ctx, module, taskName, prefix, overrideVars),
    };
  }
}

// ============================================================
// Testing with import.meta.main
// ============================================================

if (import.meta.main) {
  const { resolveTaskDefs, resolveVariableDefs } = await import("../ast");

  // Create test module templates directly
  const baseModule: ModuleTemplate = {
    vars: resolveVariableDefs({
      greeting: "Hi",
      you: "there",
    }),
    tasks: resolveTaskDefs({
      baseTask: {
        cmd: 'echo "This is the base task"',
      },
    }),
    modules: {},
    __meta__: { used: new Set() },
  };

  const rootModule: ModuleTemplate = {
    vars: {
      ...baseModule.vars,
      ...resolveVariableDefs({
        greeting: "Hello",
        target: "{{ vars.greeting }}, World!",
      }),
    },
    tasks: {
      ...baseModule.tasks,
      ...resolveTaskDefs({
        sayHello: {
          cmd: 'echo "{{ vars.target }}"',
          desc: "Says hello to the target",
        },
        callingSayHello: {
          cmd: 'echo "About to say hello: {{ tasks.sayHello }}"',
        },
        inlineExample: {
          cmd: 'echo "Inline: {{ tasks.sayHello.inline() }}"',
        },
      }),
    },
    modules: {
      sub: {
        vars: resolveVariableDefs({
          subVar: "I am sub",
        }),
        tasks: resolveTaskDefs({
          subTask: {
            cmd: 'echo "{{ vars.subVar }}"',
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      },
    },
    __meta__: { used: new Set(["base"]) },
  };

  const renderer = new Renderer();
  const result = renderer.renderAllTasks(rootModule);

  console.log("=== Main Tasks ===");
  for (const task of result.main) {
    console.log(`  ${task.name}: ${task.cmd}`);
  }

  console.log("\n=== Dep Tasks ===");
  for (const task of result.deps) {
    console.log(`  ${task.name}: ${task.cmd}`);
  }

  console.log("\n=== Dependency Graph ===");
  for (const [task, deps] of result.graph) {
    console.log(`  ${task} → [${[...deps].join(", ")}]`);
  }
}
