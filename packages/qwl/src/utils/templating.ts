import fs from "node:fs";
import nunjucks from "nunjucks";

import { getCwd, resolvePath as resolvePathUtil } from "./path";

export function escapeQuotes(str: string): string {
  return str.replace(/"/g, '\\"').replace(/'/g, "\\'");
}

/**
 * Custom extension for {% uses "./path" %}
 *
 * Includes file content directly into the rendered task.
 *
 * Resolution rules:
 * - Absolute paths are used as-is.
 * - Relative paths resolve against __srcdir__ (directory of the current module source).
 */
class UsesExtension implements nunjucks.Extension {
  tags = ["uses"];

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  parse(parser: any, nodes: any, _lexer: any): any {
    const tok = parser.nextToken();
    const args = parser.parseSignature(null, true);
    parser.advanceAfterBlockEnd(tok.value);
    return new nodes.CallExtension(this, "run", args);
  }

  run(context: any, ...args: unknown[]): nunjucks.runtime.SafeString {
    const filePath = args[0];
    if (typeof filePath !== "string") {
      throw new Error("{% uses %} requires a string path argument");
    }

    const ctxDir =
      context?.ctx?.__dir__ && typeof context.ctx.__dir__ === "string"
        ? context.ctx.__dir__
        : context?.ctx?.__srcdir__ && typeof context.ctx.__srcdir__ === "string"
          ? context.ctx.__srcdir__
          : undefined;

    const baseDir = typeof ctxDir === "string" ? ctxDir : getCwd();
    const resolvedPath = resolvePathUtil(baseDir, filePath);

    try {
      const content = fs.readFileSync(resolvedPath, "utf8");
      return new nunjucks.runtime.SafeString(content);
    } catch (e) {
      const src = context?.ctx?.__src__;
      const srcHint = typeof src === "string" ? ` (from ${src})` : "";
      throw new Error(
        `{% uses %}: Failed to read file '${filePath}' resolved to '${resolvedPath}'${srcHint}: ${(e as Error).message}`,
      );
    }
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
nj.addExtension("UsesExtension", new UsesExtension());

nj.addGlobal("env", Bun.env);
nj.addFilter("resolvePath", (input: string, baseDir?: string) => {
  if (typeof input !== "string") return input;
  const base = typeof baseDir === "string" ? baseDir : getCwd();
  return resolvePathUtil(base, input);
});

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
