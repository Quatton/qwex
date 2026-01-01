import type { ModuleTemplate, TaskTemplate } from "../ast";

/**
 * RenderContext tracks state during template rendering.
 * - Caches rendered vars and tasks
 * - Detects circular dependencies
 * - Collects task dependencies
 */
export interface RenderContext {
  // Caching
  renderedTasks: Map<string, string>; // canonicalName → rendered cmd
  renderedVars: Map<string, unknown>; // canonicalVarPath → value

  // Cycle detection
  pendingTasks: Set<string>;
  pendingVars: Set<string>;

  // Current render state (stack-based for nested renders)
  currentDeps: Set<string>;

  // Dependency graph: taskName → Set of task names it depends on
  graph: Map<string, Set<string>>;

  // Track which tasks are "main" (top-level in root module)
  mainTasks: Set<string>;
}

export function createRenderContext(): RenderContext {
  return {
    renderedTasks: new Map(),
    renderedVars: new Map(),
    pendingTasks: new Set(),
    pendingVars: new Set(),
    currentDeps: new Set(),
    graph: new Map(),
    mainTasks: new Set(),
  };
}

type RenderVarFn = (
  ctx: RenderContext,
  module: ModuleTemplate,
  varName: string,
  prefix: string
) => unknown;

type RenderTaskFn = (
  ctx: RenderContext,
  module: ModuleTemplate,
  taskName: string,
  prefix: string
) => string;

type RenderTaskInlineFn = (
  ctx: RenderContext,
  module: ModuleTemplate,
  taskName: string,
  prefix: string,
  overrideVars: Record<string, unknown>
) => string;

export interface ProxyCallbacks {
  renderVar: RenderVarFn;
  renderTask: RenderTaskFn;
  renderTaskInline: RenderTaskInlineFn;
}

/**
 * Creates a proxy object for nunjucks template rendering.
 *
 * Intercepts:
 * - vars.X → renders variable inline
 * - tasks.X → returns canonical name, registers as dependency
 * - tasks.X.inline({}) → renders task inline with overrides
 * - modules.X → returns nested proxy for submodule
 */
export function createRenderProxy(
  ctx: RenderContext,
  module: ModuleTemplate,
  task: TaskTemplate | null,
  prefix: string,
  callbacks: ProxyCallbacks
): Record<string, unknown> {
  const { renderVar, renderTask, renderTaskInline } = callbacks;

  const varsProxy = new Proxy(
    {},
    {
      get(_, key: string) {
        // Task vars override module vars
        const template = task?.vars[key] ?? module.vars[key];
        if (!template) {
          return undefined;
        }
        return renderVar(ctx, module, key, prefix);
      },
    }
  );

  const tasksProxy = new Proxy(
    {},
    {
      get(_, key: string) {
        if (!(key in module.tasks)) {
          return undefined;
        }

        // Return an object that:
        // 1. When coerced to string ({{ tasks.foo }}), returns the canonical name
        // 2. Has an inline() method for {{ tasks.foo.inline({...}) }}
        const taskRef = {
          toString: () => {
            // Register dependency when used as reference
            const depName = renderTask(ctx, module, key, prefix);
            ctx.currentDeps.add(depName);
            return depName;
          },
          inline: (overrideVars: Record<string, unknown> = {}) => {
            // Render inline without registering as dependency
            return renderTaskInline(ctx, module, key, prefix, overrideVars);
          },
        };

        return taskRef;
      },
    }
  );

  const modulesProxy = new Proxy(
    {},
    {
      get(_, modName: string) {
        const subModule = module.modules[modName];
        if (!subModule) {
          return undefined;
        }
        const newPrefix = prefix ? `${prefix}.${modName}` : modName;
        return createRenderProxy(ctx, subModule, null, newPrefix, callbacks);
      },
    }
  );

  return {
    vars: varsProxy,
    tasks: tasksProxy,
    modules: modulesProxy,
  };
}

/**
 * Creates a proxy specifically for rendering a task's context.
 * This includes task-local vars merged with module vars.
 */
export function createTaskRenderProxy(
  ctx: RenderContext,
  module: ModuleTemplate,
  task: TaskTemplate,
  prefix: string,
  callbacks: ProxyCallbacks
): Record<string, unknown> {
  return createRenderProxy(ctx, module, task, prefix, callbacks);
}
