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

  parse(parser: any, nodes: any, lexer: any): any {
    const tok = parser.nextToken();
    const args = parser.parseSignature(null, true);
    parser.advanceAfterBlockEnd(tok.value);

    const body = parser.parseUntilBlocks("endeof");
    parser.advanceAfterBlockEnd();

    return new nodes.CallExtension(this, "run", args, [body]);
  }

  run(context: unknown, ...args: unknown[]): nunjucks.runtime.SafeString {
    const body = args.pop() as () => string;
    const explicitDelimiter = args[0] as string | undefined;

    const content = body();
    const delimiter = explicitDelimiter || generateEofDelimiter(content);

    return new nunjucks.runtime.SafeString(`'${delimiter}'\n${content}\n${delimiter}`);
  }
}

/**
 * Custom extension for {% declare %} tag
 *
 * Usage:
 *   {% declare tasks.myTask %}
 *   => declare -f myTask
 *
 *   {% declare tasks.a, tasks.b %}
 *   => declare -f a b
 */
class DeclareExtension implements nunjucks.Extension {
  tags = ["declare"];

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  parse(parser: any, nodes: any, lexer: any): any {
    const tok = parser.nextToken();
    const args = parser.parseSignature(null, true);
    parser.advanceAfterBlockEnd(tok.value);

    return new nodes.CallExtension(this, "run", args, []);
  }

  run(context: unknown, ...args: unknown[]): nunjucks.runtime.SafeString {
    const declarations: string[] = [];

    for (const arg of args) {
      if (arg && typeof arg === "object" && "toString" in arg) {
        // TaskRef object - call toString to get the canonical name
        const name = String(arg);
        declarations.push(name);
      } else if (typeof arg === "string") {
        declarations.push(arg.replace(/\./g, ":"));
      }
    }

    if (declarations.length === 0) {
      return new nunjucks.runtime.SafeString("");
    }

    return new nunjucks.runtime.SafeString(`declare -f ${declarations.join(" ")}`);
  }
}

// Create the nunjucks environment
const nj = new nunjucks.Environment(null, {
  autoescape: false,
  trimBlocks: true,
  lstripBlocks: true,
});

// Register extensions
nj.addExtension("EofExtension", new EofExtension());
nj.addExtension("DeclareExtension", new DeclareExtension());

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

/**
 * `declare` filter - outputs `declare -f funcname` for a task reference
 *
 * Usage:
 *   {{ tasks.myTask | declare }}  => "declare -f myTask"
 *   {{ "funcName" | declare }}    => "declare -f funcName"
 */
nj.addFilter("declare", (value: unknown): string => {
  if (typeof value === "string") {
    return `declare -f ${value.replace(/\./g, ":")}`;
  }
  if (value && typeof value === "object" && "toString" in value) {
    const name = String(value);
    return `declare -f ${name}`;
  }
  throw new Error(`declare filter: expected task reference or string, got ${typeof value}`);
});

export { nj };
