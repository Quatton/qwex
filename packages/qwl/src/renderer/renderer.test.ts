import { describe, it, expect } from "bun:test";
import { Renderer } from "./renderer";
import { resolveTaskDefs, resolveVariableDefs, type ModuleTemplate } from "../ast";

function createRootModule(): ModuleTemplate {
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

  return {
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
}

describe("Renderer", () => {
  describe("renderAllTasks", () => {
    it("renders simple task with no dependencies", () => {
      const module = createRootModule();
      const renderer = new Renderer();

      const result = renderer.renderAllTasks(module);

      expect(result.main).toBeInstanceOf(Array);
      expect(result.deps).toBeInstanceOf(Array);
      expect(result.graph).toBeInstanceOf(Map);
    });

    it("renders variables inline", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({
          name: "World",
        }),
        tasks: resolveTaskDefs({
          greet: {
            cmd: 'echo "Hello, {{ vars.name }}!"',
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const greetTask = result.main.find((t) => t.name === "greet");
      expect(greetTask?.cmd).toBe('echo "Hello, World!"');
    });

    it("renders nested variables", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({
          first: "Hello",
          second: "{{ vars.first }}, World",
        }),
        tasks: resolveTaskDefs({
          test: {
            cmd: 'echo "{{ vars.second }}"',
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const testTask = result.main.find((t) => t.name === "test");
      expect(testTask?.cmd).toBe('echo "Hello, World"');
    });

    it("tracks task references as dependencies", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          first: {
            cmd: "echo first",
          },
          second: {
            cmd: 'echo "depends on {{ tasks.first }}"',
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const deps = result.graph.get("second");
      expect(deps?.has("first")).toBe(true);
    });

    it("renders task reference as canonical name", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          first: {
            cmd: "echo first",
          },
          second: {
            cmd: 'echo "ref: {{ tasks.first }}"',
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const secondTask = result.main.find((t) => t.name === "second");
      expect(secondTask?.cmd).toBe('echo "ref: first"');
    });

    it("inlines task with .inline()", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({
          msg: "Hello",
        }),
        tasks: resolveTaskDefs({
          base: {
            cmd: 'echo "{{ vars.msg }}"',
          },
          wrapper: {
            cmd: 'start; {{ tasks.base.inline() }}; end',
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const wrapperTask = result.main.find((t) => t.name === "wrapper");
      expect(wrapperTask?.cmd).toBe('start; echo "Hello"; end');
    });

    it("separates main and dep tasks", () => {
      const module = createRootModule();
      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      // Main tasks are top-level
      const mainNames = result.main.map((t) => t.name);
      expect(mainNames).toContain("sayHello");
      expect(mainNames).toContain("callingSayHello");
      expect(mainNames).toContain("baseTask");
    });

    it("generates hash for each task", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          test: {
            cmd: "echo test",
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const testTask = result.main.find((t) => t.name === "test");
      expect(testTask?.hash).toBeDefined();
      expect(typeof testTask?.hash).toBe("string");
      expect(testTask?.hash.length).toBeGreaterThan(0);
    });

    it("throws on circular task dependency", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          a: {
            cmd: "{{ tasks.b }}",
          },
          b: {
            cmd: "{{ tasks.a }}",
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();

      expect(() => renderer.renderAllTasks(module)).toThrow(/[Cc]ircular/);
    });

    it("throws on circular variable dependency", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({
          a: "{{ vars.b }}",
          b: "{{ vars.a }}",
        }),
        tasks: resolveTaskDefs({
          test: {
            cmd: "echo {{ vars.a }}",
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();

      expect(() => renderer.renderAllTasks(module)).toThrow(/[Cc]ircular/);
    });
  });

  describe("submodule tasks", () => {
    it("renders submodule task with correct prefix", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          main: {
            cmd: 'echo "calling {{ modules.child.tasks.childTask }}"',
          },
        }),
        modules: {
          child: {
            vars: resolveVariableDefs({
              childVar: "child value",
            }),
            tasks: resolveTaskDefs({
              childTask: {
                cmd: 'echo "{{ vars.childVar }}"',
              },
            }),
            modules: {},
            __meta__: { used: new Set() },
          },
        },
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      // Main task should reference child.childTask as bash-safe name (colon)
      const mainTask = result.main.find((t) => t.name === "main");
      expect(mainTask?.cmd).toBe('echo "calling child:childTask"');

      // Child task should be in deps with prefixed name
      const childTask = result.deps.find((t) => t.name === "child.childTask");
      expect(childTask?.cmd).toBe('echo "child value"');
    });
  });

  describe("deduplication", () => {
    it("does not duplicate tasks referenced multiple times", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          shared: {
            cmd: "echo shared",
          },
          first: {
            cmd: 'echo "first {{ tasks.shared }}"',
          },
          second: {
            cmd: 'echo "second {{ tasks.shared }}"',
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      // shared should appear exactly once
      const allTasks = [...result.main, ...result.deps];
      const sharedTasks = allTasks.filter((t) => t.name === "shared");
      expect(sharedTasks.length).toBe(1);
    });

    it("deduplicates submodule tasks referenced from multiple places", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          first: {
            cmd: 'echo "first {{ modules.sub.tasks.helper }}"',
          },
          second: {
            cmd: 'echo "second {{ modules.sub.tasks.helper }}"',
          },
        }),
        modules: {
          sub: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({
              helper: {
                cmd: "echo helper",
              },
            }),
            modules: {},
            __meta__: { used: new Set() },
          },
        },
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      // sub.helper should appear exactly once in deps
      const helperTasks = result.deps.filter((t) => t.name === "sub.helper");
      expect(helperTasks.length).toBe(1);
    });
  });
});
