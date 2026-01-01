import path from "node:path";

export function getCwd(): string {
  return process.cwd();
}

export function getPwd(): string {
  return process.env.PWD ?? process.cwd();
}

export function resolvePath(baseDir: string, filePath: string): string {
  if (path.isAbsolute(filePath)) return filePath;
  return path.resolve(baseDir, filePath);
}

export function getDirFromSourcePath(sourcePath?: string | null): string {
  if (!sourcePath || !path.isAbsolute(sourcePath)) return getCwd();
  return path.dirname(sourcePath);
}

export function resolveFromSourcePath(
  sourcePath: string | null | undefined,
  filePath: string,
): {
  baseDir: string;
  resolvedPath: string;
} {
  const baseDir = getDirFromSourcePath(sourcePath);
  return { baseDir, resolvedPath: resolvePath(baseDir, filePath) };
}

export function resolveFromParentOrCwd(specifier: string, parentPath?: string): string {
  if (path.isAbsolute(specifier)) return specifier;

  if (parentPath && path.isAbsolute(parentPath)) {
    return path.resolve(path.dirname(parentPath), specifier);
  }

  return path.resolve(getCwd(), specifier);
}
