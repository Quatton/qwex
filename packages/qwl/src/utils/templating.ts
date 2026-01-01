import fs from "node:fs";
import path from "node:path";
import nunjucks from "nunjucks";

import { hash } from "./hash";

export function escapeQuotes(str: string): string {
  return str.replace(/"/g, '\\"').replace(/'/g, "\\'");
}

/**
 * Generate a unique EOF delimiter based on content hash
 * Returns uppercase hex string prefixed with EOF_
 */
function generateEofDelimiter(content: string): string {
  const h = hash(content);
  return `EOF_${h.toString(16).toUpperCase().slice(0, 8)}`;
}

/**
 * Custom extension for {% eof %} heredoc tag
 *
 * Usage:
 *   {% eof %}content{% endeof %}
 *   => 'EOF_A1B2C3D4'\ncontent\nEOF_A1B2C3D4
 *
 *   {% eof "CUSTOM" %}content{% endeof %}
 *   => 'CUSTOM'\ncontent\nCUSTOM
 *
 * The delimiter is auto-generated from content hash unless explicitly provided.
 * Does NOT include `cat <<` - user can add that themselves if needed.
 */
class EofExtension implements nunjucks.Extension {
  tags = ["eof"];

  parse(parser: any, nodes: any, _lexer: any): any {
    const tok = parser.nextToken();
    const args = parser.parseSignature(null, true);
    parser.advanceAfterBlockEnd(tok.value);

    const body = parser.parseUntilBlocks("endeof");
    parser.advanceAfterBlockEnd();

    return new nodes.CallExtension(this, "run", args, [body]);
  }

  run(_context: unknown, ...args: unknown[]): nunjucks.runtime.SafeString {
    const body = args.pop() as () => string;
    const explicitDelimiter = args[0] as string | undefined;

    const content = body();
    const delimiter = explicitDelimiter || generateEofDelimiter(content);

    return new nunjucks.runtime.SafeString(`'${delimiter}'\n${content}\n${delimiter}`);
  }
}

/**
 * Custom extension for {% context %} tag
 *
 * This extension renders its body content and tracks dependencies referenced
 * within the block. It outputs eval "$(declare -f)" statements for all dependencies
 * before the rendered content, which properly defines functions in the current shell.
 *
 * Usage:
 *   {% context %}
 *     {{ tasks.myTask }}
 *   {% endcontext %}
 *   => eval "$(declare -f myTask)"\nmyTask
 *
 *   {% context escape=true %}
 *     echo $VAR
 *   {% endcontext %}
 *   => echo \$VAR  (escapes $ to \$)
 *
 * Options:
 * - escape: if true, escapes $ as \$ in the body content
 *
 * The __renderContext is passed from the proxy and contains:
 * - currentDeps: Set of task names referenced during rendering
 * - renderedTasks: Map of task name -> { cmd, desc }
 * - graph: Map of task name -> Set of dependencies
 */
class ContextExtension implements nunjucks.Extension {
  tags = ["context"];

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  parse(parser: any, nodes: any, _lexer: any): any {
    const tok = parser.nextToken();
    const args = parser.parseSignature(null, true);
    parser.advanceAfterBlockEnd(tok.value);

    const body = parser.parseUntilBlocks("endcontext");
    parser.advanceAfterBlockEnd();

    return new nodes.CallExtension(this, "run", args, [body]);
  }

  run(context: any, ...args: unknown[]): nunjucks.runtime.SafeString {
    const body = args.pop() as () => string;
    const options = (args[0] as { escape?: boolean }) || {};

    // Get the render context from the template context
    const renderContext = context.ctx?.__renderContext;

    if (!renderContext) {
      // If no render context, just render the body normally
      let content = body();
      if (options.escape) {
        content = content.replace(/\$/g, "\\$");
      }
      return new nunjucks.runtime.SafeString(content);
    }

    // Capture dependencies before rendering
    const depsBefore = new Set(renderContext.currentDeps);

    // Render the body content (this will accumulate deps in currentDeps)
    let content = body();

    // Apply escape if requested
    if (options.escape) {
      content = content.replace(/\$/g, "\\$");
    }

    // Find new dependencies added during body rendering
    const newDeps: string[] = [];
    for (const dep of renderContext.currentDeps) {
      if (!depsBefore.has(dep)) {
        newDeps.push(dep);
      }
    }

    // Also check for deps captured during variable pre-rendering
    // These are stored in varCapturedDeps keyed by the rendered string value
    for (const [renderedValue, capturedDeps] of renderContext.varCapturedDeps || []) {
      // If the rendered content contains this pre-rendered value, add its deps
      if (content.includes(renderedValue)) {
        for (const dep of capturedDeps) {
          if (!depsBefore.has(dep) && !newDeps.includes(dep)) {
            newDeps.push(dep);
            renderContext.currentDeps.add(dep);
          }
        }
      }
    }

    // Generate eval "$(declare -f)" statements for new dependencies
    if (newDeps.length === 0) {
      return new nunjucks.runtime.SafeString(content);
    }

    const declares = newDeps.map((dep) => `$(declare -f ${dep})`).join("\n");

    return new nunjucks.runtime.SafeString(`${declares}\n${content}`);
  }
}

// Create the nunjucks environment
const nj = new nunjucks.Environment(null, {
  autoescape: false,
  trimBlocks: true,
  lstripBlocks: true,
  tags: {
    commentStart: "<#",
    commentEnd: "#>",
  },
});

// Register extensions
nj.addExtension("EofExtension", new EofExtension());
nj.addExtension("ContextExtension", new ContextExtension());

// Global state for current module path (set during rendering)
let currentModulePath: string | null = null;

export function setCurrentModulePath(modulePath: string | null): void {
  currentModulePath = modulePath;
}

export function getCurrentModulePath(): string | null {
  return currentModulePath;
}

/**
 * Global `uses()` function - reads file content synchronously
 * Available in templates as {{ uses("./path/to/file.sh") }}
 */
nj.addGlobal("uses", (filePath: string): string => {
  if (!currentModulePath) {
    throw new Error("uses() called outside of module rendering context");
  }

  const resolvedPath = path.isAbsolute(filePath)
    ? filePath
    : path.resolve(path.dirname(currentModulePath), filePath);

  try {
    return fs.readFileSync(resolvedPath, "utf8");
  } catch (e) {
    throw new Error(`uses(): Failed to read file '${filePath}': ${(e as Error).message}`);
  }
});

nj.addGlobal("env", process.env);

const color = (text: string, colorInput: string): string => {
  const colorCode = Bun.color(colorInput, "ansi");
  const resetCode = Bun.color("#ffffff", "ansi");
  if (!colorCode) {
    return text;
  }
  return `${colorCode}${text}${resetCode}`;
};

nj.addFilter("color", color);
nj.addFilter("grey", (text: string) => color(text, "grey"));
nj.addFilter("black", (text: string) => color(text, "black"));
nj.addFilter("brightBlack", (text: string) => color(text, "brightBlack"));
nj.addFilter("escape", (text: string) =>
  text.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\$/g, "\\$").replace(/`/g, "\\`"),
);
// do not add bash_escape! just use escape. also you likely not need it trim already exists
nj.addFilter("multiline", (text: string) => text.trim().replace(/(?<!\\)\n/g, " \\\n"));
nj.addFilter("red", (text: string) => color(text, "red"));
nj.addFilter("green", (text: string) => color(text, "green"));
nj.addFilter("yellow", (text: string): string => color(text, "yellow"));
nj.addFilter("blue", (text: string): string => color(text, "blue"));
nj.addFilter("magenta", (text: string): string => color(text, "magenta"));
nj.addFilter("cyan", (text: string): string => color(text, "cyan"));
nj.addFilter("white", (text: string): string => color(text, "white"));
nj.addFilter("bold", (text: string): string => color(text, "bold"));

export { nj };

// if (import.meta.main) {
//   // Test 1: Simple context without render context (should just pass through)
//   console.log("=== Test 1: No render context ===");
//   const template1 = nj.renderString(`{% context %}Hello {{ name }}{% endcontext %}`, {
//     name: "World",
//   });
//   console.log("Output:", template1);

//   // Test 2: With mock render context
//   console.log("\n=== Test 2: With mock render context ===");
//   const mockRenderContext = {
//     currentDeps: new Set<string>(),
//     renderedTasks: new Map(),
//     graph: new Map(),
//   };

//   // Mock a task ref that adds to currentDeps when toString is called
//   const mockTaskRef = {
//     toString() {
//       mockRenderContext.currentDeps.add("myTask");
//       return "myTask";
//     },
//   };

//   const template2 = nj.renderString(`{% context %}Task: {{ task }}{% endcontext %}`, {
//     __renderContext: mockRenderContext,
//     task: mockTaskRef,
//   });
//   console.log("Output:", template2);
//   console.log("Deps after:", [...mockRenderContext.currentDeps]);
// }

if (import.meta.main) {
  console.log(color("This is green text", "green"));

  const template = `{{ "Hello, {{ name }}!" | color("blue") }}`;

  console.log(nj.renderString(template, { name: "Alice" }));
}
