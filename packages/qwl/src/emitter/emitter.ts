import type { TaskNode, RenderResult } from "../renderer";

/**
 * EmitResult contains the generated bash script and metadata.
 */
export interface EmitResult {
  script: string;
  taskCount: number;
}

/**
 * Emitter generates bash scripts from rendered TaskNodes.
 */
export class Emitter {
  /**
   * Emits a complete bash script from RenderResult.
   * Includes:
   * - Shebang
   * - Help function listing all main tasks
   * - All task functions (deps first, then main)
   * - Dispatch logic
   */
  emit(result: RenderResult): EmitResult {
    const lines: string[] = [];

    // Shebang
    lines.push("#!/usr/bin/env bash");
    lines.push("set -euo pipefail");
    lines.push("");

    // Generate help function
    lines.push(this.generateHelp(result.main));
    lines.push("");

    // Emit dependency tasks first (topological-ish order)
    for (const task of result.deps) {
      lines.push(this.emitTask(task));
      lines.push("");
    }

    // Emit main tasks
    for (const task of result.main) {
      lines.push(this.emitTask(task));
      lines.push("");
    }

    // Dispatch logic
    lines.push(this.generateDispatch(result.main));

    return {
      script: lines.join("\n"),
      taskCount: result.main.length + result.deps.length,
    };
  }

  /**
   * Emits a single task as a bash function.
   */
  private emitTask(task: TaskNode): string {
    const fnName = this.toFunctionName(task.name);
    const lines: string[] = [];

    lines.push(`# Task: ${task.name}`);
    lines.push(`# Hash: ${task.hash}`);
    lines.push(`${fnName}() {`);
    lines.push(`  ${task.cmd}`);
    lines.push("}");

    return lines.join("\n");
  }

  /**
   * Generates a help function that lists all main tasks.
   */
  private generateHelp(mainTasks: TaskNode[]): string {
    const lines: string[] = [];

    lines.push("_qwex_help() {");
    lines.push('  echo "Available tasks:"');

    for (const task of mainTasks) {
      lines.push(`  echo "  ${task.name}"`);
    }

    lines.push("}");

    return lines.join("\n");
  }

  /**
   * Generates dispatch logic to call tasks by name.
   */
  private generateDispatch(mainTasks: TaskNode[]): string {
    const lines: string[] = [];

    lines.push("# Dispatch");
    lines.push('case "${1:-}" in');

    // Help cases
    lines.push('  ""|"-h"|"--help"|"help")');
    lines.push("    _qwex_help");
    lines.push("    ;;");

    // Task cases
    for (const task of mainTasks) {
      const fnName = this.toFunctionName(task.name);
      lines.push(`  "${task.name}")`);
      lines.push(`    ${fnName}`);
      lines.push("    ;;");
    }

    // Default case
    lines.push("  *)");
    lines.push('    echo "Unknown task: $1" >&2');
    lines.push("    _qwex_help");
    lines.push("    exit 1");
    lines.push("    ;;");

    lines.push("esac");

    return lines.join("\n");
  }

  /**
   * Converts a task name to a valid bash function name.
   * E.g., "module.submodule.task" → "task__module__submodule__task"
   */
  private toFunctionName(name: string): string {
    return "task__" + name.replace(/\./g, "__");
  }
}

// ============================================================
// Testing with import.meta.main
// ============================================================

if (import.meta.main) {
  const { Renderer } = await import("../renderer");
  const { resolveTaskDefs, resolveVariableDefs } = await import("../ast");
  type ModuleTemplate = import("../ast").ModuleTemplate;

  const testModule: ModuleTemplate = {
    vars: resolveVariableDefs({
      greeting: "Hello",
      target: "{{ vars.greeting }}, World!",
    }),
    tasks: resolveTaskDefs({
      sayHello: {
        cmd: 'echo "{{ vars.target }}"',
      },
      build: {
        cmd: "npm run build",
      },
      test: {
        cmd: "npm test",
      },
    }),
    modules: {},
    __meta__: { used: new Set() },
  };

  const renderer = new Renderer(() => testModule);
  const result = renderer.renderAllTasks("test");

  const emitter = new Emitter();
  const emitResult = emitter.emit(result);

  console.log("=== Generated Script ===");
  console.log(emitResult.script);
  console.log("\n=== Stats ===");
  console.log(`Total tasks: ${emitResult.taskCount}`);
}
