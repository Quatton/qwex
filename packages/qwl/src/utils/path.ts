import path from "node:path";

export function resolvePath(baseDir: string, filePath: string): string {
  return path.resolve(baseDir, filePath);
}

export function getDirFromSourcePath(sourcePath?: string | null): string {
  if (!sourcePath || !path.isAbsolute(sourcePath)) return process.cwd();
  return path.dirname(sourcePath);
}

export function resolveFromParentOrCwd(specifier: string, parentPath?: string): string {
  if (path.isAbsolute(specifier)) return specifier;

  if (parentPath && path.isAbsolute(parentPath)) {
    return path.resolve(path.dirname(parentPath), specifier);
  }

  return path.resolve(process.cwd(), specifier);
}
