import { describe, expect, it } from "bun:test";

import { resolveTaskDefs, resolveVariableDefs, type ModuleTemplate } from "../ast";
import { TASK_FN_PREFIX } from "../constants";
import { Renderer } from "./renderer";

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

      const greetTask = result.main.find((t) => t.key === "greet");
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

      const testTask = result.main.find((t) => t.key === "test");
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

      const secondTask = result.main.find((t) => t.key === "second");
      expect(secondTask?.cmd).toBe(`echo "ref: ${TASK_FN_PREFIX}first"`);
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
            cmd: "start; {{ tasks.base.inline() }}; end",
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const wrapperTask = result.main.find((t) => t.key === "wrapper");
      expect(wrapperTask?.cmd).toBe('start; echo "Hello"; end');
    });

    it("inlines submodule task that uses its own sibling modules", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          main: {
            cmd: "{{ modules.parallel.tasks.compose.inline() }}",
          },
        }),
        modules: {
          parallel: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({
              compose: {
                cmd: '{{ log.info }} "hello"',
              },
            }),
            modules: {
              log: {
                vars: resolveVariableDefs({}),
                tasks: resolveTaskDefs({
                  info: {
                    cmd: "echo INFO:",
                  },
                }),
                modules: {},
                __meta__: { used: new Set() },
              },
            },
            __meta__: { used: new Set() },
          },
        },
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const mainTask = result.main.find((t) => t.key === "main");
      expect(mainTask?.cmd).toBe(`${TASK_FN_PREFIX}parallel:log:info "hello"`);
    });

    it("separates main and dep tasks", () => {
      const module = createRootModule();
      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      // Main tasks are top-level
      const mainNames = result.main.map((t) => t.key);
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

      const testTask = result.main.find((t) => t.key === "test");
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
      const mainTask = result.main.find((t) => t.key === "main");
      expect(mainTask?.cmd).toBe(`echo "calling ${TASK_FN_PREFIX}child:childTask"`);

      // Child task should be in deps with prefixed name
      const childTask = result.deps.find((t) => t.key === "child.childTask");
      expect(childTask?.cmd).toBe('echo "child value"');
    });

    it("resolves various module/task path forms", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          fullPath: {
            cmd: 'echo "callingA {{ modules.child.tasks.childTask }}"',
          },
          dottedPath: {
            cmd: 'echo "callingB {{ child.childTask }}"',
          },
          nestedTasksPath: {
            cmd: 'echo "callingC {{ child.tasks.childTask }}"',
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

      const expectedRef = `${TASK_FN_PREFIX}child:childTask`;

      const find = (name: string) => [...result.main, ...result.deps].find((t) => t.key === name);

      const full = find("fullPath");
      const dotted = find("dottedPath");
      const nested = find("nestedTasksPath");

      const fullCmd = `echo "callingA ${expectedRef}"`;
      const dottedCmd = `echo "callingB ${expectedRef}"`;
      const nestedCmd = `echo "callingC ${expectedRef}"`;

      expect(full?.cmd).toBe(fullCmd);
      expect(dotted?.cmd).toBe(dottedCmd);
      expect(nested?.cmd).toBe(nestedCmd);
    });

    it("resolves module variable path forms", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          varFull: {
            cmd: 'echo "varA {{ modules.child.vars.childVar }}"',
          },
          // SHOULD NOT WORK?
          // varDotted: {
          //   cmd: 'echo "varB {{ child.childVar }}"',
          // },
          varNested: {
            cmd: 'echo "varC {{ child.vars.childVar }}"',
          },
        }),
        modules: {
          child: {
            vars: resolveVariableDefs({
              childVar: "child value",
            }),
            tasks: resolveTaskDefs({}),
            modules: {},
            __meta__: { used: new Set() },
          },
        },
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const find = (name: string) => [...result.main, ...result.deps].find((t) => t.key === name);

      const full = find("varFull");
      const nested = find("varNested");

      expect(full?.cmd).toBe('echo "varA child value"');
      expect(nested?.cmd).toBe('echo "varC child value"');
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
      const sharedTasks = allTasks.filter((t) => t.key === "shared");
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
      const helperTasks = result.deps.filter((t) => t.key === "sub.helper");
      expect(helperTasks.length).toBe(1);
    });

    it("deduplicates identical tasks across modules (uv-workspace style)", () => {
      // Mirrors the real-world shape from playground/uv-workspace:
      // - user imports std/steps
      // - user also imports std/log
      // - std/steps itself imports std/log as a submodule (often named logs)
      // We want to ensure we don't end up emitting BOTH steps:logs:error and logs:error.
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          main: {
            cmd: "{{ steps.logs.error }}\n{{ logs.error }}\n",
          },
        }),
        modules: {
          steps: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({}),
            modules: {
              logs: {
                vars: resolveVariableDefs({}),
                tasks: resolveTaskDefs({
                  error: {
                    cmd: "echo boom",
                  },
                }),
                modules: {},
                __meta__: { used: new Set() },
              },
            },
            __meta__: { used: new Set() },
          },
          logs: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({
              error: {
                cmd: "echo boom",
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

      const emitted = [...result.main, ...result.deps].filter(
        (t) => t.key === "steps.logs.error" || t.key === "logs.error",
      );
      expect(emitted.length).toBe(1);

      const mainTask = result.main.find((t) => t.key === "main");
      expect(mainTask?.cmd).toBeDefined();

      const cmd = mainTask?.cmd ?? "";
      const hasSteps = cmd.includes("steps:logs:error");
      // "steps:logs:error" contains "logs:error" as a suffix, so detect standalone logs:error
      // that is NOT preceded by ':' (i.e., not part of steps:logs:error)
      const hasStandaloneLogs = /(^|[^:])logs:error/.test(cmd);
      expect(hasSteps && hasStandaloneLogs).toBe(false);
      expect(hasSteps || hasStandaloneLogs).toBe(true);
    });
  });

  describe("super keyword", () => {
    it("allows submodule to access parent module tasks via super", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          parentTask: {
            cmd: "echo parent",
          },
          main: {
            cmd: "{{ modules.child.tasks.childTask }}",
          },
        }),
        modules: {
          child: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({
              childTask: {
                cmd: 'echo "calling {{ super.tasks.parentTask }}"',
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

      const childTask = result.deps.find((t) => t.key === "child.childTask");
      expect(childTask?.cmd).toBe(`echo "calling ${TASK_FN_PREFIX}parentTask"`);
    });

    it("allows submodule to access parent module vars via super", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({
          parentVar: "hello from parent",
        }),
        tasks: resolveTaskDefs({
          main: {
            cmd: "{{ modules.child.tasks.childTask }}",
          },
        }),
        modules: {
          child: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({
              childTask: {
                cmd: 'echo "{{ super.vars.parentVar }}"',
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

      const childTask = result.deps.find((t) => t.key === "child.childTask");
      expect(childTask?.cmd).toBe('echo "hello from parent"');
    });

    it("allows submodule to access sibling module via super.modules", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          main: {
            cmd: "{{ modules.worker.tasks.run }}",
          },
        }),
        modules: {
          log: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({
              info: {
                cmd: 'echo "[INFO]"',
              },
            }),
            modules: {},
            __meta__: { used: new Set() },
          },
          worker: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({
              run: {
                cmd: '{{ super.modules.log.tasks.info }} && echo "working"',
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

      const workerTask = result.deps.find((t) => t.key === "worker.run");
      expect(workerTask?.cmd).toBe(`${TASK_FN_PREFIX}log:info && echo "working"`);
    });

    it("allows shorthand access to sibling module via super.sibling", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          main: {
            cmd: "{{ modules.worker.tasks.run }}",
          },
        }),
        modules: {
          log: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({
              info: {
                cmd: 'echo "[INFO]"',
              },
            }),
            modules: {},
            __meta__: { used: new Set() },
          },
          worker: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({
              run: {
                cmd: '{{ super.log.info }} && echo "working"',
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

      const workerTask = result.deps.find((t) => t.key === "worker.run");
      expect(workerTask?.cmd).toBe(`${TASK_FN_PREFIX}log:info && echo "working"`);
    });

    it("allows deeply nested modules to access ancestors via super chain", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({
          rootVar: "root-value",
        }),
        tasks: resolveTaskDefs({
          rootTask: {
            cmd: "echo root",
          },
          main: {
            cmd: "{{ modules.level1.modules.level2.tasks.deepTask }}",
          },
        }),
        modules: {
          level1: {
            vars: resolveVariableDefs({
              level1Var: "level1-value",
            }),
            tasks: resolveTaskDefs({}),
            modules: {
              level2: {
                vars: resolveVariableDefs({}),
                tasks: resolveTaskDefs({
                  deepTask: {
                    cmd: 'echo "root={{ super.super.vars.rootVar }}" && {{ super.super.tasks.rootTask }}',
                  },
                }),
                modules: {},
                __meta__: { used: new Set() },
              },
            },
            __meta__: { used: new Set() },
          },
        },
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const deepTask = result.deps.find((t) => t.key === "level1.level2.deepTask");
      expect(deepTask?.cmd).toBe(`echo "root=root-value" && ${TASK_FN_PREFIX}rootTask`);
    });

    it("allows super.super to access grandparent level1 var", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          main: {
            cmd: "{{ modules.level1.modules.level2.tasks.test }}",
          },
        }),
        modules: {
          level1: {
            vars: resolveVariableDefs({
              level1Var: "from-level1",
            }),
            tasks: resolveTaskDefs({}),
            modules: {
              level2: {
                vars: resolveVariableDefs({}),
                tasks: resolveTaskDefs({
                  test: {
                    cmd: 'echo "{{ super.vars.level1Var }}"',
                  },
                }),
                modules: {},
                __meta__: { used: new Set() },
              },
            },
            __meta__: { used: new Set() },
          },
        },
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const testTask = result.deps.find((t) => t.key === "level1.level2.test");
      expect(testTask?.cmd).toBe('echo "from-level1"');
    });

    it("super is undefined at root level (no parent)", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          rootTask: {
            cmd: 'echo "{{ super }}"',
          },
        }),
        modules: {},
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const rootTask = result.main.find((t) => t.key === "rootTask");
      // super should render as empty/undefined at root
      expect(rootTask?.cmd).toBe('echo ""');
    });

    it("nested modules can have their own submodules (recursive modules)", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          main: {
            cmd: "{{ modules.outer.modules.inner.modules.deepest.tasks.deepTask }}",
          },
        }),
        modules: {
          outer: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({}),
            modules: {
              inner: {
                vars: resolveVariableDefs({}),
                tasks: resolveTaskDefs({}),
                modules: {
                  deepest: {
                    vars: resolveVariableDefs({
                      deep: "very deep",
                    }),
                    tasks: resolveTaskDefs({
                      deepTask: {
                        cmd: 'echo "{{ vars.deep }}"',
                      },
                    }),
                    modules: {},
                    __meta__: { used: new Set() },
                  },
                },
                __meta__: { used: new Set() },
              },
            },
            __meta__: { used: new Set() },
          },
        },
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const deepTask = result.deps.find((t) => t.key === "outer.inner.deepest.deepTask");
      expect(deepTask?.cmd).toBe('echo "very deep"');
    });

    it("can reference deeply nested submodule task from parent", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({}),
        tasks: resolveTaskDefs({
          main: {
            cmd: "{{ modules.outer.modules.inner.tasks.innerTask }}",
          },
        }),
        modules: {
          outer: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({}),
            modules: {
              inner: {
                vars: resolveVariableDefs({}),
                tasks: resolveTaskDefs({
                  innerTask: {
                    cmd: "echo inner",
                  },
                }),
                modules: {},
                __meta__: { used: new Set() },
              },
            },
            __meta__: { used: new Set() },
          },
        },
        __meta__: { used: new Set() },
      };

      const renderer = new Renderer();
      const result = renderer.renderAllTasks(module);

      const mainTask = result.main.find((t) => t.key === "main");
      expect(mainTask?.cmd).toBe(`${TASK_FN_PREFIX}outer:inner:innerTask`);
    });

    it("super.inline() works for inlining parent task", () => {
      const module: ModuleTemplate = {
        vars: resolveVariableDefs({
          msg: "hello",
        }),
        tasks: resolveTaskDefs({
          parentTask: {
            cmd: 'echo "{{ vars.msg }}"',
          },
          main: {
            cmd: "{{ modules.child.tasks.childTask.inline() }}",
          },
        }),
        modules: {
          child: {
            vars: resolveVariableDefs({}),
            tasks: resolveTaskDefs({
              childTask: {
                cmd: "start; {{ super.tasks.parentTask.inline() }}; end",
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

      const mainTask = result.main.find((t) => t.key === "main");
      expect(mainTask?.cmd).toBe('start; echo "hello"; end');
    });
  });
});
