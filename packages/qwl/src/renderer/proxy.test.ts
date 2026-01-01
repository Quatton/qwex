import { describe, it, expect } from "bun:test";
import {
  createRenderContext,
  createRenderProxy,
  type ProxyCallbacks,
} from "./proxy";
import { resolveTaskDefs, resolveVariableDefs, type ModuleTemplate } from "../ast";

function createTestModule(): ModuleTemplate {
  return {
    vars: resolveVariableDefs({
      greeting: "Hello",
      target: "{{ vars.greeting }}, World!",
    }),
    tasks: resolveTaskDefs({
      sayHello: {
        cmd: 'echo "{{ vars.target }}"',
      },
      greet: {
        cmd: 'echo "{{ vars.greeting }}"',
      },
    }),
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
    __meta__: { used: new Set() },
  };
}

function createMockCallbacks(): ProxyCallbacks {
  return {
    renderVar: (_ctx, _module, varName, prefix) => {
      const key = prefix ? `${prefix}.${varName}` : varName;
      return `[VAR:${key}]`;
    },
    renderTask: (_ctx, _module, taskName, prefix) => {
      const key = prefix ? `${prefix}.${taskName}` : taskName;
      return key;
    },
    renderTaskInline: (_ctx, _module, taskName, prefix, overrideVars) => {
      const key = prefix ? `${prefix}.${taskName}` : taskName;
      return `[INLINE:${key}:${JSON.stringify(overrideVars)}]`;
    },
  };
}

describe("createRenderContext", () => {
  it("creates an empty context", () => {
    const ctx = createRenderContext();

    expect(ctx.renderedTasks.size).toBe(0);
    expect(ctx.renderedVars.size).toBe(0);
    expect(ctx.pendingTasks.size).toBe(0);
    expect(ctx.pendingVars.size).toBe(0);
    expect(ctx.currentDeps.size).toBe(0);
    expect(ctx.graph.size).toBe(0);
    expect(ctx.mainTasks.size).toBe(0);
  });
});

describe("createRenderProxy", () => {
  it("creates proxy with vars, tasks, and modules", () => {
    const module = createTestModule();
    const ctx = createRenderContext();
    const callbacks = createMockCallbacks();
    const task = module.tasks.sayHello!;

    const proxy = createRenderProxy(ctx, module, task, "", callbacks);

    expect(proxy).toHaveProperty("vars");
    expect(proxy).toHaveProperty("tasks");
    expect(proxy).toHaveProperty("modules");
  });

  describe("vars proxy", () => {
    it("calls renderVar callback for variable access", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const result = (proxy.vars as Record<string, unknown>).greeting;

      expect(result).toBe("[VAR:greeting]");
    });

    it("returns undefined for non-existent vars", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const result = (proxy.vars as Record<string, unknown>).nonexistent;

      expect(result).toBeUndefined();
    });
  });

  describe("tasks proxy", () => {
    it("returns task ref object with toString", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const taskRef = (proxy.tasks as Record<string, unknown>).greet as {
        toString: () => string;
      };

      expect(taskRef.toString()).toBe("greet");
    });

    it("adds dependency when toString is called", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const taskRef = (proxy.tasks as Record<string, unknown>).greet as {
        toString: () => string;
      };

      taskRef.toString();

      expect(ctx.currentDeps.has("greet")).toBe(true);
    });

    it("has inline method for inline rendering", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const taskRef = (proxy.tasks as Record<string, unknown>).greet as {
        inline: (vars?: Record<string, unknown>) => string;
      };

      const result = taskRef.inline({ foo: "bar" });

      expect(result).toBe('[INLINE:greet:{"foo":"bar"}]');
    });

    it("inline method with no args", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const taskRef = (proxy.tasks as Record<string, unknown>).greet as {
        inline: (vars?: Record<string, unknown>) => string;
      };

      const result = taskRef.inline();

      expect(result).toBe('[INLINE:greet:{}]');
    });

    it("returns undefined for non-existent tasks", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const result = (proxy.tasks as Record<string, unknown>).nonexistent;

      expect(result).toBeUndefined();
    });
  });

  describe("modules proxy", () => {
    it("returns nested proxy for submodule", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const subProxy = (proxy.modules as Record<string, unknown>).sub as Record<
        string,
        unknown
      >;

      expect(subProxy).toHaveProperty("vars");
      expect(subProxy).toHaveProperty("tasks");
      expect(subProxy).toHaveProperty("modules");
    });

    it("uses correct prefix for submodule vars", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const subProxy = (proxy.modules as Record<string, unknown>).sub as Record<
        string,
        unknown
      >;
      const result = (subProxy.vars as Record<string, unknown>).subVar;

      expect(result).toBe("[VAR:sub.subVar]");
    });

    it("uses correct prefix for submodule tasks", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const subProxy = (proxy.modules as Record<string, unknown>).sub as Record<
        string,
        unknown
      >;
      const taskRef = (subProxy.tasks as Record<string, unknown>).subTask as {
        toString: () => string;
      };

      // Returns bash-safe function name (dots replaced with double underscores)
      expect(taskRef.toString()).toBe("sub__subTask");
    });

    it("returns undefined for non-existent modules", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks);
      const result = (proxy.modules as Record<string, unknown>).nonexistent;

      expect(result).toBeUndefined();
    });
  });

  describe("with prefix", () => {
    it("includes prefix in var paths", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "myprefix", callbacks);
      const result = (proxy.vars as Record<string, unknown>).greeting;

      expect(result).toBe("[VAR:myprefix.greeting]");
    });

    it("includes prefix in task names", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "myprefix", callbacks);
      const taskRef = (proxy.tasks as Record<string, unknown>).greet as {
        toString: () => string;
      };

      // Returns bash-safe function name (dots replaced with double underscores)
      expect(taskRef.toString()).toBe("myprefix__greet");
    });
  });

  describe("alias fallback", () => {
    it("{{ foo }} resolves to {{ tasks.foo }}", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks) as Record<string, unknown>;
      const taskFn = proxy.greet as { toString: () => string };

      expect(taskFn.toString()).toBe("greet");
      expect(ctx.currentDeps.has("greet")).toBe(true);
    });

    it("{{ sub }} resolves to submodule alias proxy", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks) as Record<string, unknown>;
      const subProxy = proxy.sub as Record<string, unknown>;

      expect(subProxy).toBeDefined();
    });

    it("{{ sub.subTask }} resolves to {{ modules.sub.tasks.subTask }}", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks) as Record<string, unknown>;
      const subProxy = proxy.sub as Record<string, unknown>;
      const taskFn = subProxy.subTask as { toString: () => string };

      // Returns bash-safe function name (dots replaced with double underscores)
      expect(taskFn.toString()).toBe("sub__subTask");
    });

    it("{{ sub.subTask.inline() }} inlines the task", () => {
      const module = createTestModule();
      const ctx = createRenderContext();
      const callbacks = createMockCallbacks();
      const task = module.tasks.sayHello!;

      const proxy = createRenderProxy(ctx, module, task, "", callbacks) as Record<string, unknown>;
      const subProxy = proxy.sub as Record<string, unknown>;
      const taskRef = subProxy.subTask as { inline: (vars?: Record<string, unknown>) => string };

      expect(taskRef.inline()).toBe('[INLINE:sub.subTask:{}]');
    });
  });
});
