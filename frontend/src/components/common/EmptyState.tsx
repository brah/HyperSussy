interface EmptyStateProps {
  message: string;
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="flex h-32 items-center justify-center px-4 text-center text-sm text-hs-grey">
      {message}
    </div>
  );
}
