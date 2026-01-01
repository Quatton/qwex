import { describe, it, expect } from "bun:test";
import { Renderer } from "./renderer";
import { resolveTaskDefs, resolveVariableDefs, type ModuleTemplate } from "../ast";

function createTestModules(): Record<string, ModuleTemplate> {
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

  return { base: baseModule, root: rootModule };
}

describe("Renderer", () => {
  describe("renderAllTasks", () => {
    it("renders simple task with no dependencies", () => {
      const modules = createTestModules();
      const getTemplate = (path: string) => modules[path]!;
      const renderer = new Renderer(getTemplate);

      const result = renderer.renderAllTasks("root");

      expect(result.main).toBeInstanceOf(Array);
      expect(result.deps).toBeInstanceOf(Array);
      expect(result.graph).toBeInstanceOf(Map);
    });

    it("renders variables inline", () => {
      const modules: Record<string, ModuleTemplate> = {
        simple: {
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
        },
      };

      const renderer = new Renderer((path) => modules[path]!);
      const result = renderer.renderAllTasks("simple");

      const greetTask = result.main.find((t) => t.name === "greet");
      expect(greetTask?.cmd).toBe('echo "Hello, World!"');
    });

    it("renders nested variables", () => {
      const modules: Record<string, ModuleTemplate> = {
        nested: {
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
        },
      };

      const renderer = new Renderer((path) => modules[path]!);
      const result = renderer.renderAllTasks("nested");

      const testTask = result.main.find((t) => t.name === "test");
      expect(testTask?.cmd).toBe('echo "Hello, World"');
    });

    it("tracks task references as dependencies", () => {
      const modules: Record<string, ModuleTemplate> = {
        deps: {
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
        },
      };

      const renderer = new Renderer((path) => modules[path]!);
      const result = renderer.renderAllTasks("deps");

      const deps = result.graph.get("second");
      expect(deps?.has("first")).toBe(true);
    });

    it("renders task reference as canonical name", () => {
      const modules: Record<string, ModuleTemplate> = {
        ref: {
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
        },
      };

      const renderer = new Renderer((path) => modules[path]!);
      const result = renderer.renderAllTasks("ref");

      const secondTask = result.main.find((t) => t.name === "second");
      expect(secondTask?.cmd).toBe('echo "ref: first"');
    });

    it("inlines task with .inline()", () => {
      const modules: Record<string, ModuleTemplate> = {
        inline: {
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
        },
      };

      const renderer = new Renderer((path) => modules[path]!);
      const result = renderer.renderAllTasks("inline");

      const wrapperTask = result.main.find((t) => t.name === "wrapper");
      expect(wrapperTask?.cmd).toBe('start; echo "Hello"; end');
    });

    it("separates main and dep tasks", () => {
      const modules = createTestModules();
      const renderer = new Renderer((path) => modules[path]!);
      const result = renderer.renderAllTasks("root");

      // Main tasks are top-level
      const mainNames = result.main.map((t) => t.name);
      expect(mainNames).toContain("sayHello");
      expect(mainNames).toContain("callingSayHello");
      expect(mainNames).toContain("baseTask");
    });

    it("generates hash for each task", () => {
      const modules: Record<string, ModuleTemplate> = {
        hash: {
          vars: resolveVariableDefs({}),
          tasks: resolveTaskDefs({
            test: {
              cmd: "echo test",
            },
          }),
          modules: {},
          __meta__: { used: new Set() },
        },
      };

      const renderer = new Renderer((path) => modules[path]!);
      const result = renderer.renderAllTasks("hash");

      const testTask = result.main.find((t) => t.name === "test");
      expect(testTask?.hash).toBeDefined();
      expect(typeof testTask?.hash).toBe("string");
      expect(testTask?.hash.length).toBeGreaterThan(0);
    });

    it("throws on circular task dependency", () => {
      const modules: Record<string, ModuleTemplate> = {
        circular: {
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
        },
      };

      const renderer = new Renderer((path) => modules[path]!);

      expect(() => renderer.renderAllTasks("circular")).toThrow(/[Cc]ircular/);
    });

    it("throws on circular variable dependency", () => {
      const modules: Record<string, ModuleTemplate> = {
        circular: {
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
        },
      };

      const renderer = new Renderer((path) => modules[path]!);

      expect(() => renderer.renderAllTasks("circular")).toThrow(/[Cc]ircular/);
    });
  });

  describe("submodule tasks", () => {
    it("renders submodule task with correct prefix", () => {
      const modules: Record<string, ModuleTemplate> = {
        parent: {
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
        },
      };

      const renderer = new Renderer((path) => modules[path]!);
      const result = renderer.renderAllTasks("parent");

      // Main task should reference child.childTask
      const mainTask = result.main.find((t) => t.name === "main");
      expect(mainTask?.cmd).toBe('echo "calling child.childTask"');

      // Child task should be in deps with prefixed name
      const childTask = result.deps.find((t) => t.name === "child.childTask");
      expect(childTask?.cmd).toBe('echo "child value"');
    });
  });
});
