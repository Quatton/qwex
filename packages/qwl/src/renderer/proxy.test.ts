import { describe, expect, it } from "bun:test";

import { resolveTaskDefs, resolveVariableDefs, type ModuleTemplate } from "../ast";
import { RenderContext, RenderProxyFactory, type ProxyCallbacks } from "./proxy";

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

describe("RenderContext", () => {
  it("creates an empty context", () => {
    const ctx = new RenderContext();

    expect(ctx.renderedTasks.size).toBe(0);
    expect(ctx.renderedVars.size).toBe(0);
    expect(ctx.pendingTasks.size).toBe(0);
    expect(ctx.pendingVars.size).toBe(0);
    expect(ctx.currentDeps.size).toBe(0);
    expect(ctx.graph.size).toBe(0);
    expect(ctx.mainTasks.size).toBe(0);
  });
});

describe("RenderProxyFactory", () => {
  it("creates proxy with vars, tasks, and modules", () => {
    const module = createTestModule();
    const ctx = new RenderContext();
    const callbacks = createMockCallbacks();
    const factory = new RenderProxyFactory(ctx, callbacks);
    const task = module.tasks.sayHello!;

    const proxy = factory.createForTask(module, task, "");

    expect(proxy.vars).toBeDefined();
    expect(proxy.tasks).toBeDefined();
    expect(proxy.modules).toBeDefined();
  });

  describe("vars proxy", () => {
    it("calls renderVar callback for variable access", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const result = (proxy.vars as Record<string, unknown>).greeting;

      expect(result).toBe("[VAR:greeting]");
    });

    it("returns undefined for non-existent vars", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const result = (proxy.vars as Record<string, unknown>).nonexistent;

      expect(result).toBeUndefined();
    });
  });

  describe("tasks proxy", () => {
    it("returns task ref object with toString", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const taskRef = (proxy.tasks as Record<string, unknown>).greet as {
        toString: () => string;
      };

      expect(typeof taskRef.toString).toBe("function");
    });

    it("adds dependency when toString is called", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const taskRef = (proxy.tasks as Record<string, unknown>).greet as {
        toString: () => string;
      };

      taskRef.toString();

      expect(ctx.currentDeps.has("greet")).toBe(true);
    });

    it("has inline method for inline rendering", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const taskRef = (proxy.tasks as Record<string, unknown>).greet as {
        inline: (vars?: Record<string, unknown>) => string;
      };

      const result = taskRef.inline({ foo: "bar" });

      expect(result).toBe('[INLINE:greet:{"foo":"bar"}]');
    });

    it("inline method with no args", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const taskRef = (proxy.tasks as Record<string, unknown>).greet as {
        inline: () => string;
      };

      const result = taskRef.inline();

      expect(result).toBe("[INLINE:greet:{}]");
    });

    it("returns undefined for non-existent tasks", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const result = (proxy.tasks as Record<string, unknown>).nonexistent;

      expect(result).toBeUndefined();
    });
  });

  describe("modules proxy", () => {
    it("returns nested proxy for submodule", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const subProxy = (proxy.modules as Record<string, unknown>).sub as Record<string, unknown>;

      expect(subProxy).toBeDefined();
      expect(subProxy.vars).toBeDefined();
      expect(subProxy.tasks).toBeDefined();
    });

    it("uses correct prefix for submodule vars", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const subProxy = (proxy.modules as Record<string, unknown>).sub as Record<string, unknown>;
      const result = (subProxy.vars as Record<string, unknown>).subVar;

      expect(result).toBe("[VAR:sub.subVar]");
    });

    it("uses correct prefix for submodule tasks", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const subProxy = (proxy.modules as Record<string, unknown>).sub as Record<string, unknown>;
      const taskRef = (subProxy.tasks as Record<string, unknown>).subTask as {
        toString: () => string;
      };

      expect(taskRef.toString()).toBe("sub:subTask");
    });

    it("returns undefined for non-existent modules", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "");
      const result = (proxy.modules as Record<string, unknown>).nonexistent;

      expect(result).toBeUndefined();
    });
  });

  describe("with prefix", () => {
    it("includes prefix in var paths", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "myprefix");
      const result = (proxy.vars as Record<string, unknown>).greeting;

      expect(result).toBe("[VAR:myprefix.greeting]");
    });

    it("includes prefix in task names", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "myprefix");
      const taskRef = (proxy.tasks as Record<string, unknown>).greet as {
        toString: () => string;
      };

      expect(taskRef.toString()).toBe("myprefix:greet");
    });
  });

  describe("alias fallback", () => {
    it("{{ foo }} resolves to {{ tasks.foo }}", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const taskFn = proxy.greet as { toString: () => string };

      expect(typeof taskFn.toString).toBe("function");
    });

    it("{{ sub }} resolves to submodule alias proxy", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const subProxy = proxy.sub as Record<string, unknown>;

      expect(subProxy).toBeDefined();
    });

    it("{{ sub.subTask }} resolves to {{ modules.sub.tasks.subTask }}", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const subProxy = proxy.sub as Record<string, unknown>;
      const taskFn = subProxy.subTask as { toString: () => string };

      expect(taskFn.toString()).toBe("sub:subTask");
    });

    it("{{ sub.subTask.inline() }} inlines the task", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const subProxy = proxy.sub as Record<string, unknown>;
      const taskFn = subProxy.subTask as {
        inline: (vars?: Record<string, unknown>) => string;
      };

      expect(taskFn.inline()).toBe("[INLINE:sub.subTask:{}]");
    });
  });

  describe("comprehensive task access patterns", () => {
    it("modules.sub.tasks.subTask works", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const modules = proxy.modules as Record<string, unknown>;
      const sub = modules.sub as Record<string, unknown>;
      const tasks = sub.tasks as Record<string, unknown>;
      const taskFn = tasks.subTask as { toString: () => string };

      expect(taskFn.toString()).toBe("sub:subTask");
    });

    it("sub.tasks.subTask works", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const sub = proxy.sub as Record<string, unknown>;
      const tasks = sub.tasks as Record<string, unknown>;
      const taskFn = tasks.subTask as { toString: () => string };

      expect(taskFn.toString()).toBe("sub:subTask");
    });

    it("sub.subTask works", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const sub = proxy.sub as Record<string, unknown>;
      const taskFn = sub.subTask as { toString: () => string };

      expect(taskFn.toString()).toBe("sub:subTask");
    });

    it("tasks.greet works (for root module)", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const tasks = proxy.tasks as Record<string, unknown>;
      const taskFn = tasks.greet as { toString: () => string };

      expect(taskFn.toString()).toBe("greet");
    });

    it("greet works (for root module)", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const taskFn = proxy.greet as { toString: () => string };

      expect(taskFn.toString()).toBe("greet");
    });

    it("modules.sub.tasks.subTask.inline() works", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const modules = proxy.modules as Record<string, unknown>;
      const sub = modules.sub as Record<string, unknown>;
      const tasks = sub.tasks as Record<string, unknown>;
      const taskFn = tasks.subTask as { inline: () => string };

      expect(taskFn.inline()).toBe("[INLINE:sub.subTask:{}]");
    });

    it("sub.tasks.subTask.inline() works", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const sub = proxy.sub as Record<string, unknown>;
      const tasks = sub.tasks as Record<string, unknown>;
      const taskFn = tasks.subTask as { inline: () => string };

      expect(taskFn.inline()).toBe("[INLINE:sub.subTask:{}]");
    });

    it("sub.subTask.inline() works", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const sub = proxy.sub as Record<string, unknown>;
      const taskFn = sub.subTask as { inline: () => string };

      expect(taskFn.inline()).toBe("[INLINE:sub.subTask:{}]");
    });

    it("tasks.greet.inline() works (for root module)", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const tasks = proxy.tasks as Record<string, unknown>;
      const taskFn = tasks.greet as { inline: () => string };

      expect(taskFn.inline()).toBe("[INLINE:greet:{}]");
    });

    it("greet.inline() works (for root module)", () => {
      const module = createTestModule();
      const ctx = new RenderContext();
      const callbacks = createMockCallbacks();
      const factory = new RenderProxyFactory(ctx, callbacks);
      const task = module.tasks.sayHello!;

      const proxy = factory.createForTask(module, task, "") as Record<string, unknown>;
      const taskFn = proxy.greet as { inline: () => string };

      expect(taskFn.inline()).toBe("[INLINE:greet:{}]");
    });
  });
});
