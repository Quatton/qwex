import { ArkErrors } from "arktype";

export type QwlErrorCode =
  | "LOADER_ERROR"
  | "YAML_PARSE_ERROR"
  | "SYNTAX_ERROR"
  | "RESOLVER_ERROR"
  | "RENDERER_ERROR"
  | "INTERNAL_ERROR"
  | "UNKNOWN_ERROR";

export class QwlError extends Error {
  public readonly code: QwlErrorCode;

  constructor(opts: { code: QwlErrorCode; message?: string; cause?: unknown }) {
    const message =
      opts.message ?? (opts.cause instanceof Error ? opts.cause.message : "Unknown error");

    super(message);

    this.name = "QwlError";
    this.code = opts.code;
    this.cause = opts.cause;

    Object.setPrototypeOf(this, QwlError.prototype);
  }

  static from(cause: unknown): QwlError {
    if (cause instanceof QwlError) {
      return cause;
    }

    if (cause instanceof ArkErrors) {
      return new QwlError({
        code: "SYNTAX_ERROR",
        message: `AST validation error: ${cause.toString()}`,
        cause,
      });
    }

    if (cause instanceof SyntaxError) {
      return new QwlError({
        code: "YAML_PARSE_ERROR",
        message: `YAML parse error: ${cause.message}`,
        cause,
      });
    }

    return new QwlError({
      code: "UNKNOWN_ERROR",
      message: cause instanceof Error ? cause.message : `Unknown error: ${String(cause)}`,
      cause,
    });
  }
}
