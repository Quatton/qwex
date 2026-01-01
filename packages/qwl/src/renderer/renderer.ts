import type { ModuleTemplate, TaskTemplate, VariableTemplate } from "../ast";
import { QwlError } from "../errors";
import { hash } from "../utils/hash";
import {
  createRenderContext,
  createTaskRenderProxy,
  type RenderContext,
  type ProxyCallbacks,
} from "./proxy";

/**
 * TaskNode represents a rendered task without dependency info.
 * Dependencies are tracked separately in the graph.
 */
export interface TaskNode {
  name: string; // canonical unique name (e.g., "myModule.sayHello")
  cmd: string; // rendered body
  hash: string; // hash of cmd for caching/testing
}

/**
 * RenderResult contains the rendered tasks split into main and deps,
 * plus the dependency graph.
 */
export interface RenderResult {
  main: TaskNode[]; // top-level tasks from the root module
  deps: TaskNode[]; // tasks that are dependencies (from submodules or referenced)
  graph: Map<string, Set<string>>; // taskName → Set of dependency names
}

export type TemplateGetter = (
  path: string,
  parentPath?: string
) => ModuleTemplate;

export class Renderer {
  constructor(private getTemplate: TemplateGetter) {}

  /**
   * Main entry point: renders all tasks from a module.
   */
  renderAllTasks(modulePath: string): RenderResult {
    const module = this.getTemplate(modulePath);
    const ctx = createRenderContext();

    // Mark top-level tasks as "main"
    for (const taskName of Object.keys(module.tasks)) {
      ctx.mainTasks.add(taskName);
    }

    // Render all top-level tasks
    for (const taskName of Object.keys(module.tasks)) {
      this.renderTask(ctx, module, taskName, "");
    }

    // Split into main and deps
    const main: TaskNode[] = [];
    const deps: TaskNode[] = [];

    for (const [name, cmd] of ctx.renderedTasks) {
      const node: TaskNode = {
        name,
        cmd,
        hash: hash(cmd).toString(),
      };

      if (ctx.mainTasks.has(name)) {
        main.push(node);
      } else {
        deps.push(node);
      }
    }

    return { main, deps, graph: ctx.graph };
  }

  /**
   * Renders a single task and returns its canonical name.
   * Caches results and detects cycles.
   */
  private renderTask(
    ctx: RenderContext,
    module: ModuleTemplate,
    taskName: string,
    prefix: string
  ): string {
    const canonicalName = prefix ? `${prefix}.${taskName}` : taskName;

    // Already rendered?
    if (ctx.renderedTasks.has(canonicalName)) {
      return canonicalName;
    }

    // Cycle detection
    if (ctx.pendingTasks.has(canonicalName)) {
      throw new QwlError({
        code: "RENDERER_ERROR",
        message: `Circular task dependency detected: ${canonicalName}`,
      });
    }

    ctx.pendingTasks.add(canonicalName);

    // Save current deps and create new set for this task
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

      const proxy = createTaskRenderProxy(
        ctx,
        module,
        task,
        prefix,
        this.createCallbacks()
      );

      const cmd = task.cmd.render(proxy);

      // Store the rendered command
      ctx.renderedTasks.set(canonicalName, cmd);

      // Store dependencies in graph
      ctx.graph.set(canonicalName, new Set(ctx.currentDeps));

      return canonicalName;
    } finally {
      ctx.pendingTasks.delete(canonicalName);
      ctx.currentDeps = savedDeps;
    }
  }

  /**
   * Renders a task inline with optional override vars.
   * Does NOT register as a separate task node.
   */
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

    // Create a modified task with override vars
    const modifiedTask: TaskTemplate = {
      ...task,
      vars: { ...task.vars },
    };

    // Create proxy with override vars injected
    const proxy = createTaskRenderProxy(
      ctx,
      module,
      modifiedTask,
      prefix,
      this.createCallbacks()
    );

    // Inject override vars directly into the proxy context
    const proxyWithOverrides = {
      ...proxy,
      vars: new Proxy(proxy.vars as object, {
        get(target, key: string) {
          if (key in overrideVars) {
            return overrideVars[key];
          }
          return Reflect.get(target, key);
        },
      }),
    };

    return task.cmd.render(proxyWithOverrides);
  }

  /**
   * Renders a variable and caches the result.
   */
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
      if (!template) {
        return undefined;
      }

      const proxy = {
        vars: new Proxy(
          {},
          {
            get: (_, key: string) => this.renderVar(ctx, module, key, prefix),
          }
        ),
        tasks: {}, // vars shouldn't reference tasks
        modules: {},
      };

      const value = this.renderVariableTemplate(template, proxy);
      ctx.renderedVars.set(cacheKey, value);
      return value;
    } finally {
      ctx.pendingVars.delete(cacheKey);
    }
  }

  /**
   * Renders a VariableTemplate based on its type.
   */
  private renderVariableTemplate(
    template: VariableTemplate,
    ctx: Record<string, unknown>
  ): unknown {
    if (typeof template === "object" && "render" in template) {
      // It's a nunjucks Template
      return (template as import("nunjucks").Template).render(ctx);
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

  /**
   * Creates callback functions for the proxy.
   */
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

  const getTemplate = (path: string) => {
    if (path === "root") return rootModule;
    if (path === "base") return baseModule;
    throw new Error(`Unknown path: ${path}`);
  };

  const renderer = new Renderer(getTemplate);
  const result = renderer.renderAllTasks("root");

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
