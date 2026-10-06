/** Shared formatting helpers. */

export const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

export const formatDateTime = (value: string): string => {
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().replace("T", " ").slice(0, 19);
};

export const shortHash = (hash: string): string =>
  hash.length > 20 ? `${hash.slice(0, 10)}…${hash.slice(-8)}` : hash;
