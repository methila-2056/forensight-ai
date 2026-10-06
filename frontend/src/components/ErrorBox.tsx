export default function ErrorBox({ message }: { message: string }): JSX.Element {
  return (
    <div className="border border-red-800 bg-red-950/50 px-4 py-3">
      <p className="font-mono text-[10px] uppercase tracking-widest text-red-500">Error</p>
      <p className="mt-1 text-sm text-red-300">{message}</p>
    </div>
  );
}
