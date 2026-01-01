import { Template } from "nunjucks";
import type { ModuleTemplate, TaskTemplate, VariableTemplate } from "../ast";

export interface RenderedTask {
  cmd: string;
  desc?: string;
}

export interface RenderContext {
  renderedTasks: Map<string, RenderedTask>;
  renderedVars: Map<string, unknown>;
  pendingTasks: Set<string>;
  pendingVars: Set<string>;
  currentDeps: Set<string>;
  graph: Map<string, Set<string>>;
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

function renderVariableTemplate(
  template: VariableTemplate,
  ctx: Record<string, unknown>
): unknown {
  if (template instanceof Template) {
    return template.render(ctx);
  }
  if (Array.isArray(template)) {
    return template.map((item) => renderVariableTemplate(item, ctx));
  }
  if (typeof template === "object" && template !== null) {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(template)) {
      result[key] = renderVariableTemplate(value as VariableTemplate, ctx);
    }
    return result;
  }
  return template;
}

function createTaskCallable(
  ctx: RenderContext,
  module: ModuleTemplate,
  taskName: string,
  prefix: string,
  callbacks: ProxyCallbacks
) {
  const { renderTask, renderTaskInline } = callbacks;

  const inlineMethod = (overrideVars: Record<string, unknown> = {}) => {
    return renderTaskInline(ctx, module, taskName, prefix, overrideVars);
  };

  // HACK: nunjucks wraps functions in memberLookup(), breaking custom toString.
  // Use an object with toString() and inline() method instead of a callable.
  return {
    toString() {
      const depName = renderTask(ctx, module, taskName, prefix);
      ctx.currentDeps.add(depName);
      return depName;
    },
    inline: inlineMethod,
    // DISCUSS: what about these instead?
    // $inline: inlineMethod,
    // $: inlineMethod,
  };
}

export function createRenderProxy(
  ctx: RenderContext,
  module: ModuleTemplate,
  task: TaskTemplate | null,
  prefix: string,
  callbacks: ProxyCallbacks
): Record<string, unknown> {
  const { renderVar } = callbacks;

  const varsProxy = new Proxy(
    {},
    {
      get(_, key: string) {
        // Task vars override module vars
        const taskVarTemplate = task?.vars[key];
        if (taskVarTemplate !== undefined) {
          // Task vars are rendered directly without caching (they're task-scoped)
          return renderVariableTemplate(taskVarTemplate, {
            vars: varsProxy,
            tasks: {},
            modules: {},
          });
        }
        const moduleVarTemplate = module.vars[key];
        if (!moduleVarTemplate) return undefined;
        return renderVar(ctx, module, key, prefix);
      },
    }
  );

  const tasksProxy = new Proxy(
    {},
    {
      get(_, key: string) {
        if (!(key in module.tasks)) return undefined;
        return createTaskCallable(ctx, module, key, prefix, callbacks);
      },
    }
  );

  const modulesProxy = new Proxy(
    {},
    {
      get(_, modName: string) {
        const subModule = module.modules[modName];
        if (!subModule) return undefined;
        const newPrefix = prefix ? `${prefix}.${modName}` : modName;
        return createRenderProxy(ctx, subModule, null, newPrefix, callbacks);
      },
    }
  );

  // Root proxy with alias fallback: {{ foo }} → {{ tasks.foo }} or {{ modules.foo.tasks.* }}
  return new Proxy(
    { vars: varsProxy, tasks: tasksProxy, modules: modulesProxy },
    {
      get(target, key: string) {
        if (key in target) {
          return target[key as keyof typeof target];
        }

        // Alias: {{ foo }} → {{ tasks.foo }}
        if (key in module.tasks) {
          return createTaskCallable(ctx, module, key, prefix, callbacks);
        }

        // Alias: {{ sub }} → {{ modules.sub }} (for {{ sub.taskName }})
        const subModule = module.modules[key];
        if (subModule) {
          const newPrefix = prefix ? `${prefix}.${key}` : key;
          return createModuleAliasProxy(ctx, subModule, newPrefix, callbacks);
        }

        return undefined;
      },
    }
  );
}

function createModuleAliasProxy(
  ctx: RenderContext,
  module: ModuleTemplate,
  prefix: string,
  callbacks: ProxyCallbacks
): Record<string, unknown> {
  // {{ sub.foo }} → {{ modules.sub.tasks.foo }}
  // {{ sub.nested.bar }} → {{ modules.sub.modules.nested.tasks.bar }}
  return new Proxy(
    {},
    {
      get(_, key: string) {
        if (key in module.tasks) {
          return createTaskCallable(ctx, module, key, prefix, callbacks);
        }
        const subModule = module.modules[key];
        if (subModule) {
          const newPrefix = prefix ? `${prefix}.${key}` : key;
          return createModuleAliasProxy(ctx, subModule, newPrefix, callbacks);
        }
        return undefined;
      },
    }
  );
}

export function createTaskRenderProxy(
  ctx: RenderContext,
  module: ModuleTemplate,
  task: TaskTemplate,
  prefix: string,
  callbacks: ProxyCallbacks
): Record<string, unknown> {
  return createRenderProxy(ctx, module, task, prefix, callbacks);
}
